from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm

from app.auth import CurrentUser
from app.db import DB
from app.repositories import user_repo
from app.schemas import LoginRequest, SwitchOption, TokenResponse, User
from app.security import create_access_token, verify_password

router = APIRouter(prefix="/api", tags=["Auth"])


def issue_token(db: DB, identifier: str, password: str) -> dict:
    user = user_repo.get_by_identifier(db, identifier)
    if not verify_password(password, user):
        # Same message whether the account or the password is wrong, so it doesn't reveal which accounts exist.
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, "Incorrect email/ID or password", headers={"WWW-Authenticate": "Bearer"}
        )
    return {"access_token": create_access_token(user), "token_type": "bearer", "user": user}


@router.post("/auth/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: DB):
    """Log in with an email or user id. Returns a JWT to send as `Authorization: Bearer <token>`."""
    return issue_token(db, payload.identifier, payload.password)


@router.post("/auth/token", response_model=TokenResponse)
def login_form(form: Annotated[OAuth2PasswordRequestForm, Depends()], db: DB):
    """Same as /auth/login, but takes form fields. Swagger's **Authorize** button calls this:
    put an email or user id in `username`."""
    return issue_token(db, form.username, form.password)


@router.get("/auth/me", response_model=User)
def read_current_user(user: CurrentUser):
    """Who the current token belongs to. The frontend uses it to check a saved token is still valid."""
    return user


@router.get("/users/switch-options", response_model=list[SwitchOption])
def list_switch_options(db: DB):
    """Accounts to show in the "Switch user" picker. Public, so the login screen can list them too.

    A real deployment wouldn't publish its user list; this is a demo convenience. Picking an account
    still requires that account's password.
    """
    return user_repo.list_switch_options(db)
