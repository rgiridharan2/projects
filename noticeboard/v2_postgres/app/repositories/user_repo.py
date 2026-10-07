from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import User
from app.repositories.ids import next_id


def get(db: Session, user_id: str) -> User | None:
    return db.get(User, user_id)


def get_by_email(db: Session, email: str) -> User | None:
    return db.scalar(select(User).where(User.email == email.lower()))


def list_trainees(db: Session, cohort_id: str) -> list[User]:
    stmt = select(User).where(User.cohort_id == cohort_id, User.role == "trainee").order_by(User.name)
    return list(db.scalars(stmt))


def create(db: Session, *, name: str, email: str, role: str, cohort_id: str | None) -> User:
    user = User(id=next_id(db, User), name=name, email=email.lower(), role=role, cohort_id=cohort_id)
    db.add(user)
    db.flush()
    return user
