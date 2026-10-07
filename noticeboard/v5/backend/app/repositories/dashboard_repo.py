from datetime import datetime

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from app.models import Cohort, Milestone, Notice, NoticeRead, Submission, User
from app.repositories import milestone_repo


def get_stats(db: Session, now: datetime) -> dict:
    """Manager dashboard numbers, computed in three aggregate queries."""
    # Active trainees: assigned to a cohort that has already started.
    active = (
        select(User.id, User.cohort_id, Cohort.start_date)
        .join(Cohort, Cohort.id == User.cohort_id)
        .where(User.role == "trainee", Cohort.start_date <= now.date())
        .subquery("active")
    )

    # Each trainee's newest submission of any kind: number them newest-first per trainee, keep row 1.
    ranked = select(
        Submission.trainee_id,
        Submission.status,
        Submission.submitted_at,
        func.row_number()
        .over(partition_by=Submission.trainee_id, order_by=Submission.submitted_at.desc())
        .label("rn"),
    ).subquery("ranked")
    latest = select(ranked).where(ranked.c.rn == 1).subquery("latest")

    total_active, at_risk = db.execute(
        select(func.count(), func.count().filter(latest.c.status == "stalled"))
        .select_from(active)
        .outerjoin(latest, latest.c.trainee_id == active.c.id)
    ).one()

    # Overdue: every (active trainee, milestone in their cohort) pair whose deadline has passed with no
    # report. Same rule as the cohort matrix and nudges (milestone_repo.overdue_condition).
    reports = milestone_repo.latest_reports()
    overdue = db.scalar(
        select(func.count())
        .select_from(active)
        .join(Milestone, Milestone.cohort_id == active.c.cohort_id)
        .outerjoin(reports, and_(reports.c.trainee_id == active.c.id, reports.c.milestone_id == Milestone.id))
        .where(milestone_repo.overdue_condition(reports, now))
    )

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
