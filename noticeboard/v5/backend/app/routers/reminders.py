from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, status

from app.auth import Manager, Trainee
from app.db import DB
from app.lookups import get_trainee_or_404
from app.repositories import audit_repo, milestone_repo, reminder_repo
from app.schemas import MyReminder, Reminder, ReminderCreate

router = APIRouter(prefix="/api/reminders", tags=["Reminders"])


@router.post("", response_model=Reminder, status_code=status.HTTP_201_CREATED)
def nudge_trainee(payload: ReminderCreate, db: DB, user: Manager):
    """Remind one trainee about one overdue task. Managers only.

    Only overdue tasks (deadline passed, nothing submitted) can be nudged, and only once until the
    trainee dismisses the reminder or submits the task.
    """
    now = datetime.now(UTC)
    trainee = get_trainee_or_404(db, payload.trainee_id)
    state = next(
        (s for s in milestone_repo.task_states(db, now=now, trainee_id=trainee.id) if s.milestone.id == payload.milestone_id),
        None,
    )
    if state is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "That milestone isn't assigned to this trainee")
    if not state.overdue:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, f"Only overdue tasks can be nudged; this one is {state.status.replace('_', ' ')}"
        )
    if reminder_repo.active_for(db, trainee_id=trainee.id, milestone_id=payload.milestone_id) is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Already nudged; the trainee hasn't cleared that reminder yet")

    reminder = reminder_repo.create(
        db, trainee_id=trainee.id, milestone_id=payload.milestone_id, sent_by=user.id, created_at=now
    )
    audit_repo.record(
        db,
        actor=user,
        action="reminder.sent",
        target_type="reminder",
        target_id=reminder.id,
        summary=f"Nudged {trainee.name} about overdue {state.milestone.title}",
        at=now,
    )
    db.commit()
    return reminder


@router.get("/mine", response_model=list[MyReminder])
def list_my_reminders(db: DB, user: Trainee):
    """The current trainee's unread reminders, newest first."""
    return [
        MyReminder(
            **Reminder.model_validate(reminder).model_dump(),
            milestone_title=milestone.title,
            due_date=milestone.due_date,
            sender_name=sender_name,
        )
        for reminder, milestone, sender_name in reminder_repo.list_active_for_trainee(db, user.id)
    ]


@router.post("/{reminder_id}/dismiss", response_model=Reminder)
def dismiss_reminder(reminder_id: str, db: DB, user: Trainee):
    """Hide one of your reminders. Idempotent. (Submitting the task clears its reminders too.)"""
    reminder = reminder_repo.get(db, reminder_id)
    if reminder is None or reminder.trainee_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Reminder '{reminder_id}' not found")
    if reminder.dismissed_at is None:
        reminder_repo.dismiss(db, reminder, datetime.now(UTC))
        db.commit()
    return reminder
