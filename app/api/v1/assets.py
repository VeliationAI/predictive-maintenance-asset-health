from __future__ import annotations

import json
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.api.deps import get_current_user
from app.db.models import Asset, LoadReading, ModelRegistry, Notification, RiskScore, User, WorkOrder
from app.db.session import get_db
from app.schemas import AssetDetail, AssetOut, PaginatedAssets, SummaryOut

router = APIRouter()


@router.get("/summary", response_model=SummaryOut)
def summary(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    org_id = user.organization_id
    assets = db.scalars(select(Asset).where(Asset.organization_id == org_id)).all()
    scores = {
        r.equipment_id: r
        for r in db.scalars(select(RiskScore).where(RiskScore.organization_id == org_id)).all()
    }
    critical = high = medium = low = 0
    risk_sum = 0.0
    scored_n = 0
    dtrs = feeders = 0
    by_circle: dict[str, dict] = {}
    for a in assets:
        if a.asset_type == "DTR":
            dtrs += 1
        else:
            feeders += 1
        circle = by_circle.setdefault(a.circle, {"circle": a.circle, "assets": 0, "at_risk": 0, "risk_sum": 0.0, "scored": 0})
        circle["assets"] += 1
        r = scores.get(a.equipment_id)
        if r:
            scored_n += 1
            risk_sum += r.risk_score
            circle["scored"] += 1
            circle["risk_sum"] += r.risk_score
            if r.risk_band == "Critical":
                critical += 1
                circle["at_risk"] += 1
            elif r.risk_band == "High":
                high += 1
                circle["at_risk"] += 1
            elif r.risk_band == "Medium":
                medium += 1
            else:
                low += 1
    circle_rows = []
    for c in by_circle.values():
        avg = round(c["risk_sum"] / c["scored"], 3) if c["scored"] else None
        circle_rows.append(
            {"circle": c["circle"], "assets": c["assets"], "at_risk": c["at_risk"], "avg_risk": avg}
        )
    circle_rows.sort(key=lambda x: x["avg_risk"] or 0, reverse=True)

    model = db.scalar(
        select(ModelRegistry).where(
            ModelRegistry.organization_id == org_id, ModelRegistry.is_active.is_(True)
        )
    )
    model_payload = {}
    if model and model.metrics_json:
        metrics = json.loads(model.metrics_json)
        model_payload = {
            "roc_auc": metrics.get("roc_auc"),
            "accuracy": metrics.get("accuracy"),
            "n_assets": metrics.get("n_assets"),
            "version": model.version,
            "top_features": metrics.get("feature_importance", [])[:6],
        }

    return SummaryOut(
        totals={
            "assets": len(assets),
            "dtrs": dtrs,
            "feeders": feeders,
            "critical_n": critical,
            "high_n": high,
            "medium_n": medium,
            "low_n": low,
            "avg_risk": round(risk_sum / scored_n, 3) if scored_n else None,
        },
        by_circle=circle_rows,
        model=model_payload,
        organization=user.organization.name,
    )


@router.get("", response_model=PaginatedAssets)
def list_assets(
    asset_type: Optional[str] = None,
    circle: Optional[str] = None,
    band: Optional[str] = None,
    q: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    stmt = (
        select(Asset, RiskScore)
        .outerjoin(RiskScore, RiskScore.asset_id == Asset.id)
        .where(Asset.organization_id == user.organization_id)
    )
    if asset_type:
        stmt = stmt.where(Asset.asset_type == asset_type.upper())
    if circle:
        stmt = stmt.where(Asset.circle == circle)
    if band:
        stmt = stmt.where(RiskScore.risk_band == band)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(
            (Asset.equipment_id.ilike(like))
            | (Asset.name.ilike(like))
            | (Asset.feeder_code.ilike(like))
        )

    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.execute(
        stmt.order_by(RiskScore.risk_score.desc().nullslast(), Asset.equipment_id)
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()

    items = []
    for asset, risk in rows:
        items.append(
            AssetOut(
                equipment_id=asset.equipment_id,
                asset_type=asset.asset_type,
                name=asset.name,
                circle=asset.circle,
                division=asset.division,
                feeder_code=asset.feeder_code,
                capacity_kva=asset.capacity_kva,
                install_year=asset.install_year,
                functional_location=asset.functional_location,
                status=asset.status,
                risk_score=risk.risk_score if risk else None,
                risk_band=risk.risk_band if risk else None,
                predicted_failure_90d=risk.predicted_failure_90d if risk else None,
                recommended_action=risk.recommended_action if risk else None,
                scored_at=risk.scored_at if risk else None,
            )
        )
    return PaginatedAssets(items=items, total=total, page=page, page_size=page_size)


@router.get("/{equipment_id}", response_model=AssetDetail)
def asset_detail(
    equipment_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    asset = db.scalar(
        select(Asset)
        .options(joinedload(Asset.risk_score))
        .where(Asset.organization_id == user.organization_id, Asset.equipment_id == equipment_id)
    )
    if not asset:
        raise HTTPException(404, "Asset not found")
    risk = asset.risk_score
    payload = {
        "equipment_id": asset.equipment_id,
        "asset_type": asset.asset_type,
        "name": asset.name,
        "circle": asset.circle,
        "division": asset.division,
        "feeder_code": asset.feeder_code,
        "capacity_kva": asset.capacity_kva,
        "install_year": asset.install_year,
        "functional_location": asset.functional_location,
        "manufacturer": asset.manufacturer,
        "status": asset.status,
        "risk_score": risk.risk_score if risk else None,
        "risk_band": risk.risk_band if risk else None,
        "predicted_failure_90d": risk.predicted_failure_90d if risk else None,
        "recommended_action": risk.recommended_action if risk else None,
        "model_version": risk.model_version if risk else None,
        "scored_at": risk.scored_at.isoformat() if risk and risk.scored_at else None,
        "top_drivers": json.loads(risk.top_drivers) if risk and risk.top_drivers else [],
    }
    notifs = db.scalars(
        select(Notification)
        .where(
            Notification.organization_id == user.organization_id,
            Notification.equipment_id == equipment_id,
        )
        .order_by(Notification.created_on.desc())
        .limit(20)
    ).all()
    orders = db.scalars(
        select(WorkOrder)
        .where(
            WorkOrder.organization_id == user.organization_id,
            WorkOrder.equipment_id == equipment_id,
        )
        .order_by(WorkOrder.created_on.desc())
        .limit(20)
    ).all()
    loads = db.scalars(
        select(LoadReading)
        .where(
            LoadReading.organization_id == user.organization_id,
            LoadReading.equipment_id == equipment_id,
        )
        .order_by(LoadReading.reading_on.desc())
        .limit(60)
    ).all()
    return AssetDetail(
        asset=payload,
        notifications=[
            {
                "notification_id": n.notification_id,
                "created_on": n.created_on,
                "notification_type": n.notification_type,
                "damage_code": n.damage_code,
                "short_text": n.short_text,
                "downtime_hours": n.downtime_hours,
            }
            for n in notifs
        ],
        work_orders=[
            {
                "order_id": o.order_id,
                "created_on": o.created_on,
                "order_type": o.order_type,
                "cost_inr": o.cost_inr,
                "description": o.description,
            }
            for o in orders
        ],
        load_readings=list(
            reversed(
                [
                    {
                        "reading_on": r.reading_on,
                        "load_kw": r.load_kw,
                        "rated_kw": r.rated_kw,
                        "ambient_c": r.ambient_c,
                        "oil_temp_c": r.oil_temp_c,
                    }
                    for r in loads
                ]
            )
        ),
    )
