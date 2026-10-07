from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ScheduleBlock
from app.repositories.ids import next_id


def list_for_cohort(db: Session, *, cohort_id: str, start: datetime, end: datetime) -> list[ScheduleBlock]:
    """Blocks that overlap [start, end), earliest first. A block running across `start` is included."""
    stmt = (
        select(ScheduleBlock)
        .where(ScheduleBlock.cohort_id == cohort_id, ScheduleBlock.starts_at < end, ScheduleBlock.ends_at > start)
        .order_by(ScheduleBlock.starts_at, ScheduleBlock.ends_at)
    )
    return list(db.scalars(stmt))


def create(
    db: Session, *, cohort_id: str, milestone_id: str | None, title: str, starts_at: datetime, ends_at: datetime
) -> ScheduleBlock:
    block = ScheduleBlock(
        id=next_id(db, ScheduleBlock),
        cohort_id=cohort_id,
        milestone_id=milestone_id,
        title=title,
        starts_at=starts_at,
        ends_at=ends_at,
    )
    db.add(block)
    db.flush()
    return block
