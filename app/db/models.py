from __future__ import annotations

import enum
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class Role(str, enum.Enum):
    admin = "admin"
    analyst = "analyst"
    planner = "planner"
    viewer = "viewer"


class JobStatus(str, enum.Enum):
    pending = "pending"
    running = "running"
    succeeded = "succeeded"
    failed = "failed"


class Organization(Base):
    __tablename__ = "organizations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200), unique=True, nullable=False)
    code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    region: Mapped[str] = mapped_column(String(100), default="Telangana")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    users: Mapped[list["User"]] = relationship(back_populates="organization")
    assets: Mapped[list["Asset"]] = relationship(back_populates="organization")


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    full_name: Mapped[str] = mapped_column(String(200), nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[Role] = mapped_column(Enum(Role), default=Role.viewer, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_login_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    organization: Mapped[Organization] = relationship(back_populates="users")


class Asset(Base):
    __tablename__ = "assets"
    __table_args__ = (UniqueConstraint("organization_id", "equipment_id", name="uq_org_equipment"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), index=True)
    equipment_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    asset_type: Mapped[str] = mapped_column(String(32), nullable=False)  # DTR | FEEDER
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    functional_location: Mapped[str] = mapped_column(String(255), nullable=False)
    circle: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    division: Mapped[str] = mapped_column(String(100), nullable=False)
    feeder_code: Mapped[Optional[str]] = mapped_column(String(64))
    capacity_kva: Mapped[float] = mapped_column(Float, default=0)
    install_year: Mapped[int] = mapped_column(Integer, default=2015)
    manufacturer: Mapped[Optional[str]] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(32), default="OPERATING")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    organization: Mapped[Organization] = relationship(back_populates="assets")
    risk_score: Mapped[Optional["RiskScore"]] = relationship(back_populates="asset", uselist=False)


class Notification(Base):
    __tablename__ = "notifications"
    __table_args__ = (UniqueConstraint("organization_id", "notification_id", name="uq_org_notif"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), index=True)
    notification_id: Mapped[str] = mapped_column(String(64), nullable=False)
    equipment_id: Mapped[str] = mapped_column(String(64), index=True)
    created_on: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    notification_type: Mapped[str] = mapped_column(String(8), nullable=False)
    short_text: Mapped[Optional[str]] = mapped_column(String(255))
    priority: Mapped[Optional[str]] = mapped_column(String(8))
    damage_code: Mapped[Optional[str]] = mapped_column(String(64))
    downtime_hours: Mapped[float] = mapped_column(Float, default=0)


class WorkOrder(Base):
    __tablename__ = "work_orders"
    __table_args__ = (UniqueConstraint("organization_id", "order_id", name="uq_org_order"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), index=True)
    order_id: Mapped[str] = mapped_column(String(64), nullable=False)
    equipment_id: Mapped[str] = mapped_column(String(64), index=True)
    notification_id: Mapped[Optional[str]] = mapped_column(String(64))
    created_on: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    completed_on: Mapped[Optional[str]] = mapped_column(String(32))
    order_type: Mapped[str] = mapped_column(String(16), nullable=False)
    work_center: Mapped[Optional[str]] = mapped_column(String(64))
    cost_inr: Mapped[float] = mapped_column(Float, default=0)
    description: Mapped[Optional[str]] = mapped_column(Text)


class LoadReading(Base):
    __tablename__ = "load_readings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), index=True)
    equipment_id: Mapped[str] = mapped_column(String(64), index=True)
    reading_on: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    load_kw: Mapped[float] = mapped_column(Float, nullable=False)
    rated_kw: Mapped[float] = mapped_column(Float, nullable=False)
    ambient_c: Mapped[Optional[float]] = mapped_column(Float)
    oil_temp_c: Mapped[Optional[float]] = mapped_column(Float)


class RiskScore(Base):
    __tablename__ = "risk_scores"
    __table_args__ = (UniqueConstraint("organization_id", "equipment_id", name="uq_org_risk"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), index=True)
    asset_id: Mapped[int] = mapped_column(ForeignKey("assets.id"), unique=True)
    equipment_id: Mapped[str] = mapped_column(String(64), index=True)
    risk_score: Mapped[float] = mapped_column(Float, nullable=False)
    risk_band: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    predicted_failure_90d: Mapped[bool] = mapped_column(Boolean, default=False)
    top_drivers: Mapped[Optional[str]] = mapped_column(Text)
    recommended_action: Mapped[Optional[str]] = mapped_column(Text)
    model_version: Mapped[str] = mapped_column(String(64), default="v2")
    scored_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    asset: Mapped[Asset] = relationship(back_populates="risk_score")


class ImportJob(Base):
    __tablename__ = "import_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), index=True)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    job_type: Mapped[str] = mapped_column(String(64), default="sap_pm_csv")
    status: Mapped[JobStatus] = mapped_column(Enum(JobStatus), default=JobStatus.pending)
    message: Mapped[Optional[str]] = mapped_column(Text)
    rows_loaded: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    organization_id: Mapped[Optional[int]] = mapped_column(ForeignKey("organizations.id"), index=True)
    user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"))
    action: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    resource: Mapped[Optional[str]] = mapped_column(String(100))
    detail: Mapped[Optional[str]] = mapped_column(Text)
    ip_address: Mapped[Optional[str]] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ModelRegistry(Base):
    __tablename__ = "model_registry"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), index=True)
    version: Mapped[str] = mapped_column(String(64), nullable=False)
    path: Mapped[str] = mapped_column(String(500), nullable=False)
    metrics_json: Mapped[Optional[str]] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_by: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
