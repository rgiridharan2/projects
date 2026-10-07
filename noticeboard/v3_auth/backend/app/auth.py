"""Reusable FastAPI dependencies for authentication and authorization.

    user: CurrentUser   -> any logged-in user (401 without a valid token)
    user: Manager       -> managers only (403 for trainees)
    user: Trainee       -> trainees only (403 for managers)
"""

from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer

from app.db import DB
from app.models import User
from app.repositories import user_repo
from app.security import decode_access_token

# Reads "Authorization: Bearer <token>". tokenUrl wires up Swagger's Authorize button.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/token")


def get_current_user(db: DB, token: Annotated[str, Depends(oauth2_scheme)]) -> User:
    """Validate the JWT and load the user it names.

    The user is re-read from the database on every request rather than trusted from the token,
    so a deleted account or a changed role takes effect immediately.
    """
    unauthorized = HTTPException(
        status.HTTP_401_UNAUTHORIZED,
        "Invalid or expired token",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        user_id = decode_access_token(token)["sub"]
    except jwt.InvalidTokenError:
        raise unauthorized
    user = user_repo.get(db, user_id)
    if user is None:
        raise unauthorized
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_role(roles: list[str]):
    """Dependency factory: require_role(["manager"]) only lets managers through."""

    def check_role(user: CurrentUser) -> User:
        if user.role not in roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, f"Requires role: {' or '.join(roles)}")
        return user

    return check_role


Manager = Annotated[User, Depends(require_role(["manager"]))]
Trainee = Annotated[User, Depends(require_role(["trainee"]))]


def ensure_owner_or_manager(user: User, trainee_id: str) -> None:
    """Trainees may only act on their own records; managers may act on anyone's."""
    if user.role != "manager" and user.id != trainee_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Trainees can only manage their own submissions")
