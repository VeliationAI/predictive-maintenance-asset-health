from __future__ import annotations

import json
from datetime import timedelta

import joblib
import numpy as np
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.metrics import accuracy_score, classification_report, roc_auc_score
from sklearn.model_selection import train_test_split
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import ModelRegistry
from app.services.features import FEATURE_COLUMNS, build_feature_frame, reference_date


def train_and_save(db: Session, organization_id: int, created_by: int | None = None) -> dict:
    settings = get_settings()
    settings.model_dir.mkdir(parents=True, exist_ok=True)
    train_as_of = reference_date() - timedelta(days=90)
    frame = build_feature_frame(db, organization_id, train_as_of, with_future_label=True)
    if frame.empty:
        raise RuntimeError("No assets to train on")

    x = frame[FEATURE_COLUMNS].values
    y = frame["label_failure_90d"].values
    stratify = y if len(np.unique(y)) > 1 else None
    x_train, x_test, y_train, y_test = train_test_split(
        x, y, test_size=0.25, random_state=42, stratify=stratify
    )

    model = GradientBoostingClassifier(random_state=42, n_estimators=160, max_depth=3, learning_rate=0.06)
    pos = max(int(y_train.sum()), 1)
    neg = max(len(y_train) - pos, 1)
    sample_weight = np.where(y_train == 1, neg / pos, 1.0)
    model.fit(x_train, y_train, sample_weight=sample_weight)

    proba = model.predict_proba(x_test)[:, 1] if len(np.unique(y_train)) > 1 else np.zeros(len(y_test))
    preds = (proba >= 0.5).astype(int)
    metrics = {
        "n_assets": int(len(frame)),
        "n_positive": int(y.sum()),
        "features": FEATURE_COLUMNS,
        "accuracy": float(accuracy_score(y_test, preds)) if len(y_test) else None,
        "roc_auc": float(roc_auc_score(y_test, proba)) if len(np.unique(y_test)) > 1 else None,
        "report": classification_report(y_test, preds, zero_division=0),
    }
    importances = sorted(
        zip(FEATURE_COLUMNS, model.feature_importances_.tolist()),
        key=lambda item: item[1],
        reverse=True,
    )
    metrics["feature_importance"] = [
        {"feature": name, "importance": round(value, 4)} for name, value in importances
    ]

    version = f"org{organization_id}-v{reference_date().strftime('%Y%m%d')}"
    model_path = settings.model_dir / f"risk_model_{organization_id}.joblib"
    metrics_path = settings.model_dir / f"metrics_{organization_id}.json"
    joblib.dump({"model": model, "features": FEATURE_COLUMNS, "version": version}, model_path)
    metrics_path.write_text(json.dumps(metrics, indent=2), encoding="utf-8")

    db.query(ModelRegistry).filter(
        ModelRegistry.organization_id == organization_id, ModelRegistry.is_active.is_(True)
    ).update({"is_active": False})
    db.add(
        ModelRegistry(
            organization_id=organization_id,
            version=version,
            path=str(model_path),
            metrics_json=json.dumps(metrics),
            is_active=True,
            created_by=created_by,
        )
    )
    db.commit()
    metrics["model_version"] = version
    metrics["model_path"] = str(model_path)
    return metrics
