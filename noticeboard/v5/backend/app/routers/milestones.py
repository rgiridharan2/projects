from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Query, status

from app.auth import Manager, Trainee
from app.db import DB
from app.lookups import get_cohort_or_404
from app.repositories import audit_repo, milestone_repo
from app.schemas import Milestone, MilestoneCreate, MilestoneDispatch, MyMilestone

router = APIRouter(prefix="/api/milestones", tags=["Milestones"])


@router.post("", response_model=Milestone, status_code=status.HTTP_201_CREATED)
def create_milestone(payload: MilestoneCreate, db: DB, user: Manager):
    """Assign a task with a deadline to one cohort. Managers only.

    Omit `milestone_order` to add it after the cohort's last task.
    """
    cohort = get_cohort_or_404(db, payload.cohort_id)
    if payload.milestone_order is not None and milestone_repo.order_taken(
        db, payload.cohort_id, payload.milestone_order
    ):
        raise HTTPException(
            status.HTTP_409_CONFLICT, f"Cohort '{payload.cohort_id}' already has a task at position {payload.milestone_order}"
        )
    milestone = milestone_repo.create(db, **payload.model_dump())
    audit_repo.record(
        db,
        actor=user,
        action="milestone.dispatched",
        target_type="milestone",
        target_id=milestone.id,
        summary=f"Dispatched “{milestone.title}” to {cohort.name} as task #{milestone.milestone_order}",
        at=datetime.now(UTC),
    )
    db.commit()
    return milestone


@router.post("/dispatch", response_model=list[Milestone], status_code=status.HTTP_201_CREATED)
def dispatch_milestone(payload: MilestoneDispatch, db: DB, user: Manager):
    """Send one task to several cohorts at once, each with its own deadline. Managers only.

    All-or-nothing: if any cohort is unknown, nothing is created. Each copy goes to the end of
    that cohort's sequence.
    """
    names = [get_cohort_or_404(db, assignment.cohort_id).name for assignment in payload.assignments]
    created = [
        milestone_repo.create(db, cohort_id=a.cohort_id, title=payload.title, due_date=a.due_date)
        for a in payload.assignments
    ]
    audit_repo.record(
        db,
        actor=user,
        action="milestone.dispatched",
        target_type="milestone",
        target_id=created[0].id,
        summary=f"Dispatched “{payload.title}” to {len(created)} cohort{'s' if len(created) != 1 else ''}: {', '.join(names)}",
        at=datetime.now(UTC),
    )
    db.commit()
    return created


@router.get("", response_model=list[Milestone])
def list_milestones(
    db: DB,
    user: Manager,
    cohort_id: str | None = Query(default=None, description="Only this cohort's milestones."),
):
    """Milestones in sequence order. Managers only (trainees use /mine)."""
    if cohort_id is not None:
        get_cohort_or_404(db, cohort_id)
    return milestone_repo.list_for_cohort(db, cohort_id)


@router.get("/mine", response_model=list[MyMilestone])
def list_my_milestones(db: DB, user: Trainee):
    """The current trainee's tasks in sequence order, each with its status for them and whether it's
    overdue (deadline passed, nothing submitted)."""
    return [
        MyMilestone(
            **Milestone.model_validate(state.milestone).model_dump(),
            status=state.status,
            overdue=state.overdue,
            last_submitted_at=state.last_submitted_at,
        )
        for state in milestone_repo.task_states(db, now=datetime.now(UTC), trainee_id=user.id)
    ]
