"""Score all assets and persist risk bands + interventions."""

from __future__ import annotations

import json
from datetime import datetime, timezone

import joblib
import numpy as np
import pandas as pd

from .config import MODEL_PATH, risk_band
from .features import FEATURE_COLUMNS, build_feature_frame, recommend_action, reference_date
from .models import connect


def _top_drivers(model, row: pd.Series, feature_names: list[str], k: int = 4) -> list[dict]:
    importances = getattr(model, "feature_importances_", None)
    if importances is None:
        return []
    ranked = sorted(zip(feature_names, importances, strict=True), key=lambda x: x[1], reverse=True)
    drivers = []
    for name, weight in ranked[:k]:
        drivers.append(
            {
                "feature": name,
                "value": round(float(row[name]), 3),
                "model_weight": round(float(weight), 4),
            }
        )
    return drivers


def score_all() -> int:
    if not MODEL_PATH.exists():
        raise RuntimeError("Model missing. Run: python -m app.train")

    bundle = joblib.load(MODEL_PATH)
    model = bundle["model"]
    features = bundle.get("features", FEATURE_COLUMNS)
    # Score with features available "today" (no future leakage).
    frame = build_feature_frame(reference_date(), with_future_label=False)
    if frame.empty:
        return 0

    x = frame[features].values
    if hasattr(model, "predict_proba") and len(getattr(model, "classes_", [])) > 1:
        scores = model.predict_proba(x)[:, 1]
    else:
        scores = model.predict(x).astype(float)

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    scored_rows = []
    for i, (_, row) in enumerate(frame.iterrows()):
        score = float(scores[i])
        # Mild calibration with operational heuristics for demo clarity
        heuristic = 0.0
        heuristic += min(0.25, float(row["overload_days_30d"]) * 0.03)
        heuristic += min(0.2, float(row["breakdown_count_90d"]) * 0.08)
        heuristic += min(0.1, max(0, float(row["days_since_last_pm"]) - 90) / 400)
        blended = float(np.clip(0.75 * score + 0.25 * heuristic, 0, 1))
        drivers = _top_drivers(model, row, features)
        action = recommend_action(row, blended)
        scored_rows.append(
            {
                "equipment_id": row["equipment_id"],
                "risk_score": round(blended, 4),
                "risk_band": risk_band(blended),
                "predicted_failure_90d": int(blended >= 0.45),
                "top_drivers": json.dumps(drivers),
                "recommended_action": action,
                "scored_at": now,
            }
        )

    with connect() as conn:
        conn.execute("DELETE FROM risk_scores")
        conn.executemany(
            """
            INSERT INTO risk_scores (
                equipment_id, risk_score, risk_band, predicted_failure_90d,
                top_drivers, recommended_action, scored_at
            ) VALUES (
                :equipment_id, :risk_score, :risk_band, :predicted_failure_90d,
                :top_drivers, :recommended_action, :scored_at
            )
            """,
            scored_rows,
        )
    return len(scored_rows)


def main() -> None:
    n = score_all()
    print(f"Scored {n} assets")


if __name__ == "__main__":
    main()
