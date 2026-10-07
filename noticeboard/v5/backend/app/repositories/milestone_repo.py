from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from app.models import Milestone, Submission, User
from app.repositories.ids import next_id

# How one trainee's latest report for a milestone translates into that task's status.
# No report at all means "pending".
TASK_STATUS = {
    "on_track": "completed",  # a manager signed it off (or the trainee reported it done)
    "needs_review": "under_review",  # submitted, waiting for a manager
    "stalled": "in_progress",  # blocked or sent back: the trainee needs to continue
}


@dataclass
class TaskState:
    """One trainee's position on one milestone."""

    trainee_id: str
    milestone: Milestone
    status: str  # pending | in_progress | under_review | completed
    overdue: bool
    last_submitted_at: datetime | None


def latest_reports():
    """Subquery: each trainee's newest report per milestone (row 1 when numbered newest-first)."""
    ranked = (
        select(
            Submission.trainee_id,
            Submission.milestone_id,
            Submission.status,
            Submission.submitted_at,
            func.row_number()
            .over(
                partition_by=(Submission.trainee_id, Submission.milestone_id),
                order_by=Submission.submitted_at.desc(),
            )
            .label("rn"),
        )
        .where(Submission.milestone_id.is_not(None))
        .subquery("ranked")
    )
    return select(ranked).where(ranked.c.rn == 1).subquery("latest")


def overdue_condition(latest, now: datetime):
    """The one definition of "overdue", used by the task list, the cohort matrix, nudges and the
    dashboard: the deadline has passed and the trainee hasn't submitted anything for the task.
    (Stalled work counts as "at risk" instead.)"""
    return and_(latest.c.status.is_(None), Milestone.due_date < now)


def task_states(
    db: Session, *, now: datetime, cohort_id: str | None = None, trainee_id: str | None = None
) -> list[TaskState]:
    """Every (trainee, milestone in their cohort) pair, by trainee name then milestone order."""
    latest = latest_reports()
    stmt = (
        select(User.id, Milestone, latest.c.status, latest.c.submitted_at, overdue_condition(latest, now))
        .join(Milestone, Milestone.cohort_id == User.cohort_id)
        .outerjoin(latest, and_(latest.c.trainee_id == User.id, latest.c.milestone_id == Milestone.id))
        .where(User.role == "trainee")
        .order_by(User.name, User.id, Milestone.milestone_order)
    )
    if cohort_id is not None:
        stmt = stmt.where(User.cohort_id == cohort_id)
    if trainee_id is not None:
        stmt = stmt.where(User.id == trainee_id)
    return [
        TaskState(user_id, milestone, TASK_STATUS.get(report_status, "pending"), bool(overdue), submitted_at)
        for user_id, milestone, report_status, submitted_at, overdue in db.execute(stmt)
    ]


def get(db: Session, milestone_id: str) -> Milestone | None:
    return db.get(Milestone, milestone_id)


def list_for_cohort(db: Session, cohort_id: str | None) -> list[Milestone]:
    stmt = select(Milestone).order_by(Milestone.cohort_id, Milestone.milestone_order)
    if cohort_id is not None:
        stmt = stmt.where(Milestone.cohort_id == cohort_id)
    return list(db.scalars(stmt))


def next_order(db: Session, cohort_id: str) -> int:
    return (db.scalar(select(func.max(Milestone.milestone_order)).where(Milestone.cohort_id == cohort_id)) or 0) + 1


def order_taken(db: Session, cohort_id: str, milestone_order: int) -> bool:
    stmt = select(Milestone.id).where(Milestone.cohort_id == cohort_id, Milestone.milestone_order == milestone_order)
    return db.scalar(stmt) is not None


def create(
    db: Session, *, cohort_id: str, title: str, due_date: datetime, milestone_order: int | None = None
) -> Milestone:
    """Add a milestone; without an explicit order it goes to the end of the cohort's sequence."""
    milestone = Milestone(
        id=next_id(db, Milestone),
        cohort_id=cohort_id,
        milestone_order=milestone_order or next_order(db, cohort_id),
        title=title,
        due_date=due_date,
    )
    db.add(milestone)
    db.flush()
    return milestone
