from __future__ import annotations

import logging

from sqlalchemy import select

from app.core.config import get_settings
from app.core.security import hash_password
from app.db.base import Base
from app.db.models import Organization, Role, User
from app.db.session import SessionLocal, engine

logger = logging.getLogger(__name__)


def init_database() -> None:
    Base.metadata.create_all(bind=engine)
    settings = get_settings()
    db = SessionLocal()
    try:
        org = db.scalar(select(Organization).where(Organization.code == "TGSPDCL"))
        if not org:
            org = Organization(
                name=settings.default_org_name,
                code="TGSPDCL",
                region="Telangana",
            )
            db.add(org)
            db.flush()
            logger.info("Created default organization %s", org.code)

        admin = db.scalar(select(User).where(User.email == settings.default_admin_email))
        if not admin:
            admin = User(
                organization_id=org.id,
                email=settings.default_admin_email,
                full_name="Platform Admin",
                hashed_password=hash_password(settings.default_admin_password),
                role=Role.admin,
                is_active=True,
            )
            db.add(admin)
            # Seed companion roles for demo
            for email, name, role in [
                ("planner@gridsense.example", "Maintenance Planner", Role.planner),
                ("analyst@gridsense.example", "Reliability Analyst", Role.analyst),
                ("viewer@gridsense.example", "Operations Viewer", Role.viewer),
            ]:
                if not db.scalar(select(User).where(User.email == email)):
                    db.add(
                        User(
                            organization_id=org.id,
                            email=email,
                            full_name=name,
                            hashed_password=hash_password(settings.default_admin_password),
                            role=role,
                            is_active=True,
                        )
                    )
            db.commit()
            logger.info("Seeded default users for org %s", org.code)
        else:
            db.commit()
    finally:
        db.close()
