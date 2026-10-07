from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Submission, User
from app.repositories.ids import next_id


def get(db: Session, submission_id: str) -> Submission | None:
    return db.get(Submission, submission_id)


def list_recent(db: Session, *, cohort_id: str | None, limit: int) -> list[Submission]:
    """Newest submissions first, optionally only from trainees in one cohort."""
    stmt = select(Submission).order_by(Submission.submitted_at.desc()).limit(limit)
    if cohort_id is not None:
        stmt = stmt.join(User, User.id == Submission.trainee_id).where(User.cohort_id == cohort_id)
    return list(db.scalars(stmt))


def list_for_trainee(db: Session, trainee_id: str) -> list[Submission]:
    """All of one trainee's submissions, newest first."""
    stmt = select(Submission).where(Submission.trainee_id == trainee_id).order_by(Submission.submitted_at.desc())
    return list(db.scalars(stmt))


def create(
    db: Session,
    *,
    trainee_id: str,
    milestone_id: str | None = None,
    milestone_name: str,
    status: str,
    asset_url: str | None,
    notes: str | None,
    submitted_at: datetime,
) -> Submission:
    submission = Submission(
        id=next_id(db, Submission),
        trainee_id=trainee_id,
        milestone_id=milestone_id,
        milestone_name=milestone_name,
        status=status,
        asset_url=asset_url,
        notes=notes,
        submitted_at=submitted_at,
    )
    db.add(submission)
    db.flush()
    return submission


def set_status(db: Session, submission: Submission, status: str) -> Submission:
    submission.status = status
    db.flush()
    return submission
