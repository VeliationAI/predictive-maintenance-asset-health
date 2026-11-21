from __future__ import annotations

from typing import Callable, Iterable

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session, joinedload

from app.core.security import AuthError, parse_token
from app.db.models import Role, User
from app.db.session import get_db

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)


def get_current_user(
    request: Request,
    token: str | None = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    try:
        payload = parse_token(token)
    except AuthError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc

    user_id = payload.get("uid")
    user = None
    if user_id:
        from sqlalchemy import select

        user = db.scalar(
            select(User).options(joinedload(User.organization)).where(User.id == user_id)
        )
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User inactive or missing")
    request.state.user_id = user.id
    request.state.org_id = user.organization_id
    return user


def require_roles(*roles: Role) -> Callable:
    allowed: Iterable[Role] = roles

    def _checker(user: User = Depends(get_current_user)) -> User:
        if user.role not in allowed and user.role != Role.admin:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient role")
        return user

    return _checker
