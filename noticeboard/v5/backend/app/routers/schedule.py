from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import AwareDatetime

from app.auth import Manager, Trainee
from app.db import DB
from app.lookups import get_cohort_or_404
from app.repositories import audit_repo, milestone_repo, schedule_repo
from app.schemas import ScheduleBlock, ScheduleBlockCreate

router = APIRouter(prefix="/api/schedule", tags=["Schedule"])

MAX_RANGE = timedelta(days=62)  # about two months: enough for a month view, small enough to stay cheap

START = Query(description="Range start, ISO timestamp with timezone, e.g. 2026-10-01T00:00:00Z")
END = Query(description="Range end (exclusive). At most 62 days after start.")


def check_range(start: AwareDatetime, end: AwareDatetime) -> None:
    if not start < end <= start + MAX_RANGE:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "end must be after start, and at most 62 days later")


@router.post("", response_model=ScheduleBlock, status_code=status.HTTP_201_CREATED)
def create_block(payload: ScheduleBlockCreate, db: DB, user: Manager):
    """Schedule a session (lecture, lab, office hours...) for a cohort. Managers only."""
    cohort = get_cohort_or_404(db, payload.cohort_id)
    if payload.milestone_id is not None:
        milestone = milestone_repo.get(db, payload.milestone_id)
        if milestone is None or milestone.cohort_id != payload.cohort_id:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "That milestone isn't assigned to this cohort")
    block = schedule_repo.create(db, **payload.model_dump())
    audit_repo.record(
        db,
        actor=user,
        action="schedule.created",
        target_type="schedule_block",
        target_id=block.id,
        summary=f"Scheduled “{block.title}” for {cohort.name}",
        at=datetime.now(UTC),
    )
    db.commit()
    return block


@router.get("", response_model=list[ScheduleBlock])
def list_blocks(
    db: DB, user: Manager, cohort_id: str, start: AwareDatetime = START, end: AwareDatetime = END
):
    """A cohort's sessions overlapping [start, end). Managers only."""
    check_range(start, end)
    get_cohort_or_404(db, cohort_id)
    return schedule_repo.list_for_cohort(db, cohort_id=cohort_id, start=start, end=end)


@router.get("/mine", response_model=list[ScheduleBlock])
def list_my_blocks(db: DB, user: Trainee, start: AwareDatetime = START, end: AwareDatetime = END):
    """The current trainee's cohort sessions overlapping [start, end), for the agenda view."""
    check_range(start, end)
    if user.cohort_id is None:
        return []
    return schedule_repo.list_for_cohort(db, cohort_id=user.cohort_id, start=start, end=end)
