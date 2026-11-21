"""Bootstrap org users (via app startup) and load demo fleet data."""

from __future__ import annotations

import argparse

from app.db.models import Organization
from app.db.session import SessionLocal
from app.services.bootstrap import init_database
from app.services.ingest import seed_organization
from sqlalchemy import select


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--from-csv", action="store_true")
    args = parser.parse_args()
    init_database()
    db = SessionLocal()
    try:
        org = db.scalar(select(Organization).where(Organization.code == "TGSPDCL"))
        if not org:
            raise SystemExit("Organization missing after bootstrap")
        result = seed_organization(db, org.id, from_csv=args.from_csv)
        print(result["job_id"], result.get("scored"), result.get("metrics", {}).get("roc_auc"))
    finally:
        db.close()


if __name__ == "__main__":
    main()
