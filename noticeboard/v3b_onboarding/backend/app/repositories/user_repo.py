from sqlalchemy import case, select
from sqlalchemy.orm import Session

from app.models import Cohort, User
from app.repositories.ids import next_id


def get(db: Session, user_id: str) -> User | None:
    return db.get(User, user_id)


def get_by_email(db: Session, email: str) -> User | None:
    return db.scalar(select(User).where(User.email == email.lower()))


def get_by_identifier(db: Session, identifier: str) -> User | None:
    """Look a user up by email (anything containing '@') or by id."""
    identifier = identifier.strip()
    return get_by_email(db, identifier) if "@" in identifier else get(db, identifier)


def list_trainees(db: Session, cohort_id: str) -> list[User]:
    stmt = select(User).where(User.cohort_id == cohort_id, User.role == "trainee").order_by(User.name)
    return list(db.scalars(stmt))


def list_peers(db: Session, *, cohort_id: str, exclude_id: str) -> list[User]:
    """The other trainees in a cohort, by name."""
    stmt = (
        select(User)
        .where(User.cohort_id == cohort_id, User.role == "trainee", User.id != exclude_id)
        .order_by(User.name)
    )
    return list(db.scalars(stmt))


def list_switch_options(db: Session) -> list[dict]:
    """Everyone who can log in, with their cohort's name: managers first, then trainees by cohort and name."""
    stmt = (
        select(User.id, User.name, User.role, Cohort.name.label("cohort_name"))
        .outerjoin(Cohort, Cohort.id == User.cohort_id)
        .where(User.hashed_password.is_not(None))
        .order_by(case((User.role == "manager", 0), else_=1), Cohort.start_date, User.name)
    )
    return [row._asdict() for row in db.execute(stmt)]


def create(
    db: Session, *, name: str, email: str, role: str, cohort_id: str | None, hashed_password: str | None
) -> User:
    user = User(
        id=next_id(db, User),
        name=name,
        email=email.lower(),
        role=role,
        cohort_id=cohort_id,
        hashed_password=hashed_password,
    )
    db.add(user)
    db.flush()
    return user
