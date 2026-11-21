from __future__ import annotations

from datetime import datetime, timedelta

import pandas as pd
from sqlalchemy import text
from sqlalchemy.orm import Session

FEATURE_COLUMNS = [
    "age_years",
    "capacity_kva",
    "is_dtr",
    "avg_load_factor_30d",
    "peak_load_factor_30d",
    "overload_days_30d",
    "load_volatility_30d",
    "avg_oil_temp_30d",
    "breakdown_count_90d",
    "corrective_count_90d",
    "preventive_count_180d",
    "downtime_hours_90d",
    "days_since_last_pm",
    "days_since_last_breakdown",
    "work_order_cost_180d",
    "repeat_damage_flag",
]


def reference_date() -> datetime:
    return datetime(2026, 11, 20)


def build_feature_frame(
    db: Session,
    organization_id: int,
    as_of: datetime | None = None,
    *,
    with_future_label: bool = False,
    label_horizon_days: int = 90,
) -> pd.DataFrame:
    as_of = as_of or reference_date()
    cutoff_30 = (as_of - timedelta(days=30)).strftime("%Y-%m-%d")
    cutoff_90 = (as_of - timedelta(days=90)).strftime("%Y-%m-%d")
    cutoff_180 = (as_of - timedelta(days=180)).strftime("%Y-%m-%d")
    as_of_s = as_of.strftime("%Y-%m-%d")
    future_end = (as_of + timedelta(days=label_horizon_days)).strftime("%Y-%m-%d")

    assets = pd.read_sql(
        text(
            """
            SELECT id AS asset_id, equipment_id, asset_type, name, circle, division, feeder_code,
                   capacity_kva, install_year, manufacturer, status, functional_location
            FROM assets WHERE organization_id = :org
            """
        ),
        db.bind,
        params={"org": organization_id},
    )
    if assets.empty:
        return pd.DataFrame(columns=["equipment_id", "label_failure_90d", *FEATURE_COLUMNS])

    loads = pd.read_sql(
        text(
            """
            SELECT equipment_id, reading_on, load_kw, rated_kw, ambient_c, oil_temp_c
            FROM load_readings
            WHERE organization_id = :org AND reading_on >= :start AND reading_on <= :end
            """
        ),
        db.bind,
        params={"org": organization_id, "start": cutoff_180, "end": as_of_s},
    )
    notifs = pd.read_sql(
        text(
            """
            SELECT equipment_id, created_on, notification_type, damage_code, downtime_hours
            FROM notifications
            WHERE organization_id = :org AND created_on <= :end
            """
        ),
        db.bind,
        params={"org": organization_id, "end": future_end if with_future_label else as_of_s},
    )
    orders = pd.read_sql(
        text(
            """
            SELECT equipment_id, created_on, order_type, cost_inr
            FROM work_orders
            WHERE organization_id = :org AND created_on <= :end
            """
        ),
        db.bind,
        params={"org": organization_id, "end": as_of_s},
    )

    if not loads.empty:
        loads["load_factor"] = loads["load_kw"] / loads["rated_kw"].clip(lower=1)
        recent = loads[loads["reading_on"] >= cutoff_30]
        load_agg = recent.groupby("equipment_id").agg(
            avg_load_factor_30d=("load_factor", "mean"),
            peak_load_factor_30d=("load_factor", "max"),
            overload_days_30d=("load_factor", lambda s: int((s >= 1.0).sum())),
            load_volatility_30d=("load_factor", "std"),
            avg_oil_temp_30d=("oil_temp_c", "mean"),
        ).reset_index()
    else:
        load_agg = pd.DataFrame(columns=["equipment_id"])

    hist = notifs[notifs["created_on"] <= as_of_s] if not notifs.empty else notifs
    n90 = hist[hist["created_on"] >= cutoff_90] if not hist.empty else hist

    def grouped_size(df: pd.DataFrame, mask, name: str) -> pd.Series:
        if df.empty:
            return pd.Series(dtype=int, name=name)
        subset = df[mask] if mask is not None else df
        return subset.groupby("equipment_id").size().rename(name)

    breakdown = grouped_size(n90, n90["notification_type"] == "M1" if not n90.empty else None, "breakdown_count_90d")
    corrective = grouped_size(
        n90,
        n90["notification_type"].isin(["M1", "M2"]) if not n90.empty else None,
        "corrective_count_90d",
    )
    downtime = (
        n90.groupby("equipment_id")["downtime_hours"].sum().rename("downtime_hours_90d")
        if not n90.empty
        else pd.Series(dtype=float, name="downtime_hours_90d")
    )
    damage_mode = (
        n90.groupby("equipment_id")["damage_code"]
        .agg(lambda s: int(s.value_counts().iloc[0] >= 2) if len(s) else 0)
        .rename("repeat_damage_flag")
        if not n90.empty
        else pd.Series(dtype=int, name="repeat_damage_flag")
    )
    last_bd = (
        hist[hist["notification_type"] == "M1"].groupby("equipment_id")["created_on"].max().rename("last_breakdown_on")
        if not hist.empty
        else pd.Series(dtype=str, name="last_breakdown_on")
    )

    prev = orders[(orders["order_type"] == "PM02") & (orders["created_on"] >= cutoff_180)] if not orders.empty else orders
    preventive = grouped_size(prev, None, "preventive_count_180d")
    last_pm = prev.groupby("equipment_id")["created_on"].max().rename("last_pm_on") if not prev.empty else pd.Series(dtype=str, name="last_pm_on")
    cost = orders.groupby("equipment_id")["cost_inr"].sum().rename("work_order_cost_180d") if not orders.empty else pd.Series(dtype=float, name="work_order_cost_180d")

    if with_future_label and not notifs.empty:
        future = notifs[
            (notifs["created_on"] > as_of_s)
            & (notifs["created_on"] <= future_end)
            & (notifs["notification_type"] == "M1")
        ]
        label = future.groupby("equipment_id").size().gt(0).astype(int).rename("label_failure_90d")
    else:
        label = pd.Series(dtype=int, name="label_failure_90d")

    frame = assets.merge(load_agg, on="equipment_id", how="left")
    for series in [breakdown, corrective, downtime, damage_mode, preventive, cost, last_bd, last_pm, label]:
        if isinstance(series, pd.Series) and series.name:
            frame = frame.merge(series, left_on="equipment_id", right_index=True, how="left")

    frame["age_years"] = as_of.year - frame["install_year"]
    frame["is_dtr"] = (frame["asset_type"] == "DTR").astype(int)
    if "label_failure_90d" not in frame.columns:
        frame["label_failure_90d"] = 0
    frame["label_failure_90d"] = frame["label_failure_90d"].fillna(0).astype(int)

    def days_since(col: str) -> pd.Series:
        if col not in frame.columns:
            return pd.Series([365] * len(frame))
        parsed = pd.to_datetime(frame[col], errors="coerce")
        return (as_of - parsed).dt.days.fillna(365)

    frame["days_since_last_pm"] = days_since("last_pm_on")
    frame["days_since_last_breakdown"] = days_since("last_breakdown_on")
    for col in FEATURE_COLUMNS:
        if col not in frame.columns:
            frame[col] = 0
        frame[col] = pd.to_numeric(frame[col], errors="coerce").fillna(0)
    return frame


def recommend_action(row: pd.Series, risk_score: float) -> str:
    if risk_score >= 0.70:
        if row["overload_days_30d"] >= 5:
            return "Urgent: inspect for overload damage; consider load balancing or capacity upgrade"
        if row["breakdown_count_90d"] >= 2:
            return "Urgent: open SAP PM work order for root-cause repair; schedule outage window"
        return "Urgent: field inspection within 7 days; verify oil/insulation and protection settings"
    if risk_score >= 0.45:
        if row["days_since_last_pm"] > 120:
            return "Plan preventive maintenance this month; check hotspots and bushings"
        if row["peak_load_factor_30d"] >= 1.05:
            return "Monitor peak loading; redistribute feeder load before summer"
        return "Schedule condition assessment; review last notifications in SAP PM"
    if risk_score >= 0.25:
        return "Continue routine PM cycle; watch load factor trend next 30 days"
    return "Healthy — keep on standard inspection interval"
