from fastapi import APIRouter, Query, status

from app.auth import Manager, Trainee
from app.db import DB
from app.lookups import get_cohort_or_404
from app.repositories import milestone_repo
from app.schemas import Milestone, MilestoneCreate, MyMilestone

router = APIRouter(prefix="/api/milestones", tags=["Milestones"])


@router.post("", response_model=Milestone, status_code=status.HTTP_201_CREATED)
def create_milestone(payload: MilestoneCreate, db: DB, user: Manager):
    """Assign a task with a due date to everyone in a cohort. Managers only."""
    get_cohort_or_404(db, payload.cohort_id)
    milestone = milestone_repo.create(db, **payload.model_dump())
    db.commit()
    return milestone


@router.get("", response_model=list[Milestone])
def list_milestones(
    db: DB,
    user: Manager,
    cohort_id: str | None = Query(default=None, description="Only this cohort's milestones."),
):
    """Milestones by due date. Managers only (trainees use /mine)."""
    if cohort_id is not None:
        get_cohort_or_404(db, cohort_id)
    return milestone_repo.list_for_cohort(db, cohort_id)


@router.get("/mine", response_model=list[MyMilestone])
def list_my_milestones(db: DB, user: Trainee):
    """The current trainee's tasks, soonest due first, each with its status for them:
    `pending` (no report yet), `under_review`, `in_progress` (stalled or sent back) or `completed`."""
    if user.cohort_id is None:
        return []
    return [
        MyMilestone(**Milestone.model_validate(milestone).model_dump(), status=task_status, last_submitted_at=at)
        for milestone, task_status, at in milestone_repo.list_for_trainee(
            db, trainee_id=user.id, cohort_id=user.cohort_id
        )
    ]
