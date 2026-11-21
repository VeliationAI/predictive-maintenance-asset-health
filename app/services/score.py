from __future__ import annotations

import json
from datetime import datetime, timezone

import joblib
import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import Asset, ModelRegistry, RiskScore
from app.services.features import FEATURE_COLUMNS, build_feature_frame, recommend_action, reference_date
from app.services.risk_bands import risk_band


def _active_model_path(db: Session, organization_id: int) -> str:
    settings = get_settings()
    reg = db.scalar(
        select(ModelRegistry).where(
            ModelRegistry.organization_id == organization_id,
            ModelRegistry.is_active.is_(True),
        )
    )
    if reg:
        return reg.path
    fallback = settings.model_dir / f"risk_model_{organization_id}.joblib"
    if fallback.exists():
        return str(fallback)
    legacy = settings.model_dir / "risk_model.joblib"
    if legacy.exists():
        return str(legacy)
    raise RuntimeError("No trained model. Run retrain first.")


def score_all(db: Session, organization_id: int) -> tuple[int, str]:
    path = _active_model_path(db, organization_id)
    bundle = joblib.load(path)
    model = bundle["model"]
    features = bundle.get("features", FEATURE_COLUMNS)
    version = bundle.get("version", "v2")
    frame = build_feature_frame(db, organization_id, reference_date(), with_future_label=False)
    if frame.empty:
        return 0, version

    x = frame[features].values
    if hasattr(model, "predict_proba") and len(getattr(model, "classes_", [])) > 1:
        scores = model.predict_proba(x)[:, 1]
    else:
        scores = model.predict(x).astype(float)

    now = datetime.now(timezone.utc)
    # Clear previous scores for org
    db.query(RiskScore).filter(RiskScore.organization_id == organization_id).delete()

    assets = {
        a.equipment_id: a
        for a in db.scalars(select(Asset).where(Asset.organization_id == organization_id)).all()
    }

    for i, (_, row) in enumerate(frame.iterrows()):
        score = float(scores[i])
        heuristic = 0.0
        heuristic += min(0.25, float(row["overload_days_30d"]) * 0.03)
        heuristic += min(0.2, float(row["breakdown_count_90d"]) * 0.08)
        heuristic += min(0.1, max(0, float(row["days_since_last_pm"]) - 90) / 400)
        blended = float(np.clip(0.75 * score + 0.25 * heuristic, 0, 1))
        importances = getattr(model, "feature_importances_", None)
        drivers = []
        if importances is not None:
            ranked = sorted(zip(features, importances), key=lambda x: x[1], reverse=True)[:4]
            drivers = [
                {"feature": name, "value": round(float(row[name]), 3), "model_weight": round(float(w), 4)}
                for name, w in ranked
            ]
        asset = assets.get(row["equipment_id"])
        if not asset:
            continue
        db.add(
            RiskScore(
                organization_id=organization_id,
                asset_id=asset.id,
                equipment_id=asset.equipment_id,
                risk_score=round(blended, 4),
                risk_band=risk_band(blended),
                predicted_failure_90d=blended >= 0.45,
                top_drivers=json.dumps(drivers),
                recommended_action=recommend_action(row, blended),
                model_version=version,
                scored_at=now,
            )
        )
    db.commit()
    return len(frame), version
