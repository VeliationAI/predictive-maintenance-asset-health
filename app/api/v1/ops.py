from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import require_roles
from app.core.config import get_settings
from app.db.models import ImportJob, Role, User
from app.db.session import get_db
from app.schemas import ImportJobOut, RetrainResponse
from app.services.audit import write_audit
from app.services.ingest import seed_organization
from app.services.score import score_all
from app.services.train import train_and_save

router = APIRouter()


@router.post("/retrain", response_model=RetrainResponse)
def retrain(
    request: Request,
    user: User = Depends(require_roles(Role.admin, Role.analyst)),
    db: Session = Depends(get_db),
):
    metrics = train_and_save(db, user.organization_id, created_by=user.id)
    scored, version = score_all(db, user.organization_id)
    write_audit(
        db,
        action="retrain",
        organization_id=user.organization_id,
        user_id=user.id,
        resource="model",
        detail=version,
        ip_address=request.client.host if request.client else None,
    )
    return RetrainResponse(
        scored=scored,
        roc_auc=metrics.get("roc_auc"),
        accuracy=metrics.get("accuracy"),
        model_version=version,
        feature_importance=metrics.get("feature_importance", [])[:8],
    )


@router.post("/seed", response_model=ImportJobOut)
def seed_demo(
    request: Request,
    user: User = Depends(require_roles(Role.admin, Role.analyst)),
    db: Session = Depends(get_db),
):
    result = seed_organization(db, user.organization_id, from_csv=False, user_id=user.id)
    write_audit(
        db,
        action="seed_demo",
        organization_id=user.organization_id,
        user_id=user.id,
        resource="import_job",
        detail=str(result.get("job_id")),
        ip_address=request.client.host if request.client else None,
    )
    job = db.get(ImportJob, result["job_id"])
    return job


@router.post("/import/sap-csv", response_model=ImportJobOut)
async def import_sap_csv(
    request: Request,
    assets: UploadFile = File(...),
    notifications: UploadFile = File(...),
    work_orders: UploadFile = File(...),
    load_readings: UploadFile = File(...),
    user: User = Depends(require_roles(Role.admin, Role.analyst)),
    db: Session = Depends(get_db),
):
    settings = get_settings()
    raw = settings.raw_dir
    raw.mkdir(parents=True, exist_ok=True)
    mapping = {
        "assets.csv": assets,
        "notifications.csv": notifications,
        "work_orders.csv": work_orders,
        "load_readings.csv": load_readings,
    }
    for name, upload in mapping.items():
        content = await upload.read()
        (raw / name).write_bytes(content)
    try:
        result = seed_organization(db, user.organization_id, from_csv=True, user_id=user.id)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(400, f"Import failed: {exc}") from exc
    write_audit(
        db,
        action="import_sap_csv",
        organization_id=user.organization_id,
        user_id=user.id,
        resource="import_job",
        detail=str(result.get("job_id")),
        ip_address=request.client.host if request.client else None,
    )
    return db.get(ImportJob, result["job_id"])


@router.get("/jobs", response_model=list[ImportJobOut])
def list_jobs(
    user: User = Depends(require_roles(Role.admin, Role.analyst, Role.planner)),
    db: Session = Depends(get_db),
):
    jobs = db.scalars(
        select(ImportJob)
        .where(ImportJob.organization_id == user.organization_id)
        .order_by(ImportJob.created_at.desc())
        .limit(50)
    ).all()
    return jobs
