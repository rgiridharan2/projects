"""Wipe the database and load demo data.

    python seed.py          (run `alembic upgrade head` first)

Every account's password is `password123`.

Loads 3 cohorts, 12 trainees plus 1 manager, 5 notices with read receipts, and weekly
progress reports going back up to 6 weeks. All dates are relative to today, so the dashboard
shows the same numbers whenever you run it:
    total_active 12, at_risk 2, overdue_submissions 4, read_rates 0.86
"""

import sys
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, text
from sqlalchemy.exc import OperationalError, ProgrammingError
from sqlalchemy.orm import Session

from app.db import SessionLocal, engine
from app.models import Cohort, Notice, NoticeRead, Submission, User
from app.repositories import cohort_repo, notice_repo, submission_repo, user_repo
from app.security import hash_password

# name, track type, started N days ago, weekly milestones
COHORTS = [
    ("Cloud Native Q4", "group", 42, ["Linux & Git", "Docker basics", "Kubernetes fundamentals",
                                      "Helm & config", "CI/CD pipelines", "Observability"]),
    ("Solo Track - Data", "solo", 28, ["SQL foundations", "Python for data", "pandas wrangling", "Data modelling"]),
    ("Full-Stack Foundations", "group", 21, ["HTML & CSS", "JavaScript essentials", "React basics"]),
]

DEMO_PASSWORD = "password123"

MANAGER = ("Alex Smith", "alex.smith@example.com")

# name, cohort (index into COHORTS), weekly reports sent, days since the latest one, latest status, blocker
TRAINEES = [
    ("Jane Doe",       0, 5, 2,  "needs_review", None),
    ("Marcus Chen",    0, 5, 3,  "on_track",     None),
    ("Priya Patel",    0, 5, 1,  "needs_review", None),
    ("Tom Okafor",     0, 4, 4,  "stalled",      "Stuck on Helm templating; pods keep crash-looping."),  # at risk
    ("Sofia Rossi",    0, 3, 12, "on_track",     None),                                                 # overdue
    ("Liam Murphy",    0, 2, 20, "on_track",     None),                                                 # overdue
    ("Aisha Khan",     1, 3, 5,  "stalled",      "Locked out of the warehouse since the credential rotation."),  # at risk
    ("Diego Alvarez",  2, 2, 2,  "needs_review", None),
    ("Hannah Schmidt", 2, 2, 3,  "on_track",     None),
    ("Kenji Tanaka",   2, 2, 1,  "needs_review", None),
    ("Grace Mensah",   2, 1, 10, "on_track",     None),                                                 # overdue
    ("Ethan Brooks",   2, 0, 0,  None,           None),  # never submitted: overdue
]

# title, body, priority, target cohort (index into COHORTS, None = everyone), posted N days ago
NOTICES = [
    ("Welcome to the Q4 programme", "Your cohort lead will reach out this week. Submit a progress "
     "report every Friday.", "standard", None, 41),
    ("Kubernetes lab cluster maintenance", "The shared k8s cluster is offline Saturday 08:00-12:00 UTC.",
     "urgent", 0, 10),
    ("Holiday schedule", "No live sessions next Monday. Async work continues as normal.", "standard", None, 6),
    ("React workshop moved to Thursday", "Same time and link, new day.", "standard", 2, 4),
    ("Warehouse credentials rotated", "Re-run the setup script to pick up new credentials before your next session.",
     "urgent", 1, 2),
]

# (trainee, notice index) pairs left unread; every other delivered notice has been read.
UNREAD = {("Ethan Brooks", 0), ("Ethan Brooks", 2), ("Ethan Brooks", 3), ("Liam Murphy", 1), ("Liam Murphy", 2)}

NOTES = {
    "on_track": "Completed all exercises; repo README has run instructions.",
    "needs_review": "Ready for review. Would like feedback on the project structure.",
}


def wipe(db: Session) -> None:
    """Delete every row and restart the id sequences, so the next ids are c1, u1, n1, s1."""
    # Children before parents, so no foreign key ever points at a deleted row.
    for model in (NoticeRead, Submission, Notice, User, Cohort):
        db.execute(delete(model))
    for model in (Cohort, User, Notice, Submission):
        db.execute(text(f"ALTER SEQUENCE {model.id_seq.name} RESTART WITH 1"))


def seed(db: Session, now: datetime) -> dict[str, int]:
    """Insert the demo data through the repository layer. Returns row counts."""
    cohorts = [
        cohort_repo.create(db, name=name, track_type=track, start_date=(now - timedelta(days=age)).date())
        for name, track, age, _ in COHORTS
    ]

    def email_for(name: str) -> str:
        return name.lower().replace(" ", ".") + "@example.com"

    # bcrypt is deliberately slow (~0.25 s), so hash the shared demo password once instead of 13 times.
    hashed = hash_password(DEMO_PASSWORD)

    def add_user(name: str, email: str, role: str, cohort_id: str | None):
        return user_repo.create(db, name=name, email=email, role=role, cohort_id=cohort_id, hashed_password=hashed)

    # Jane first and the manager second, so ids match v1's seed (u1 = Jane, u2 = Alex).
    trainees = {}
    first, *rest = TRAINEES
    trainees[first[0]] = add_user(first[0], email_for(first[0]), "trainee", cohorts[first[1]].id)
    add_user(*MANAGER, "manager", None)
    for name, cohort_idx, *_ in rest:
        trainees[name] = add_user(name, email_for(name), "trainee", cohorts[cohort_idx].id)

    submission_count = 0
    for name, cohort_idx, reports, days_since_last, latest_status, blocker in TRAINEES:
        milestones = COHORTS[cohort_idx][3]
        handle = name.lower().replace(" ", "")
        for week in range(1, reports + 1):
            is_latest = week == reports
            status = latest_status if is_latest else "on_track"  # older reports were already reviewed
            submission_repo.create(
                db,
                trainee_id=trainees[name].id,
                milestone_name=f"Week {week}: {milestones[week - 1]}",
                status=status,
                asset_url=f"https://github.com/{handle}/week-{week}",
                notes=blocker if status == "stalled" else NOTES[status],
                submitted_at=now - timedelta(days=days_since_last + (reports - week) * 7, hours=3),
            )
            submission_count += 1

    read_count = 0
    for idx, (title, body, priority, cohort_idx, age) in enumerate(NOTICES):
        notice = notice_repo.create(
            db,
            title=title,
            body=body,
            priority=priority,
            target_cohort_id=None if cohort_idx is None else cohorts[cohort_idx].id,
            created_at=now - timedelta(days=age),
        )
        for name, trainee in trainees.items():
            delivered = notice.target_cohort_id in (None, trainee.cohort_id)
            if delivered and (name, idx) not in UNREAD:
                read_at = notice.created_at + timedelta(hours=1 + read_count % 20)
                notice_repo.mark_read(db, notice_id=notice.id, trainee_id=trainee.id, read_at=read_at)
                read_count += 1

    return {
        "cohorts": len(cohorts),
        "trainees": len(trainees),
        "managers": 1,
        "notices": len(NOTICES),
        "read receipts": read_count,
        "submissions": submission_count,
    }


def main() -> int:
    target = engine.url.render_as_string(hide_password=True)
    try:
        with SessionLocal() as db:
            wipe(db)
            counts = seed(db, now=datetime.now(UTC))
            db.commit()  # one transaction: either everything is replaced or nothing changes
    except OperationalError:
        print(f"Could not connect to {target}. Is Postgres running? See SETUP_POSTGRES.md.", file=sys.stderr)
        return 1
    except ProgrammingError:
        print("Tables or columns missing. Run `alembic upgrade head` first.", file=sys.stderr)
        return 1

    print(f"Seeded {target}")
    for table, n in counts.items():
        print(f"  {n:>3} {table}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
