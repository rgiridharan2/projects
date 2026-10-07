from datetime import datetime

from sqlalchemy import case, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models import Notice, NoticeRead
from app.repositories.ids import next_id


def get(db: Session, notice_id: str) -> Notice | None:
    return db.get(Notice, notice_id)


def list_for_cohort(db: Session, cohort_id: str | None) -> list[Notice]:
    """A cohort's notices plus global ones (or every notice if cohort_id is None), urgent first, then newest."""
    stmt = select(Notice)
    if cohort_id is not None:
        stmt = stmt.where(or_(Notice.target_cohort_id.is_(None), Notice.target_cohort_id == cohort_id))
    urgent_first = case((Notice.priority == "urgent", 0), else_=1)
    return list(db.scalars(stmt.order_by(urgent_first, Notice.created_at.desc())))


def create(
    db: Session, *, title: str, body: str, priority: str, target_cohort_id: str | None, created_at: datetime
) -> Notice:
    notice = Notice(
        id=next_id(db, Notice),
        title=title,
        body=body,
        priority=priority,
        target_cohort_id=target_cohort_id,
        created_at=created_at,
    )
    db.add(notice)
    db.flush()
    return notice


def mark_read(db: Session, *, notice_id: str, trainee_id: str, read_at: datetime) -> NoticeRead:
    """Record a read receipt once; later calls keep the original read_at.

    INSERT ... ON CONFLICT DO NOTHING makes this safe even if two requests arrive together.
    """
    db.execute(
        insert(NoticeRead)
        .values(notice_id=notice_id, trainee_id=trainee_id, read_at=read_at)
        .on_conflict_do_nothing(index_elements=["notice_id", "trainee_id"])
    )
    return db.get(NoticeRead, (notice_id, trainee_id))
