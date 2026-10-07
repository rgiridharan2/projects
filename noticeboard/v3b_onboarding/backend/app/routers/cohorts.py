from fastapi import APIRouter, HTTPException, status

from app.auth import CurrentUser, Manager, Trainee
from app.db import DB
from app.lookups import get_cohort_or_404
from app.repositories import cohort_repo, user_repo
from app.schemas import Cohort, CohortCreate, CohortSummary, MyCohort, PublicCohort, TraineeCreate, User
from app.security import hash_password

router = APIRouter(prefix="/api", tags=["Cohorts & Trainees"])


@router.get("/cohorts", response_model=list[CohortSummary])
def list_cohorts(db: DB, user: CurrentUser):
    """List all cohorts with how many trainees each one has. Any logged-in user."""
    return [
        CohortSummary(**Cohort.model_validate(cohort).model_dump(), trainee_count=count)
        for cohort, count in cohort_repo.list_with_trainee_counts(db)
    ]


@router.get("/cohorts/public-list", response_model=list[PublicCohort])
def list_public_cohorts(db: DB):
    """Cohorts that accept sign-ups, for the registration dropdown. Public."""
    return cohort_repo.list_open_for_signup(db)


@router.get("/cohorts/mine", response_model=MyCohort)
def read_my_cohort(db: DB, user: Trainee):
    """The current trainee's cohort and the other trainees in it."""
    if user.cohort_id is None:
        return {"cohort": None, "peers": []}
    return {
        "cohort": cohort_repo.get(db, user.cohort_id),
        "peers": user_repo.list_peers(db, cohort_id=user.cohort_id, exclude_id=user.id),
    }


@router.post("/cohorts", response_model=Cohort, status_code=status.HTTP_201_CREATED)
def create_cohort(payload: CohortCreate, db: DB, user: Manager):
    """Create a cohort. Managers only. Set `open_for_signup: false` to keep it out of public sign-up."""
    cohort = cohort_repo.create(db, **payload.model_dump())
    db.commit()
    return cohort


@router.get("/cohorts/{cohort_id}/trainees", response_model=list[User])
def list_cohort_trainees(cohort_id: str, db: DB, user: Manager):
    """Roster of trainees in one cohort, by name. Managers only."""
    get_cohort_or_404(db, cohort_id)
    return user_repo.list_trainees(db, cohort_id)


@router.post("/trainees", response_model=User, status_code=status.HTTP_201_CREATED)
def create_trainee(payload: TraineeCreate, db: DB, user: Manager):
    """Onboard a trainee with an initial password. Managers only. Emails are unique (case-insensitive)."""
    get_cohort_or_404(db, payload.cohort_id)
    if user_repo.get_by_email(db, payload.email) is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, f"A user with email '{payload.email.lower()}' already exists")

    trainee = user_repo.create(
        db,
        name=payload.name,
        email=payload.email,
        role="trainee",
        cohort_id=payload.cohort_id,
        hashed_password=hash_password(payload.initial_password),
    )
    db.commit()
    return trainee
