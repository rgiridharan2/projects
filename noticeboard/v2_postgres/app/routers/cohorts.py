from fastapi import APIRouter, HTTPException, status

from app.db import DB
from app.lookups import get_cohort_or_404
from app.repositories import cohort_repo, user_repo
from app.schemas import Cohort, CohortSummary, TraineeCreate, User

router = APIRouter(prefix="/api", tags=["Cohorts & Trainees"])


@router.get("/cohorts", response_model=list[CohortSummary])
def list_cohorts(db: DB):
    """List all cohorts with how many trainees each one has."""
    return [
        CohortSummary(**Cohort.model_validate(cohort).model_dump(), trainee_count=count)
        for cohort, count in cohort_repo.list_with_trainee_counts(db)
    ]


@router.get("/cohorts/{cohort_id}/trainees", response_model=list[User])
def list_cohort_trainees(cohort_id: str, db: DB):
    """Roster of trainees in one cohort, by name."""
    get_cohort_or_404(db, cohort_id)
    return user_repo.list_trainees(db, cohort_id)


@router.post("/trainees", response_model=User, status_code=status.HTTP_201_CREATED)
def create_trainee(payload: TraineeCreate, db: DB):
    """Add a trainee to a cohort. Emails are unique (case-insensitive) to block duplicate entries."""
    get_cohort_or_404(db, payload.cohort_id)
    if user_repo.get_by_email(db, payload.email) is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, f"A user with email '{payload.email.lower()}' already exists")

    user = user_repo.create(db, name=payload.name, email=payload.email, role="trainee", cohort_id=payload.cohort_id)
    db.commit()
    return user
