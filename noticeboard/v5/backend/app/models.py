"""SQLAlchemy tables. One class per read model in app/schemas.py, same column names.

Value rules (roles, statuses, priorities) are enforced by the Pydantic Literal types, so
the columns are plain strings: no Postgres ENUM types, CHECK constraints or triggers.
"""

from datetime import date, datetime
from typing import ClassVar

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, MetaData, Sequence, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# Predictable constraint names, so later migrations can refer to (and drop) them by name.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


# IDs keep v1's format ("c1", "u13") so the API contract doesn't change. Each table gets its
# numbers from its own Postgres sequence (see repositories/ids.py), which never hands out the
# same number twice, even to concurrent requests.


class Cohort(Base):
    __tablename__ = "cohorts"
    id_prefix: ClassVar[str] = "c"
    id_seq: ClassVar[Sequence] = Sequence("cohorts_id_seq", metadata=Base.metadata)

    id: Mapped[str] = mapped_column(String(20), primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    track_type: Mapped[str] = mapped_column(String(10))
    start_date: Mapped[date] = mapped_column(Date)
    # Only open cohorts appear in the public sign-up dropdown, so strangers can't join any cohort they like.
    open_for_signup: Mapped[bool] = mapped_column(Boolean, default=True)


class User(Base):
    __tablename__ = "users"
    id_prefix: ClassVar[str] = "u"
    id_seq: ClassVar[Sequence] = Sequence("users_id_seq", metadata=Base.metadata)

    id: Mapped[str] = mapped_column(String(20), primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    email: Mapped[str] = mapped_column(String(254), unique=True, index=True)  # stored lowercase
    role: Mapped[str] = mapped_column(String(10))
    cohort_id: Mapped[str | None] = mapped_column(ForeignKey("cohorts.id"), index=True)
    # bcrypt hash, never the password itself. Null = can't log in (rows that existed before migration 0002).
    hashed_password: Mapped[str | None] = mapped_column(String(255))


class Notice(Base):
    __tablename__ = "notices"
    id_prefix: ClassVar[str] = "n"
    id_seq: ClassVar[Sequence] = Sequence("notices_id_seq", metadata=Base.metadata)

    id: Mapped[str] = mapped_column(String(20), primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text)
    priority: Mapped[str] = mapped_column(String(10))
    target_cohort_id: Mapped[str | None] = mapped_column(ForeignKey("cohorts.id"), index=True)  # null = everyone
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class NoticeRead(Base):
    __tablename__ = "notice_reads"

    # Composite primary key: at most one read receipt per trainee per notice.
    notice_id: Mapped[str] = mapped_column(ForeignKey("notices.id"), primary_key=True)
    trainee_id: Mapped[str] = mapped_column(ForeignKey("users.id"), primary_key=True)
    read_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Milestone(Base):
    """A task assigned to everyone in a cohort, with a deadline."""

    __tablename__ = "milestones"
    # Two tasks in one cohort can't share a position in its sequence.
    __table_args__ = (UniqueConstraint("cohort_id", "milestone_order"),)
    id_prefix: ClassVar[str] = "m"
    id_seq: ClassVar[Sequence] = Sequence("milestones_id_seq", metadata=Base.metadata)

    id: Mapped[str] = mapped_column(String(20), primary_key=True)
    cohort_id: Mapped[str] = mapped_column(ForeignKey("cohorts.id"), index=True)
    milestone_order: Mapped[int] = mapped_column(Integer)  # 1, 2, 3... within the cohort
    title: Mapped[str] = mapped_column(String(200))
    due_date: Mapped[datetime] = mapped_column(DateTime(timezone=True))  # an exact moment, e.g. Fri 23:59 local


class ScheduleBlock(Base):
    """A scheduled time slot for a cohort (lecture, lab, office hours...), shown on the agenda timeline."""

    __tablename__ = "schedule_blocks"
    id_prefix: ClassVar[str] = "b"
    id_seq: ClassVar[Sequence] = Sequence("schedule_blocks_id_seq", metadata=Base.metadata)

    id: Mapped[str] = mapped_column(String(20), primary_key=True)
    cohort_id: Mapped[str] = mapped_column(ForeignKey("cohorts.id"), index=True)
    milestone_id: Mapped[str | None] = mapped_column(ForeignKey("milestones.id"))  # the module it belongs to
    title: Mapped[str] = mapped_column(String(200))
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Reminder(Base):
    """A manager's nudge to one trainee about one overdue task."""

    __tablename__ = "reminders"
    id_prefix: ClassVar[str] = "r"
    id_seq: ClassVar[Sequence] = Sequence("reminders_id_seq", metadata=Base.metadata)

    id: Mapped[str] = mapped_column(String(20), primary_key=True)
    trainee_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    milestone_id: Mapped[str] = mapped_column(ForeignKey("milestones.id"))
    sent_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    # Set when the trainee dismisses it or submits the task. Null = still showing.
    dismissed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AuditEvent(Base):
    """One administrative action, for the activity log: who did what, to what, and when."""

    __tablename__ = "audit_events"
    id_prefix: ClassVar[str] = "a"
    id_seq: ClassVar[Sequence] = Sequence("audit_events_id_seq", metadata=Base.metadata)

    id: Mapped[str] = mapped_column(String(20), primary_key=True)
    actor_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"))  # null = the system (background checks)
    action: Mapped[str] = mapped_column(String(40))  # e.g. "submission.signed_off", "notice.posted"
    target_type: Mapped[str] = mapped_column(String(30))  # "submission", "notice", "milestone", ...
    target_id: Mapped[str | None] = mapped_column(String(20))
    summary: Mapped[str] = mapped_column(Text)  # human-readable, written at the time of the action
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class Escalation(Base):
    """A task flagged because it's more than 48 hours past its deadline with nothing submitted."""

    __tablename__ = "escalations"
    # Each (trainee, task) can only be escalated once, so re-running the check never duplicates flags.
    __table_args__ = (UniqueConstraint("trainee_id", "milestone_id"),)
    id_prefix: ClassVar[str] = "e"
    id_seq: ClassVar[Sequence] = Sequence("escalations_id_seq", metadata=Base.metadata)

    id: Mapped[str] = mapped_column(String(20), primary_key=True)
    trainee_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    milestone_id: Mapped[str] = mapped_column(ForeignKey("milestones.id"))
    escalated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))  # set when the task is submitted


class Submission(Base):
    __tablename__ = "submissions"
    id_prefix: ClassVar[str] = "s"
    id_seq: ClassVar[Sequence] = Sequence("submissions_id_seq", metadata=Base.metadata)

    id: Mapped[str] = mapped_column(String(20), primary_key=True)
    trainee_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    # The task this report is for. Null for free-form reports (and every report made before v3b).
    milestone_id: Mapped[str | None] = mapped_column(ForeignKey("milestones.id"), index=True)
    milestone_name: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(20))
    asset_url: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
