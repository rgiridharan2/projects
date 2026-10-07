from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AuditEvent, User
from app.repositories.ids import next_id


def record(
    db: Session,
    *,
    actor: User | None,
    action: str,
    target_type: str,
    target_id: str | None,
    summary: str,
    at: datetime,
) -> AuditEvent:
    """Add one entry to the activity log. Called inside the same transaction as the action itself,
    so the log can't say something happened that was rolled back."""
    event = AuditEvent(
        id=next_id(db, AuditEvent),
        actor_id=actor.id if actor else None,
        action=action,
        target_type=target_type,
        target_id=target_id,
        summary=summary,
        created_at=at,
    )
    db.add(event)
    db.flush()
    return event


def list_recent(db: Session, *, limit: int, before: datetime | None = None) -> list[tuple[AuditEvent, str | None]]:
    """(event, actor name or None for the system), newest first. Pass the last row's created_at as
    `before` to fetch the next page."""
    stmt = (
        select(AuditEvent, User.name)
        .outerjoin(User, User.id == AuditEvent.actor_id)
        .order_by(AuditEvent.created_at.desc(), AuditEvent.id.desc())
        .limit(limit)
    )
    if before is not None:
        stmt = stmt.where(AuditEvent.created_at < before)
    return list(db.execute(stmt).all())
