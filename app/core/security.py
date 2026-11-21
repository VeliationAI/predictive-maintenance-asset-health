from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from jose import JWTError, jwt
from passlib.context import CryptContext

from .config import get_settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def create_access_token(subject: str, claims: Optional[dict[str, Any]] = None) -> str:
    settings = get_settings()
    payload: dict[str, Any] = {"sub": subject, "iat": datetime.now(timezone.utc)}
    if claims:
        payload.update(claims)
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.access_token_expire_minutes)
    payload["exp"] = expire
    return jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)


def decode_token(token: str) -> dict[str, Any]:
    settings = get_settings()
    return jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])


class AuthError(Exception):
    pass


def parse_token(token: str) -> dict[str, Any]:
    try:
        return decode_token(token)
    except JWTError as exc:
        raise AuthError("Invalid or expired token") from exc
