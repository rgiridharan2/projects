from datetime import datetime, timedelta

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from app.models import Cohort, Notice, NoticeRead, Submission, User

OVERDUE_AFTER = timedelta(days=7)


def get_stats(db: Session, now: datetime) -> dict:
    """Manager dashboard numbers, computed in two aggregate queries."""
    cutoff = now - OVERDUE_AFTER

    # Active trainees: assigned to a cohort that has already started.
    active = (
        select(User.id, User.cohort_id, Cohort.start_date)
        .join(Cohort, Cohort.id == User.cohort_id)
        .where(User.role == "trainee", Cohort.start_date <= now.date())
        .subquery("active")
    )

    # Each trainee's newest submission: number them newest-first per trainee, keep row 1.
    ranked = select(
        Submission.trainee_id,
        Submission.status,
        Submission.submitted_at,
        func.row_number()
        .over(partition_by=Submission.trainee_id, order_by=Submission.submitted_at.desc())
        .label("rn"),
    ).subquery("ranked")
    latest = select(ranked).where(ranked.c.rn == 1).subquery("latest")

    # Overdue: last report is older than the cutoff, or no report yet and the cohort is past its first week.
    is_overdue = or_(
        latest.c.submitted_at < cutoff,
        and_(latest.c.submitted_at.is_(None), active.c.start_date < cutoff.date()),
    )
    total_active, at_risk, overdue = db.execute(
        select(
            func.count(),
            func.count().filter(latest.c.status == "stalled"),
            func.count().filter(is_overdue),
        )
        .select_from(active)
        .outerjoin(latest, latest.c.trainee_id == active.c.id)
    ).one()

    # Read rate: every (notice, active trainee) pair the notice was meant for, and how many have a receipt.
    deliveries = (
        select(Notice.id.label("notice_id"), active.c.id.label("trainee_id"))
        .select_from(Notice)
        .join(active, or_(Notice.target_cohort_id.is_(None), Notice.target_cohort_id == active.c.cohort_id))
        .subquery("deliveries")
    )
    delivered, read = db.execute(
        select(func.count(), func.count(NoticeRead.read_at))
        .select_from(deliveries)
        .outerjoin(
            NoticeRead,
            and_(NoticeRead.notice_id == deliveries.c.notice_id, NoticeRead.trainee_id == deliveries.c.trainee_id),
        )
    ).one()

    return {
        "total_active": total_active,
        "at_risk": at_risk,
        "overdue_submissions": overdue,
        "read_rates": round(read / delivered, 2) if delivered else 0.0,
    }
