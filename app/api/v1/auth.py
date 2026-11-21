from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.api.deps import get_current_user
from app.core.config import get_settings
from app.core.security import create_access_token, verify_password
from app.db.models import User
from app.db.session import get_db
from app.schemas import LoginRequest, TokenResponse, UserOut
from app.services.audit import write_audit

router = APIRouter()


def _load_user(db: Session, email: str) -> User | None:
    return db.scalar(
        select(User).options(joinedload(User.organization)).where(User.email == email)
    )


def _issue_token(user: User, db: Session, request: Request) -> TokenResponse:
    settings = get_settings()
    token = create_access_token(
        subject=user.email,
        claims={"uid": user.id, "org": user.organization_id, "role": user.role.value},
    )
    user.last_login_at = datetime.now(timezone.utc)
    db.commit()
    write_audit(
        db,
        action="login",
        organization_id=user.organization_id,
        user_id=user.id,
        resource="auth",
        ip_address=request.client.host if request.client else None,
    )
    org_name = user.organization.name if user.organization else ""
    return TokenResponse(
        access_token=token,
        expires_in_minutes=settings.access_token_expire_minutes,
        role=user.role,
        full_name=user.full_name,
        organization=org_name,
    )


@router.post("/login", response_model=TokenResponse)
def login_form(
    request: Request,
    form: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    user = _load_user(db, form.username)
    if not user or not verify_password(form.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    if not user.is_active:
        raise HTTPException(status_code=400, detail="User disabled")
    return _issue_token(user, db, request)


@router.post("/token", response_model=TokenResponse)
def login_json(payload: LoginRequest, request: Request, db: Session = Depends(get_db)):
    user = _load_user(db, payload.email)
    if not user or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    return _issue_token(user, db, request)


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return user


@router.get("/demo-accounts")
def demo_accounts():
    settings = get_settings()
    if not settings.allow_demo_login:
        raise HTTPException(404, "Demo login disabled")
    return {
        "password": settings.default_admin_password,
        "accounts": [
            {"email": settings.default_admin_email, "role": "admin"},
            {"email": "planner@gridsense.example", "role": "planner"},
            {"email": "analyst@gridsense.example", "role": "analyst"},
            {"email": "viewer@gridsense.example", "role": "viewer"},
        ],
    }
