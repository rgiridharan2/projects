from datetime import date

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from app.models import Cohort, User
from app.repositories.ids import next_id


def get(db: Session, cohort_id: str) -> Cohort | None:
    return db.get(Cohort, cohort_id)


def list_with_trainee_counts(db: Session) -> list[tuple[Cohort, int]]:
    """Every cohort with its trainee count, in one query. LEFT JOIN so empty cohorts show 0."""
    stmt = (
        select(Cohort, func.count(User.id))
        .outerjoin(User, and_(User.cohort_id == Cohort.id, User.role == "trainee"))
        .group_by(Cohort.id)
        .order_by(Cohort.start_date, Cohort.name)
    )
    return list(db.execute(stmt).all())


def list_open_for_signup(db: Session) -> list[Cohort]:
    stmt = select(Cohort).where(Cohort.open_for_signup).order_by(Cohort.start_date, Cohort.name)
    return list(db.scalars(stmt))


def create(
    db: Session, *, name: str, track_type: str, start_date: date, open_for_signup: bool = True
) -> Cohort:
    cohort = Cohort(
        id=next_id(db, Cohort),
        name=name,
        track_type=track_type,
        start_date=start_date,
        open_for_signup=open_for_signup,
    )
    db.add(cohort)
    db.flush()
    return cohort
