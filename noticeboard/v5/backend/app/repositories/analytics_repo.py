"""Per-trainee performance numbers, and the cohort health score built from them.

The CSV report and the health score both come from trainee_metrics(), so a cohort's score can
always be re-derived from the rows in its exported report.
"""

from collections import Counter
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from app.models import Cohort, Milestone, Notice, NoticeRead, Submission, User
from app.repositories import milestone_repo

# Health score = 60% on-time submission rate + 40% notice read rate, as 0-100.
ON_TIME_WEIGHT, READ_WEIGHT = 0.6, 0.4
HEALTHY_FROM, WATCH_FROM = 75, 60  # below 60 the cohort is flagged "at_risk"


@dataclass
class TraineeMetrics:
    trainee_id: str
    name: str
    email: str
    cohort_id: str | None
    cohort_name: str | None
    tasks_due: int  # tasks whose deadline has passed
    on_time: int  # ...of which the first report came in at or before the deadline
    overdue: int  # ...of which nothing has been submitted (same rule as the matrix)
    completed: int
    under_review: int
    in_progress: int
    notices_delivered: int
    notices_read: int
    last_submission_at: datetime | None

    @property
    def on_time_rate(self) -> float | None:
        return self.on_time / self.tasks_due if self.tasks_due else None

    @property
    def read_rate(self) -> float | None:
        return self.notices_read / self.notices_delivered if self.notices_delivered else None


def trainee_metrics(db: Session, *, now: datetime, cohort_id: str | None = None) -> list[TraineeMetrics]:
    """One row per trainee (optionally one cohort's), by name."""
    trainees_stmt = (
        select(User, Cohort.name)
        .outerjoin(Cohort, Cohort.id == User.cohort_id)
        .where(User.role == "trainee")
        .order_by(User.name, User.id)
    )
    if cohort_id is not None:
        trainees_stmt = trainees_stmt.where(User.cohort_id == cohort_id)
    trainees = db.execute(trainees_stmt).all()

    # Task statuses and overdue flags: the shared rule from milestone_repo.
    statuses: dict[str, Counter] = {}
    for state in milestone_repo.task_states(db, now=now, cohort_id=cohort_id):
        counts = statuses.setdefault(state.trainee_id, Counter())
        counts[state.status] += 1
        counts["overdue"] += state.overdue

    # On time: for each task already past its deadline, was the trainee's FIRST report in time?
    first = (
        select(Submission.trainee_id, Submission.milestone_id, func.min(Submission.submitted_at).label("first_at"))
        .where(Submission.milestone_id.is_not(None))
        .group_by(Submission.trainee_id, Submission.milestone_id)
        .subquery("first_report")
    )
    punctuality = {
        trainee_id: (due, on_time)
        for trainee_id, due, on_time in db.execute(
            select(User.id, func.count(), func.count().filter(first.c.first_at <= Milestone.due_date))
            .join(Milestone, Milestone.cohort_id == User.cohort_id)
            .outerjoin(first, and_(first.c.trainee_id == User.id, first.c.milestone_id == Milestone.id))
            .where(User.role == "trainee", Milestone.due_date < now)
            .group_by(User.id)
        )
    }

    # Notices: everything addressed to the trainee's cohort or to everyone, and how many they've read.
    reading = {
        trainee_id: (delivered, read)
        for trainee_id, delivered, read in db.execute(
            select(User.id, func.count(Notice.id), func.count(NoticeRead.read_at))
            .join(Notice, or_(Notice.target_cohort_id.is_(None), Notice.target_cohort_id == User.cohort_id))
            .outerjoin(NoticeRead, and_(NoticeRead.notice_id == Notice.id, NoticeRead.trainee_id == User.id))
            .where(User.role == "trainee")
            .group_by(User.id)
        )
    }

    last_report = dict(
        db.execute(select(Submission.trainee_id, func.max(Submission.submitted_at)).group_by(Submission.trainee_id)).all()
    )

    rows = []
    for user, cohort_name in trainees:
        counts = statuses.get(user.id, Counter())
        due, on_time = punctuality.get(user.id, (0, 0))
        delivered, read = reading.get(user.id, (0, 0))
        rows.append(
            TraineeMetrics(
                trainee_id=user.id,
                name=user.name,
                email=user.email,
                cohort_id=user.cohort_id,
                cohort_name=cohort_name,
                tasks_due=due,
                on_time=on_time,
                overdue=counts["overdue"],
                completed=counts["completed"],
                under_review=counts["under_review"],
                in_progress=counts["in_progress"],
                notices_delivered=delivered,
                notices_read=read,
                last_submission_at=last_report.get(user.id),
            )
        )
    return rows


def health_status(score: int | None) -> str:
    if score is None:
        return "no_data"
    if score >= HEALTHY_FROM:
        return "healthy"
    return "watch" if score >= WATCH_FROM else "at_risk"


def cohort_health(db: Session, *, now: datetime) -> list[dict]:
    """Every cohort's health score, worst first, by summing its trainees' metrics."""
    metrics = trainee_metrics(db, now=now)
    results = []
    for cohort in db.scalars(select(Cohort).order_by(Cohort.start_date, Cohort.name)):
        rows = [m for m in metrics if m.cohort_id == cohort.id]
        due, on_time = sum(m.tasks_due for m in rows), sum(m.on_time for m in rows)
        delivered, read = sum(m.notices_delivered for m in rows), sum(m.notices_read for m in rows)
        on_time_rate = on_time / due if due else None
        read_rate = read / delivered if delivered else None

        # Weighted average of whichever parts have data (a brand-new cohort has no deadlines yet).
        parts = [(rate, weight) for rate, weight in ((on_time_rate, ON_TIME_WEIGHT), (read_rate, READ_WEIGHT)) if rate is not None]
        score = round(100 * sum(r * w for r, w in parts) / sum(w for _, w in parts)) if parts else None

        results.append(
            {
                "cohort": cohort,
                "score": score,
                "status": health_status(score),
                "on_time_rate": None if on_time_rate is None else round(on_time_rate, 2),
                "read_rate": None if read_rate is None else round(read_rate, 2),
                "trainees": len(rows),
                "overdue": sum(m.overdue for m in rows),
                "stalled": sum(m.in_progress for m in rows),
            }
        )
    order = {"at_risk": 0, "watch": 1, "healthy": 2, "no_data": 3}
    return sorted(results, key=lambda r: (order[r["status"]], r["score"] if r["score"] is not None else 101))
