"""Generate or import SAP PM–shaped Telangana DTR/feeder data."""

from __future__ import annotations

import argparse
import csv
import random
from datetime import datetime, timedelta
from pathlib import Path

from .config import CIRCLES, RAW_DIR
from .models import init_db, connect

RNG = random.Random(42)
MANUFACTURERS = ["BHEL", "Toshiba", "ABB", "Schneider", "Crompton", "Kirloskar"]
DAMAGE = ["OVERLOAD", "INSULATION", "BUSHING", "OIL_LEAK", "HOTSPOT", "RELAY", "CONDUCTOR"]


def _write_csv(path: Path, rows: list[dict], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def generate_synthetic(n_dtr: int = 180, n_feeder: int = 60, days: int = 180) -> dict[str, list[dict]]:
    today = datetime(2026, 11, 20)
    assets: list[dict] = []
    notifications: list[dict] = []
    work_orders: list[dict] = []
    loads: list[dict] = []

    notif_seq = 100000
    order_seq = 400000

    for i in range(1, n_dtr + 1):
        circle = CIRCLES[i % len(CIRCLES)]
        division = f"{circle.split()[0]}-D{(i % 4) + 1}"
        feeder = f"FDR-{(i % n_feeder) + 1:03d}"
        capacity = RNG.choice([100, 160, 250, 315, 500, 630])
        install_year = RNG.randint(2005, 2023)
        eq = f"DTR-{circle[:3].upper()}-{i:04d}"
        # Latent frailty: older + overloaded assets fail more
        frailty = max(0.05, (2026 - install_year) / 40 + RNG.random() * 0.25)
        assets.append(
            {
                "equipment_id": eq,
                "asset_type": "DTR",
                "name": f"{capacity} kVA DTR @ {feeder}",
                "functional_location": f"TG-{circle.replace(' ', '')}-{division}-{feeder}-{eq}",
                "circle": circle,
                "division": division,
                "feeder_code": feeder,
                "capacity_kva": capacity,
                "install_year": install_year,
                "manufacturer": RNG.choice(MANUFACTURERS),
                "status": "OPERATING",
                "_frailty": frailty,
            }
        )

    for i in range(1, n_feeder + 1):
        circle = CIRCLES[i % len(CIRCLES)]
        division = f"{circle.split()[0]}-D{(i % 3) + 1}"
        feeder = f"FDR-{i:03d}"
        eq = f"FDR-{circle[:3].upper()}-{i:03d}"
        install_year = RNG.randint(2008, 2022)
        frailty = max(0.05, (2026 - install_year) / 35 + RNG.random() * 0.2)
        assets.append(
            {
                "equipment_id": eq,
                "asset_type": "FEEDER",
                "name": f"11 kV Feeder {feeder}",
                "functional_location": f"TG-{circle.replace(' ', '')}-{division}-{feeder}",
                "circle": circle,
                "division": division,
                "feeder_code": feeder,
                "capacity_kva": RNG.choice([2000, 3000, 5000, 8000]),
                "install_year": install_year,
                "manufacturer": "Discom Network",
                "status": "OPERATING",
                "_frailty": frailty,
            }
        )

    for asset in assets:
        eq = asset["equipment_id"]
        rated_kw = asset["capacity_kva"] * 0.9
        frailty = asset["_frailty"]
        for day in range(days):
            dt = today - timedelta(days=days - day)
            # Summer peaks (Apr–Jun) and evening peaks
            season = 1.15 if dt.month in {4, 5, 6} else 1.0
            base = rated_kw * (0.55 + frailty * 0.35) * season
            noise = RNG.uniform(0.85, 1.25)
            load_kw = max(10.0, base * noise)
            overload = load_kw / rated_kw
            oil = 45 + overload * 35 + RNG.uniform(-3, 5) if asset["asset_type"] == "DTR" else None
            loads.append(
                {
                    "equipment_id": eq,
                    "reading_on": dt.strftime("%Y-%m-%d"),
                    "load_kw": round(load_kw, 2),
                    "rated_kw": round(rated_kw, 2),
                    "ambient_c": round(28 + (8 if dt.month in {4, 5, 6} else 0) + RNG.uniform(-2, 3), 1),
                    "oil_temp_c": round(oil, 1) if oil is not None else "",
                }
            )

            # Failure / repair events driven by stress
            daily_risk = frailty * 0.012 + max(0, overload - 0.9) * 0.045
            if RNG.random() < daily_risk:
                notif_seq += 1
                order_seq += 1
                ntype = RNG.choices(["M1", "M2", "M3"], weights=[0.35, 0.45, 0.20])[0]
                downtime = round(RNG.uniform(1, 18), 1) if ntype == "M1" else round(RNG.uniform(0, 4), 1)
                damage = RNG.choice(DAMAGE)
                nid = f"N{notif_seq}"
                oid = f"O{order_seq}"
                notifications.append(
                    {
                        "notification_id": nid,
                        "equipment_id": eq,
                        "created_on": dt.strftime("%Y-%m-%d"),
                        "notification_type": ntype,
                        "short_text": f"{damage} on {eq}",
                        "priority": "1" if ntype == "M1" else "2",
                        "damage_code": damage,
                        "downtime_hours": downtime,
                    }
                )
                completed = dt + timedelta(days=RNG.randint(0, 5))
                work_orders.append(
                    {
                        "order_id": oid,
                        "equipment_id": eq,
                        "notification_id": nid,
                        "created_on": dt.strftime("%Y-%m-%d"),
                        "completed_on": completed.strftime("%Y-%m-%d"),
                        "order_type": "PM01" if ntype in {"M1", "M2"} else "PM02",
                        "work_center": f"WC-{asset['circle'][:4].upper()}",
                        "cost_inr": round(RNG.uniform(5000, 180000), 0),
                        "description": f"Repair {damage}",
                    }
                )

        # Occasional preventive without notification
        if RNG.random() < 0.4:
            order_seq += 1
            when = today - timedelta(days=RNG.randint(20, 160))
            work_orders.append(
                {
                    "order_id": f"O{order_seq}",
                    "equipment_id": eq,
                    "notification_id": "",
                    "created_on": when.strftime("%Y-%m-%d"),
                    "completed_on": (when + timedelta(days=1)).strftime("%Y-%m-%d"),
                    "order_type": "PM02",
                    "work_center": f"WC-{asset['circle'][:4].upper()}",
                    "cost_inr": round(RNG.uniform(2000, 25000), 0),
                    "description": "Scheduled preventive maintenance",
                }
            )

    for asset in assets:
        asset.pop("_frailty", None)

    return {
        "assets": assets,
        "notifications": notifications,
        "work_orders": work_orders,
        "load_readings": loads,
    }


def export_raw(tables: dict[str, list[dict]]) -> None:
    _write_csv(
        RAW_DIR / "assets.csv",
        tables["assets"],
        [
            "equipment_id",
            "asset_type",
            "name",
            "functional_location",
            "circle",
            "division",
            "feeder_code",
            "capacity_kva",
            "install_year",
            "manufacturer",
            "status",
        ],
    )
    _write_csv(
        RAW_DIR / "notifications.csv",
        tables["notifications"],
        [
            "notification_id",
            "equipment_id",
            "created_on",
            "notification_type",
            "short_text",
            "priority",
            "damage_code",
            "downtime_hours",
        ],
    )
    _write_csv(
        RAW_DIR / "work_orders.csv",
        tables["work_orders"],
        [
            "order_id",
            "equipment_id",
            "notification_id",
            "created_on",
            "completed_on",
            "order_type",
            "work_center",
            "cost_inr",
            "description",
        ],
    )
    _write_csv(
        RAW_DIR / "load_readings.csv",
        tables["load_readings"],
        ["equipment_id", "reading_on", "load_kw", "rated_kw", "ambient_c", "oil_temp_c"],
    )


def _read_csv(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def load_from_csv() -> dict[str, list[dict]]:
    return {
        "assets": _read_csv(RAW_DIR / "assets.csv"),
        "notifications": _read_csv(RAW_DIR / "notifications.csv"),
        "work_orders": _read_csv(RAW_DIR / "work_orders.csv"),
        "load_readings": _read_csv(RAW_DIR / "load_readings.csv"),
    }


def ingest(tables: dict[str, list[dict]]) -> None:
    init_db()
    with connect() as conn:
        conn.execute("DELETE FROM risk_scores")
        conn.execute("DELETE FROM load_readings")
        conn.execute("DELETE FROM work_orders")
        conn.execute("DELETE FROM notifications")
        conn.execute("DELETE FROM assets")

        conn.executemany(
            """
            INSERT INTO assets (
                equipment_id, asset_type, name, functional_location, circle, division,
                feeder_code, capacity_kva, install_year, manufacturer, status
            ) VALUES (
                :equipment_id, :asset_type, :name, :functional_location, :circle, :division,
                :feeder_code, :capacity_kva, :install_year, :manufacturer, :status
            )
            """,
            tables["assets"],
        )
        conn.executemany(
            """
            INSERT INTO notifications (
                notification_id, equipment_id, created_on, notification_type, short_text,
                priority, damage_code, downtime_hours
            ) VALUES (
                :notification_id, :equipment_id, :created_on, :notification_type, :short_text,
                :priority, :damage_code, :downtime_hours
            )
            """,
            tables["notifications"],
        )
        # Normalize empty notification_id
        wo_rows = []
        for row in tables["work_orders"]:
            cleaned = dict(row)
            if not cleaned.get("notification_id"):
                cleaned["notification_id"] = None
            wo_rows.append(cleaned)
        conn.executemany(
            """
            INSERT INTO work_orders (
                order_id, equipment_id, notification_id, created_on, completed_on,
                order_type, work_center, cost_inr, description
            ) VALUES (
                :order_id, :equipment_id, :notification_id, :created_on, :completed_on,
                :order_type, :work_center, :cost_inr, :description
            )
            """,
            wo_rows,
        )
        load_rows = []
        for row in tables["load_readings"]:
            cleaned = dict(row)
            if cleaned.get("oil_temp_c") in {"", None}:
                cleaned["oil_temp_c"] = None
            load_rows.append(cleaned)
        conn.executemany(
            """
            INSERT INTO load_readings (
                equipment_id, reading_on, load_kw, rated_kw, ambient_c, oil_temp_c
            ) VALUES (
                :equipment_id, :reading_on, :load_kw, :rated_kw, :ambient_c, :oil_temp_c
            )
            """,
            load_rows,
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed asset health database")
    parser.add_argument("--from-csv", action="store_true", help="Load from data/raw CSVs")
    parser.add_argument("--dtr", type=int, default=180)
    parser.add_argument("--feeder", type=int, default=60)
    args = parser.parse_args()

    if args.from_csv:
        tables = load_from_csv()
        print(f"Loaded CSVs from {RAW_DIR}")
    else:
        tables = generate_synthetic(n_dtr=args.dtr, n_feeder=args.feeder)
        export_raw(tables)
        print(f"Generated synthetic data -> {RAW_DIR}")

    ingest(tables)
    print(
        f"Ingested {len(tables['assets'])} assets, "
        f"{len(tables['notifications'])} notifications, "
        f"{len(tables['work_orders'])} work orders, "
        f"{len(tables['load_readings'])} load readings"
    )

    from .train import train_and_save
    from .score import score_all

    metrics = train_and_save()
    scored = score_all()
    print(f"Model AUC={metrics.get('roc_auc', 'n/a')} | Scored {scored} assets")


if __name__ == "__main__":
    main()
