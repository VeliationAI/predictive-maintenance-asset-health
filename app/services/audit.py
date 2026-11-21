from __future__ import annotations

from sqlalchemy.orm import Session

from app.db.models import AuditLog


def write_audit(
    db: Session,
    *,
    action: str,
    organization_id: int | None = None,
    user_id: int | None = None,
    resource: str | None = None,
    detail: str | None = None,
    ip_address: str | None = None,
) -> None:
    db.add(
        AuditLog(
            organization_id=organization_id,
            user_id=user_id,
            action=action,
            resource=resource,
            detail=detail,
            ip_address=ip_address,
        )
    )
    db.commit()
