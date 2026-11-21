from __future__ import annotations

import csv
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import Asset, ImportJob, JobStatus, LoadReading, Notification, WorkOrder
from app.services.score import score_all
from app.services.train import train_and_save

# Reuse synthetic generator from legacy seed module if present
try:
    from app.seed_data import export_raw, generate_synthetic
except ImportError:  # pragma: no cover
    generate_synthetic = None
    export_raw = None


def _read_csv(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def clear_operational_data(db: Session, organization_id: int) -> None:
    for model in (LoadReading, WorkOrder, Notification, Asset):
        db.execute(delete(model).where(model.organization_id == organization_id))
    db.commit()


def ingest_tables(db: Session, organization_id: int, tables: dict[str, list[dict]]) -> int:
    clear_operational_data(db, organization_id)
    assets = []
    for row in tables["assets"]:
        assets.append(
            Asset(
                organization_id=organization_id,
                equipment_id=row["equipment_id"],
                asset_type=row["asset_type"],
                name=row["name"],
                functional_location=row["functional_location"],
                circle=row["circle"],
                division=row["division"],
                feeder_code=row.get("feeder_code") or None,
                capacity_kva=float(row.get("capacity_kva") or 0),
                install_year=int(row.get("install_year") or 2015),
                manufacturer=row.get("manufacturer"),
                status=row.get("status") or "OPERATING",
            )
        )
    db.add_all(assets)
    db.flush()

    db.add_all(
        [
            Notification(
                organization_id=organization_id,
                notification_id=row["notification_id"],
                equipment_id=row["equipment_id"],
                created_on=row["created_on"],
                notification_type=row["notification_type"],
                short_text=row.get("short_text"),
                priority=row.get("priority"),
                damage_code=row.get("damage_code"),
                downtime_hours=float(row.get("downtime_hours") or 0),
            )
            for row in tables["notifications"]
        ]
    )
    db.add_all(
        [
            WorkOrder(
                organization_id=organization_id,
                order_id=row["order_id"],
                equipment_id=row["equipment_id"],
                notification_id=row.get("notification_id") or None,
                created_on=row["created_on"],
                completed_on=row.get("completed_on") or None,
                order_type=row["order_type"],
                work_center=row.get("work_center"),
                cost_inr=float(row.get("cost_inr") or 0),
                description=row.get("description"),
            )
            for row in tables["work_orders"]
        ]
    )
    load_rows = []
    for row in tables["load_readings"]:
        oil = row.get("oil_temp_c")
        load_rows.append(
            LoadReading(
                organization_id=organization_id,
                equipment_id=row["equipment_id"],
                reading_on=row["reading_on"],
                load_kw=float(row["load_kw"]),
                rated_kw=float(row["rated_kw"]),
                ambient_c=float(row["ambient_c"]) if row.get("ambient_c") not in {None, ""} else None,
                oil_temp_c=float(oil) if oil not in {None, ""} else None,
            )
        )
    # Chunk inserts for large load tables
    chunk = 2000
    for i in range(0, len(load_rows), chunk):
        db.add_all(load_rows[i : i + chunk])
        db.flush()
    db.commit()
    return (
        len(tables["assets"])
        + len(tables["notifications"])
        + len(tables["work_orders"])
        + len(tables["load_readings"])
    )


def load_from_raw_dir() -> dict[str, list[dict]]:
    raw = get_settings().raw_dir
    return {
        "assets": _read_csv(raw / "assets.csv"),
        "notifications": _read_csv(raw / "notifications.csv"),
        "work_orders": _read_csv(raw / "work_orders.csv"),
        "load_readings": _read_csv(raw / "load_readings.csv"),
    }


def seed_organization(
    db: Session,
    organization_id: int,
    *,
    from_csv: bool = False,
    user_id: int | None = None,
) -> dict:
    from app.db.models import User

    actor_id = user_id
    if not actor_id:
        user = db.scalar(select(User).where(User.organization_id == organization_id))
        if not user:
            raise RuntimeError("No user available to attribute import job")
        actor_id = user.id
    job = ImportJob(
        organization_id=organization_id,
        created_by=actor_id,
        job_type="sap_pm_csv" if from_csv else "synthetic_seed",
        status=JobStatus.running,
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    try:
        if from_csv:
            tables = load_from_raw_dir()
        else:
            if generate_synthetic is None:
                raise RuntimeError("Synthetic generator unavailable")
            tables = generate_synthetic()
            if export_raw:
                export_raw(tables)
        rows = ingest_tables(db, organization_id, tables)
        metrics = train_and_save(db, organization_id, created_by=job.created_by)
        scored, version = score_all(db, organization_id)
        job.status = JobStatus.succeeded
        job.rows_loaded = rows
        job.message = f"Loaded {rows} rows; scored {scored}; model {version}; AUC={metrics.get('roc_auc')}"
        job.finished_at = datetime.now(timezone.utc)
        db.commit()
        return {"job_id": job.id, "rows": rows, "scored": scored, "metrics": metrics}
    except Exception as exc:  # noqa: BLE001
        job.status = JobStatus.failed
        job.message = str(exc)
        job.finished_at = datetime.now(timezone.utc)
        db.commit()
        raise
