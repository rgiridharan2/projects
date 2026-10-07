"""Wipe the database and load demo data.

    python seed.py          (run `alembic upgrade head` first)

Every account's password is `password123`. Managers: manager@edtech.com and alex.smith@example.com.

Loads 3 cohorts with weekly milestones (Week N due at 23:59 on start + 7N days), a weekday class
timetable for each cohort, 12 trainees, 2 managers, 5 notices with read receipts, weekly progress
reports going back up to 6 weeks, and one unread nudge (Alex -> Liam). Dates are relative to today,
in this computer's timezone, so the dashboards show the same numbers whenever you run it:
    manager:  total_active 12, at_risk 2, overdue_submissions 9, read_rates 0.86
    Jane:     5 milestones reported, Week 6 due today, "2 tasks are pending now"
"""

import sys
from datetime import UTC, date, datetime, time, timedelta

from sqlalchemy import delete, text
from sqlalchemy.exc import OperationalError, ProgrammingError
from sqlalchemy.orm import Session

from app.db import SessionLocal, engine
from app.models import Cohort, Milestone, Notice, NoticeRead, Reminder, ScheduleBlock, Submission, User
from app.repositories import (
    cohort_repo,
    milestone_repo,
    notice_repo,
    reminder_repo,
    schedule_repo,
    submission_repo,
    user_repo,
)
from app.security import hash_password

# name, track type, started N days ago, open for public sign-up, weekly milestones (Week N is due start + 7N days)
COHORTS = [
    ("Cloud Native Q4", "group", 42, True, ["Linux & Git", "Docker basics", "Kubernetes fundamentals", "Helm & config",
                                            "CI/CD pipelines", "Observability", "Service mesh basics", "Capstone project"]),
    # Solo tracks are assigned one-to-one by a manager, so they stay out of the public sign-up list.
    ("Solo Track - Data", "solo", 28, False, ["SQL foundations", "Python for data", "pandas wrangling",
                                              "Data modelling", "Dashboards & BI", "Capstone project"]),
    ("Full-Stack Foundations", "group", 21, True, ["HTML & CSS", "JavaScript essentials", "React basics",
                                                   "State management", "APIs & data fetching", "Capstone project"]),
]

DEMO_PASSWORD = "password123"

MANAGERS = [("Alex Smith", "alex.smith@example.com"), ("Morgan Reyes", "manager@edtech.com")]

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

# The weekly class timetable: (weekday 0=Mon, start, end, title). {topic} is that week's module.
TIMETABLE = [
    (0, "09:00", "10:30", "Kickoff lecture: {topic}"),
    (0, "13:00", "15:00", "Lab: {topic}"),
    (1, "10:00", "12:00", "Workshop: {topic}"),
    (1, "14:00", "16:00", "Lab: {topic}"),
    (2, "09:30", "10:00", "Stand-up"),
    (2, "10:00", "12:30", "Pair programming: {topic}"),
    (3, "13:00", "15:30", "Lab: {topic}"),
    (3, "16:00", "17:00", "Mentor check-in"),
    (4, "09:00", "10:00", "Office hours"),
    (4, "15:00", "16:00", "Demo & review: {topic}"),
]

NOTES = {
    "on_track": "Completed all exercises; repo README has run instructions.",
    "needs_review": "Ready for review. Would like feedback on the project structure.",
}


def wipe(db: Session) -> None:
    """Delete every row and restart the id sequences, so the next ids are c1, u1, m1, n1, s1..."""
    # Children before parents, so no foreign key ever points at a deleted row.
    for model in (NoticeRead, Reminder, ScheduleBlock, Submission, Milestone, Notice, User, Cohort):
        db.execute(delete(model))
    for model in (Cohort, User, Milestone, Notice, Submission, ScheduleBlock, Reminder):
        db.execute(text(f"ALTER SEQUENCE {model.id_seq.name} RESTART WITH 1"))


def local_time(day: date, clock: str) -> datetime:
    """A wall-clock time on a day in this computer's timezone, as an aware datetime.
    (A naive datetime's .astimezone() applies the local offset for that date, daylight saving included.)"""
    return datetime.combine(day, time.fromisoformat(clock)).astimezone()


def seed(db: Session, now: datetime) -> dict[str, int]:
    """Insert the demo data through the repository layer. Returns row counts."""
    today = now.astimezone().date()  # local "today", so "due today" means today on this computer
    cohorts = [
        cohort_repo.create(
            db, name=name, track_type=track, start_date=today - timedelta(days=age), open_for_signup=is_open
        )
        for name, track, age, is_open, _ in COHORTS
    ]
    # milestones[cohort index][week - 1]; Week N is due at 23:59 on start + N weeks, local time.
    milestones = [
        [
            milestone_repo.create(
                db,
                cohort_id=cohort.id,
                title=f"Week {week}: {title}",
                due_date=local_time(cohort.start_date + timedelta(weeks=week), "23:59"),
                milestone_order=week,
            )
            for week, title in enumerate(COHORTS[idx][4], start=1)
        ]
        for idx, cohort in enumerate(cohorts)
    ]

    # Each cohort's timetable, Monday to Friday, from its start until its last deadline.
    block_count = 0
    for cohort, tasks in zip(cohorts, milestones):
        for offset in range(len(tasks) * 7):
            day = cohort.start_date + timedelta(days=offset)
            task = tasks[offset // 7]  # the module whose week this is
            topic = task.title.split(": ", 1)[1]
            for weekday, start, end, title in TIMETABLE:
                if day.weekday() == weekday:
                    schedule_repo.create(
                        db,
                        cohort_id=cohort.id,
                        milestone_id=task.id,
                        title=title.format(topic=topic),
                        starts_at=local_time(day, start),
                        ends_at=local_time(day, end),
                    )
                    block_count += 1

    def email_for(name: str) -> str:
        return name.lower().replace(" ", ".") + "@example.com"

    # bcrypt is deliberately slow (~0.25 s), so hash the shared demo password once instead of 13 times.
    hashed = hash_password(DEMO_PASSWORD)

    def add_user(name: str, email: str, role: str, cohort_id: str | None):
        return user_repo.create(db, name=name, email=email, role=role, cohort_id=cohort_id, hashed_password=hashed)

    # Jane first and Alex second, so ids match v1's seed (u1 = Jane, u2 = Alex). Morgan comes last (u14).
    trainees = {}
    first, *rest = TRAINEES
    trainees[first[0]] = add_user(first[0], email_for(first[0]), "trainee", cohorts[first[1]].id)
    alex = add_user(*MANAGERS[0], "manager", None)
    for name, cohort_idx, *_ in rest:
        trainees[name] = add_user(name, email_for(name), "trainee", cohorts[cohort_idx].id)
    add_user(*MANAGERS[1], "manager", None)

    submission_count = 0
    for name, cohort_idx, reports, days_since_last, latest_status, blocker in TRAINEES:
        handle = name.lower().replace(" ", "")
        for week in range(1, reports + 1):
            is_latest = week == reports
            status = latest_status if is_latest else "on_track"  # older reports were already reviewed
            submission_repo.create(
                db,
                trainee_id=trainees[name].id,
                milestone_id=milestones[cohort_idx][week - 1].id,
                milestone_name=milestones[cohort_idx][week - 1].title,
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

    # Alex already nudged Liam about his overdue Week 3, two days ago; he hasn't cleared it yet.
    reminder_repo.create(
        db,
        trainee_id=trainees["Liam Murphy"].id,
        milestone_id=milestones[0][2].id,
        sent_by=alex.id,
        created_at=now - timedelta(days=2),
    )

    return {
        "cohorts": len(cohorts),
        "milestones": sum(len(m) for m in milestones),
        "schedule blocks": block_count,
        "trainees": len(trainees),
        "managers": len(MANAGERS),
        "notices": len(NOTICES),
        "read receipts": read_count,
        "submissions": submission_count,
        "reminders": 1,
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
