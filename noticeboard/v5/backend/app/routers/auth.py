from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm

from app.auth import CurrentUser
from app.db import DB
from app.repositories import cohort_repo, user_repo
from app.schemas import LoginRequest, SignupRequest, SwitchOption, TokenResponse, User
from app.security import create_access_token, hash_password, verify_password

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


@router.post("/auth/signup", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def signup(payload: SignupRequest, db: DB):
    """Create a trainee account and log straight in. Public.

    The role is always "trainee": SignupRequest has no role field, so nobody can sign themselves up
    as a manager. Managers are created by seed.py.
    """
    if payload.cohort_id is not None:
        cohort = cohort_repo.get(db, payload.cohort_id)
        # Same error for unknown and closed cohorts, so the response doesn't reveal private ones.
        if cohort is None or not cohort.open_for_signup:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Cohort '{payload.cohort_id}' is not open for sign-up")
    if user_repo.get_by_email(db, payload.email) is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "An account with this email already exists")

    user = user_repo.create(
        db,
        name=payload.name,
        email=payload.email,
        role="trainee",
        cohort_id=payload.cohort_id,
        hashed_password=hash_password(payload.password),
    )
    db.commit()
    return {"access_token": create_access_token(user), "token_type": "bearer", "user": user}


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
def list_switch_options(db: DB, user: CurrentUser):
    """Accounts for the navbar's "Switch user" picker, a testing convenience. Logged-in users only
    (v3 made this public for the old account-picker login screen). Switching still needs the
    target account's password.
    """
    return user_repo.list_switch_options(db)
