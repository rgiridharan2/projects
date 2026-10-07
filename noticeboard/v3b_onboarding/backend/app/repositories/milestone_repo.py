from datetime import date, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Milestone, Submission
from app.repositories.ids import next_id

# How one trainee's latest report for a milestone translates into that task's status.
# No report at all means "pending".
TASK_STATUS = {
    "on_track": "completed",  # a manager signed it off (or the trainee reported it done)
    "needs_review": "under_review",  # submitted, waiting for a manager
    "stalled": "in_progress",  # blocked or sent back: the trainee needs to continue
}


def get(db: Session, milestone_id: str) -> Milestone | None:
    return db.get(Milestone, milestone_id)


def list_for_cohort(db: Session, cohort_id: str | None) -> list[Milestone]:
    stmt = select(Milestone).order_by(Milestone.due_date, Milestone.title)
    if cohort_id is not None:
        stmt = stmt.where(Milestone.cohort_id == cohort_id)
    return list(db.scalars(stmt))


def list_for_trainee(
    db: Session, *, trainee_id: str, cohort_id: str
) -> list[tuple[Milestone, str, datetime | None]]:
    """Every milestone in the trainee's cohort, soonest due first, with the task status and the
    time of their latest report for it."""
    # Number this trainee's reports newest-first per milestone; row 1 is the latest.
    ranked = (
        select(
            Submission.milestone_id,
            Submission.status,
            Submission.submitted_at,
            func.row_number()
            .over(partition_by=Submission.milestone_id, order_by=Submission.submitted_at.desc())
            .label("rn"),
        )
        .where(Submission.trainee_id == trainee_id, Submission.milestone_id.is_not(None))
        .subquery("ranked")
    )
    latest = select(ranked).where(ranked.c.rn == 1).subquery("latest")

    stmt = (
        select(Milestone, latest.c.status, latest.c.submitted_at)
        .outerjoin(latest, latest.c.milestone_id == Milestone.id)
        .where(Milestone.cohort_id == cohort_id)
        .order_by(Milestone.due_date, Milestone.title)
    )
    return [
        (milestone, TASK_STATUS.get(report_status, "pending"), submitted_at)
        for milestone, report_status, submitted_at in db.execute(stmt)
    ]


def create(db: Session, *, cohort_id: str, title: str, due_date: date) -> Milestone:
    milestone = Milestone(id=next_id(db, Milestone), cohort_id=cohort_id, title=title, due_date=due_date)
    db.add(milestone)
    db.flush()
    return milestone
