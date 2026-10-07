"""Fetch-or-404 helpers shared by the routers.

Relationship rules are checked here, in Python, before anything is written. A missing cohort
or trainee gives a clear 404 instead of a foreign-key error from Postgres.
"""

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models import Cohort, User
from app.repositories import cohort_repo, user_repo


def get_cohort_or_404(db: Session, cohort_id: str) -> Cohort:
    cohort = cohort_repo.get(db, cohort_id)
    if cohort is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Cohort '{cohort_id}' not found")
    return cohort


def get_trainee_or_404(db: Session, trainee_id: str) -> User:
    user = user_repo.get(db, trainee_id)
    if user is None or user.role != "trainee":
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Trainee '{trainee_id}' not found")
    return user
