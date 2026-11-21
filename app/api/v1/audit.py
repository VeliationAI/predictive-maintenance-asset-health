from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import require_roles
from app.db.models import AuditLog, Role, User
from app.db.session import get_db
from app.schemas import AuditOut

router = APIRouter()


@router.get("", response_model=list[AuditOut])
def list_audit(
    user: User = Depends(require_roles(Role.admin)),
    db: Session = Depends(get_db),
):
    rows = db.scalars(
        select(AuditLog)
        .where(AuditLog.organization_id == user.organization_id)
        .order_by(AuditLog.created_at.desc())
        .limit(100)
    ).all()
    return rows
