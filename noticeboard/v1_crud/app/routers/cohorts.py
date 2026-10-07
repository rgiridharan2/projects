from collections import Counter

from fastapi import APIRouter, HTTPException, status

from app import data
from app.lookups import get_cohort_or_404
from app.schemas import CohortSummary, TraineeCreate, User

router = APIRouter(prefix="/api", tags=["Cohorts & Trainees"])


@router.get("/cohorts", response_model=list[CohortSummary])
def list_cohorts():
    """List all cohorts with how many trainees each one has."""
    counts = Counter(u["cohort_id"] for u in data.USERS.values() if u["role"] == "trainee")
    return [{**cohort, "trainee_count": counts[cohort["id"]]} for cohort in data.COHORTS.values()]


@router.get("/cohorts/{cohort_id}/trainees", response_model=list[User])
def list_cohort_trainees(cohort_id: str):
    """Roster of trainees in one cohort."""
    get_cohort_or_404(cohort_id)
    return [u for u in data.USERS.values() if u["role"] == "trainee" and u["cohort_id"] == cohort_id]


@router.post("/trainees", response_model=User, status_code=status.HTTP_201_CREATED)
def create_trainee(payload: TraineeCreate):
    """Add a trainee to a cohort. Emails are unique (case-insensitive) to block duplicate entries."""
    get_cohort_or_404(payload.cohort_id)
    email = payload.email.lower()
    if any(u["email"] == email for u in data.USERS.values()):
        raise HTTPException(status.HTTP_409_CONFLICT, f"A user with email '{email}' already exists")

    user = {
        "id": data.next_id("u", data.USERS),
        "name": payload.name,
        "email": email,
        "role": "trainee",
        "cohort_id": payload.cohort_id,
    }
    data.USERS[user["id"]] = user
    return user
