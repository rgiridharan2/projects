from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.orm import Session, aliased

from app.models import Milestone, Reminder, User
from app.repositories.ids import next_id


def get(db: Session, reminder_id: str) -> Reminder | None:
    return db.get(Reminder, reminder_id)


def active_for(db: Session, *, trainee_id: str, milestone_id: str) -> Reminder | None:
    """The trainee's unread reminder about this task, if there is one."""
    stmt = select(Reminder).where(
        Reminder.trainee_id == trainee_id, Reminder.milestone_id == milestone_id, Reminder.dismissed_at.is_(None)
    )
    return db.scalar(stmt)


def active_in_cohort(db: Session, cohort_id: str) -> dict[tuple[str, str], datetime]:
    """{(trainee_id, milestone_id): sent at} for every unread reminder in a cohort."""
    stmt = (
        select(Reminder.trainee_id, Reminder.milestone_id, Reminder.created_at)
        .join(Milestone, Milestone.id == Reminder.milestone_id)
        .where(Milestone.cohort_id == cohort_id, Reminder.dismissed_at.is_(None))
    )
    return {(trainee_id, milestone_id): at for trainee_id, milestone_id, at in db.execute(stmt)}


def list_active_for_trainee(db: Session, trainee_id: str) -> list[tuple[Reminder, Milestone, str]]:
    """(reminder, its milestone, the sender's name) for each unread reminder, newest first."""
    sender = aliased(User)
    stmt = (
        select(Reminder, Milestone, sender.name)
        .join(Milestone, Milestone.id == Reminder.milestone_id)
        .join(sender, sender.id == Reminder.sent_by)
        .where(Reminder.trainee_id == trainee_id, Reminder.dismissed_at.is_(None))
        .order_by(Reminder.created_at.desc())
    )
    return list(db.execute(stmt).all())


def create(db: Session, *, trainee_id: str, milestone_id: str, sent_by: str, created_at: datetime) -> Reminder:
    reminder = Reminder(
        id=next_id(db, Reminder),
        trainee_id=trainee_id,
        milestone_id=milestone_id,
        sent_by=sent_by,
        created_at=created_at,
    )
    db.add(reminder)
    db.flush()
    return reminder


def dismiss(db: Session, reminder: Reminder, at: datetime) -> Reminder:
    reminder.dismissed_at = at
    db.flush()
    return reminder


def dismiss_for_task(db: Session, *, trainee_id: str, milestone_id: str, at: datetime) -> None:
    """Clear any unread reminders about a task once the trainee submits it."""
    db.execute(
        update(Reminder)
        .where(Reminder.trainee_id == trainee_id, Reminder.milestone_id == milestone_id, Reminder.dismissed_at.is_(None))
        .values(dismissed_at=at)
    )
