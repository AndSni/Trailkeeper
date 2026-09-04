"""Password hashing (bcrypt) and JWT access/refresh tokens (PyJWT)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import bcrypt
import jwt

from app.config import settings

# bcrypt hard-limits the password to 72 bytes; anything longer is silently
# truncated by some implementations and rejected by others. Truncate up front
# so behaviour is identical everywhere.
_BCRYPT_MAX_BYTES = 72


def _clamp(password: str) -> bytes:
    return password.encode("utf-8")[:_BCRYPT_MAX_BYTES]


def hash_password(password: str) -> str:
    return bcrypt.hashpw(_clamp(password), bcrypt.gensalt()).decode("ascii")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(_clamp(password), password_hash.encode("ascii"))
    except (ValueError, TypeError):
        return False


def _encode(sub: str, token_type: str, ttl: timedelta) -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": sub,
        "type": token_type,
        "iat": now,
        "exp": now + ttl,
        "jti": uuid.uuid4().hex,
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def create_access_token(user_id: uuid.UUID | str) -> str:
    return _encode(str(user_id), "access", timedelta(minutes=settings.access_token_ttl_minutes))


def create_refresh_token(user_id: uuid.UUID | str) -> str:
    return _encode(str(user_id), "refresh", timedelta(days=settings.refresh_token_ttl_days))


def decode_token(token: str, *, expected_type: str) -> dict:
    """Return the token payload, or raise jwt.InvalidTokenError."""
    payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    if payload.get("type") != expected_type:
        raise jwt.InvalidTokenError(f"expected a {expected_type} token")
    return payload
