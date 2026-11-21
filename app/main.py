"""FastAPI service + asset health dashboard."""

from __future__ import annotations

import json
import os
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .config import METRICS_PATH
from .models import connect, init_db
from .score import score_all
from .train import train_and_save

STATIC_DIR = Path(__file__).resolve().parent / "static"

app = FastAPI(
    title="Predictive Maintenance / Asset Health",
    description="Challenge 18 — DTR and feeder failure risk from load + SAP PM history",
    version="1.0.0",
)

if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.on_event("startup")
def startup() -> None:
    init_db()


@app.get("/")
def home():
    index = STATIC_DIR / "index.html"
    if not index.exists():
        raise HTTPException(404, "Dashboard missing")
    return FileResponse(index)


@app.get("/api/health")
def health():
    return {"status": "ok", "service": "asset-health"}


@app.get("/api/summary")
def summary():
    with connect() as conn:
        totals = conn.execute(
            """
            SELECT
                COUNT(*) AS assets,
                SUM(CASE WHEN a.asset_type = 'DTR' THEN 1 ELSE 0 END) AS dtrs,
                SUM(CASE WHEN a.asset_type = 'FEEDER' THEN 1 ELSE 0 END) AS feeders,
                SUM(CASE WHEN r.risk_band = 'Critical' THEN 1 ELSE 0 END) AS critical_n,
                SUM(CASE WHEN r.risk_band = 'High' THEN 1 ELSE 0 END) AS high_n,
                SUM(CASE WHEN r.risk_band = 'Medium' THEN 1 ELSE 0 END) AS medium_n,
                SUM(CASE WHEN r.risk_band = 'Low' THEN 1 ELSE 0 END) AS low_n,
                ROUND(AVG(r.risk_score), 3) AS avg_risk
            FROM assets a
            LEFT JOIN risk_scores r ON a.equipment_id = r.equipment_id
            """
        ).fetchone()
        by_circle = conn.execute(
            """
            SELECT a.circle,
                   COUNT(*) AS assets,
                   SUM(CASE WHEN r.risk_band IN ('Critical', 'High') THEN 1 ELSE 0 END) AS at_risk,
                   ROUND(AVG(r.risk_score), 3) AS avg_risk
            FROM assets a
            LEFT JOIN risk_scores r ON a.equipment_id = r.equipment_id
            GROUP BY a.circle
            ORDER BY avg_risk DESC
            """
        ).fetchall()
    metrics = {}
    if METRICS_PATH.exists():
        metrics = json.loads(METRICS_PATH.read_text(encoding="utf-8"))
    return {
        "totals": dict(totals) if totals else {},
        "by_circle": [dict(row) for row in by_circle],
        "model": {
            "roc_auc": metrics.get("roc_auc"),
            "accuracy": metrics.get("accuracy"),
            "n_assets": metrics.get("n_assets"),
            "top_features": metrics.get("feature_importance", [])[:6],
        },
    }


@app.get("/api/assets")
def list_assets(
    asset_type: str | None = None,
    circle: str | None = None,
    risk_band: str | None = Query(None, alias="band"),
    q: str | None = None,
    limit: int = 100,
):
    sql = """
        SELECT a.equipment_id, a.asset_type, a.name, a.circle, a.division, a.feeder_code,
               a.capacity_kva, a.install_year, a.functional_location,
               r.risk_score, r.risk_band, r.predicted_failure_90d,
               r.recommended_action, r.scored_at
        FROM assets a
        LEFT JOIN risk_scores r ON a.equipment_id = r.equipment_id
        WHERE 1=1
    """
    params: list = []
    if asset_type:
        sql += " AND a.asset_type = ?"
        params.append(asset_type.upper())
    if circle:
        sql += " AND a.circle = ?"
        params.append(circle)
    if risk_band:
        sql += " AND r.risk_band = ?"
        params.append(risk_band)
    if q:
        sql += " AND (a.equipment_id LIKE ? OR a.name LIKE ? OR a.feeder_code LIKE ?)"
        params.extend([f"%{q}%", f"%{q}%", f"%{q}%"])
    sql += " ORDER BY COALESCE(r.risk_score, 0) DESC LIMIT ?"
    params.append(limit)

    with connect() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [dict(row) for row in rows]


@app.get("/api/assets/{equipment_id}")
def asset_detail(equipment_id: str):
    with connect() as conn:
        asset = conn.execute(
            """
            SELECT a.*, r.risk_score, r.risk_band, r.predicted_failure_90d,
                   r.top_drivers, r.recommended_action, r.scored_at
            FROM assets a
            LEFT JOIN risk_scores r ON a.equipment_id = r.equipment_id
            WHERE a.equipment_id = ?
            """,
            [equipment_id],
        ).fetchone()
        if not asset:
            raise HTTPException(404, "Asset not found")
        notifications = conn.execute(
            """
            SELECT * FROM notifications
            WHERE equipment_id = ?
            ORDER BY created_on DESC LIMIT 20
            """,
            [equipment_id],
        ).fetchall()
        work_orders = conn.execute(
            """
            SELECT * FROM work_orders
            WHERE equipment_id = ?
            ORDER BY created_on DESC LIMIT 20
            """,
            [equipment_id],
        ).fetchall()
        loads = conn.execute(
            """
            SELECT reading_on, load_kw, rated_kw, ambient_c, oil_temp_c
            FROM load_readings
            WHERE equipment_id = ?
            ORDER BY reading_on DESC LIMIT 60
            """,
            [equipment_id],
        ).fetchall()

    payload = dict(asset)
    drivers = []
    if payload.get("top_drivers"):
        try:
            drivers = json.loads(payload["top_drivers"])
        except json.JSONDecodeError:
            drivers = []
    payload["top_drivers"] = drivers
    return {
        "asset": payload,
        "notifications": [dict(r) for r in notifications],
        "work_orders": [dict(r) for r in work_orders],
        "load_readings": list(reversed([dict(r) for r in loads])),
    }


@app.post("/api/retrain")
def retrain():
    metrics = train_and_save()
    n = score_all()
    return {
        "scored": n,
        "roc_auc": metrics.get("roc_auc"),
        "accuracy": metrics.get("accuracy"),
        "feature_importance": metrics.get("feature_importance", [])[:8],
    }


def run() -> None:
    import uvicorn

    port = int(os.environ.get("PORT", "8080"))
    uvicorn.run("app.main:app", host="0.0.0.0", port=port, reload=False)


if __name__ == "__main__":
    run()
