from datetime import datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.models import Cohort, Escalation, Milestone, User
from app.repositories import milestone_repo
from app.repositories.ids import next_id

ESCALATE_AFTER = timedelta(hours=48)


def run_check(db: Session, now: datetime) -> list[Escalation]:
    """Flag every task that's overdue (nothing submitted) and more than 48 hours past its deadline,
    unless it was flagged before. Safe to run as often as you like."""
    already = {tuple(row) for row in db.execute(select(Escalation.trainee_id, Escalation.milestone_id))}
    created = []
    for state in milestone_repo.task_states(db, now=now):
        key = (state.trainee_id, state.milestone.id)
        if state.overdue and state.milestone.due_date < now - ESCALATE_AFTER and key not in already:
            escalation = Escalation(
                id=next_id(db, Escalation), trainee_id=key[0], milestone_id=key[1], escalated_at=now
            )
            db.add(escalation)
            created.append(escalation)
    db.flush()
    return created


def resolve_for_task(db: Session, *, trainee_id: str, milestone_id: str, at: datetime) -> None:
    """The trainee handed the task in, so the escalation is over."""
    db.execute(
        update(Escalation)
        .where(Escalation.trainee_id == trainee_id, Escalation.milestone_id == milestone_id, Escalation.resolved_at.is_(None))
        .values(resolved_at=at)
    )


def active_in_cohort(db: Session, cohort_id: str) -> set[tuple[str, str]]:
    stmt = (
        select(Escalation.trainee_id, Escalation.milestone_id)
        .join(Milestone, Milestone.id == Escalation.milestone_id)
        .where(Milestone.cohort_id == cohort_id, Escalation.resolved_at.is_(None))
    )
    return {tuple(row) for row in db.execute(stmt)}


def list_active(db: Session) -> list[tuple[Escalation, str, Milestone, str]]:
    """(escalation, trainee name, milestone, cohort name) for every unresolved flag, oldest deadline first."""
    stmt = (
        select(Escalation, User.name, Milestone, Cohort.name)
        .join(User, User.id == Escalation.trainee_id)
        .join(Milestone, Milestone.id == Escalation.milestone_id)
        .join(Cohort, Cohort.id == Milestone.cohort_id)
        .where(Escalation.resolved_at.is_(None))
        .order_by(Milestone.due_date, User.name)
    )
    return list(db.execute(stmt).all())
