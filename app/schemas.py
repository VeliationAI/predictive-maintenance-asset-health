from __future__ import annotations

from datetime import datetime
from typing import Any, List, Optional

from pydantic import BaseModel, EmailStr, Field

from app.db.models import Role


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in_minutes: int
    role: Role
    full_name: str
    organization: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class UserOut(BaseModel):
    id: int
    email: EmailStr
    full_name: str
    role: Role
    organization_id: int
    is_active: bool

    model_config = {"from_attributes": True}


class AssetOut(BaseModel):
    equipment_id: str
    asset_type: str
    name: str
    circle: str
    division: str
    feeder_code: Optional[str] = None
    capacity_kva: float
    install_year: int
    functional_location: str
    status: str
    risk_score: Optional[float] = None
    risk_band: Optional[str] = None
    predicted_failure_90d: Optional[bool] = None
    recommended_action: Optional[str] = None
    scored_at: Optional[datetime] = None


class AssetDetail(BaseModel):
    asset: dict[str, Any]
    notifications: List[dict[str, Any]]
    work_orders: List[dict[str, Any]]
    load_readings: List[dict[str, Any]]


class SummaryOut(BaseModel):
    totals: dict[str, Any]
    by_circle: List[dict[str, Any]]
    model: dict[str, Any]
    organization: str


class PaginatedAssets(BaseModel):
    items: List[AssetOut]
    total: int
    page: int
    page_size: int


class RetrainResponse(BaseModel):
    scored: int
    roc_auc: Optional[float] = None
    accuracy: Optional[float] = None
    model_version: str
    feature_importance: List[dict[str, Any]] = Field(default_factory=list)


class ImportJobOut(BaseModel):
    id: int
    status: str
    message: Optional[str] = None
    rows_loaded: int
    created_at: datetime
    finished_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class AuditOut(BaseModel):
    id: int
    action: str
    resource: Optional[str]
    detail: Optional[str]
    created_at: datetime
    user_id: Optional[int]

    model_config = {"from_attributes": True}


class HealthOut(BaseModel):
    status: str
    version: str
    env: str
    database: str
