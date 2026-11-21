"""Train failure-risk model from engineered features."""

from __future__ import annotations

import json
from pathlib import Path

import joblib
import numpy as np
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.metrics import (
    accuracy_score,
    classification_report,
    roc_auc_score,
)
from sklearn.model_selection import train_test_split

from .config import METRICS_PATH, MODEL_DIR, MODEL_PATH
from datetime import timedelta

from .features import FEATURE_COLUMNS, build_feature_frame, reference_date


def train_and_save(random_state: int = 42) -> dict:
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    # Train as of 90 days ago so labels are true forward failures.
    train_as_of = reference_date() - timedelta(days=90)
    frame = build_feature_frame(train_as_of, with_future_label=True)
    if frame.empty:
        raise RuntimeError("No assets to train on. Run: python -m app.seed")

    x = frame[FEATURE_COLUMNS].values
    y = frame["label_failure_90d"].values

    # Stratify when both classes exist
    stratify = y if len(np.unique(y)) > 1 else None
    x_train, x_test, y_train, y_test = train_test_split(
        x, y, test_size=0.25, random_state=random_state, stratify=stratify
    )

    model = GradientBoostingClassifier(
        random_state=random_state,
        n_estimators=160,
        max_depth=3,
        learning_rate=0.06,
    )
    # Emphasize rare failure class for utility risk ranking.
    pos = max(int(y_train.sum()), 1)
    neg = max(len(y_train) - pos, 1)
    sample_weight = np.where(y_train == 1, neg / pos, 1.0)
    model.fit(x_train, y_train, sample_weight=sample_weight)

    proba = model.predict_proba(x_test)[:, 1] if len(np.unique(y_train)) > 1 else np.zeros(len(y_test))
    preds = (proba >= 0.5).astype(int) if len(proba) else np.array([])

    metrics: dict = {
        "n_assets": int(len(frame)),
        "n_positive": int(y.sum()),
        "features": FEATURE_COLUMNS,
        "accuracy": float(accuracy_score(y_test, preds)) if len(y_test) else None,
    }
    if len(np.unique(y_test)) > 1:
        metrics["roc_auc"] = float(roc_auc_score(y_test, proba))
    else:
        metrics["roc_auc"] = None

    metrics["report"] = classification_report(y_test, preds, zero_division=0)
    importances = sorted(
        zip(FEATURE_COLUMNS, model.feature_importances_.tolist()),
        key=lambda item: item[1],
        reverse=True,
    )
    metrics["feature_importance"] = [
        {"feature": name, "importance": round(value, 4)} for name, value in importances
    ]

    joblib.dump({"model": model, "features": FEATURE_COLUMNS}, MODEL_PATH)
    METRICS_PATH.write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    return metrics


def main() -> None:
    metrics = train_and_save()
    print(json.dumps({k: metrics[k] for k in ("n_assets", "n_positive", "accuracy", "roc_auc")}, indent=2))
    print("Top drivers:")
    for row in metrics["feature_importance"][:8]:
        print(f"  {row['feature']}: {row['importance']}")
    print(f"Saved model -> {MODEL_PATH}")


if __name__ == "__main__":
    main()
