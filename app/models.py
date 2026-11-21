"""SQLite schema mirroring common SAP PM export shapes."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path

from .config import DB_PATH, PROCESSED_DIR

SCHEMA = """
CREATE TABLE IF NOT EXISTS assets (
    equipment_id TEXT PRIMARY KEY,
    asset_type TEXT NOT NULL,              -- DTR | FEEDER
    name TEXT NOT NULL,
    functional_location TEXT NOT NULL,     -- SAP TPLNR-style
    circle TEXT NOT NULL,
    division TEXT NOT NULL,
    feeder_code TEXT,
    capacity_kva REAL,
    install_year INTEGER,
    manufacturer TEXT,
    status TEXT DEFAULT 'OPERATING'
);

CREATE TABLE IF NOT EXISTS notifications (
    notification_id TEXT PRIMARY KEY,      -- SAP QMNUM-style
    equipment_id TEXT NOT NULL,
    created_on TEXT NOT NULL,
    notification_type TEXT NOT NULL,       -- M1 breakdown, M2 corrective, M3 preventive
    short_text TEXT,
    priority TEXT,
    damage_code TEXT,
    downtime_hours REAL DEFAULT 0,
    FOREIGN KEY (equipment_id) REFERENCES assets(equipment_id)
);

CREATE TABLE IF NOT EXISTS work_orders (
    order_id TEXT PRIMARY KEY,             -- SAP AUFNR-style
    equipment_id TEXT NOT NULL,
    notification_id TEXT,
    created_on TEXT NOT NULL,
    completed_on TEXT,
    order_type TEXT NOT NULL,              -- PM01 corrective, PM02 preventive
    work_center TEXT,
    cost_inr REAL DEFAULT 0,
    description TEXT,
    FOREIGN KEY (equipment_id) REFERENCES assets(equipment_id)
);

CREATE TABLE IF NOT EXISTS load_readings (
    reading_id INTEGER PRIMARY KEY AUTOINCREMENT,
    equipment_id TEXT NOT NULL,
    reading_on TEXT NOT NULL,              -- daily peak snapshot
    load_kw REAL NOT NULL,
    rated_kw REAL NOT NULL,
    ambient_c REAL,
    oil_temp_c REAL,
    FOREIGN KEY (equipment_id) REFERENCES assets(equipment_id)
);

CREATE TABLE IF NOT EXISTS risk_scores (
    equipment_id TEXT PRIMARY KEY,
    risk_score REAL NOT NULL,
    risk_band TEXT NOT NULL,
    predicted_failure_90d INTEGER NOT NULL,
    top_drivers TEXT,
    recommended_action TEXT,
    scored_at TEXT NOT NULL,
    FOREIGN KEY (equipment_id) REFERENCES assets(equipment_id)
);

CREATE INDEX IF NOT EXISTS idx_notif_eq ON notifications(equipment_id);
CREATE INDEX IF NOT EXISTS idx_wo_eq ON work_orders(equipment_id);
CREATE INDEX IF NOT EXISTS idx_load_eq ON load_readings(equipment_id);
"""


def ensure_dirs() -> None:
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)


@contextmanager
def connect(db_path: Path | None = None):
    ensure_dirs()
    path = db_path or DB_PATH
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db(db_path: Path | None = None) -> None:
    with connect(db_path) as conn:
        conn.executescript(SCHEMA)
