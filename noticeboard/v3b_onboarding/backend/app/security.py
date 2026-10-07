"""Password hashing and JWT helpers. No FastAPI imports here: see app/auth.py for the dependencies."""

from datetime import UTC, datetime, timedelta

import jwt
from passlib.context import CryptContext

from app.config import settings
from app.models import User

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto", bcrypt__rounds=settings.bcrypt_rounds)


def hash_password(password: str) -> str:
    """bcrypt hash with a random salt, e.g. '$2b$12$...'. The same password hashes differently each time."""
    return pwd_context.hash(password)


def verify_password(password: str, user: User | None) -> bool:
    """True only if the user exists, has a password, and it matches.

    When there's no user (or no hash) we still run a dummy bcrypt check, so a wrong email takes
    as long as a wrong password and response times don't reveal which accounts exist.
    """
    if user is None or user.hashed_password is None:
        pwd_context.dummy_verify()
        return False
    return pwd_context.verify(password, user.hashed_password)


def create_access_token(user: User) -> str:
    now = datetime.now(UTC)
    claims = {
        "sub": user.id,
        "role": user.role,
        "cohort_id": user.cohort_id,
        "iat": now,
        "exp": now + timedelta(minutes=settings.access_token_minutes),
    }
    return jwt.encode(claims, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict:
    """Return the claims, or raise jwt.InvalidTokenError (bad signature, expired, malformed...)."""
    return jwt.decode(
        token, settings.jwt_secret, algorithms=[settings.jwt_algorithm], options={"require": ["sub", "exp"]}
    )
