"""Wipe the database and load demo data.

    python seed.py          (run `alembic upgrade head` first)

Every account's password is `password123`. Managers: manager@edtech.com and gandalf.grey@example.com.

Loads 3 cohorts with weekly milestones (Week N due at 23:59 on start + 7N days), a weekday class
timetable for each cohort, 12 trainees, 2 managers, 5 notices with read receipts, weekly progress
reports going back up to 6 weeks, one unread nudge (Gandalf -> Legolas Greenleaf) and an activity-log history.
Dates are relative to today, in this computer's timezone, so the numbers are the same whenever you run it:
    manager:  total_active 12, at_risk 2, overdue_submissions 9, read_rates 0.86
    health:   Cloud Native Q4 56 (at_risk), Full-Stack Foundations 68 (watch), Solo Track 100 (healthy)
    Frodo:    5 milestones reported, Week 6 due today, "2 tasks are pending now"
Escalations are not seeded: the API's background check raises them a few seconds after it starts.
"""

import sys
from datetime import UTC, date, datetime, time, timedelta

from sqlalchemy import delete, func, select, text
from sqlalchemy.exc import OperationalError, ProgrammingError
from sqlalchemy.orm import Session

from app.db import SessionLocal, engine
from app.models import (
    AuditEvent,
    Cohort,
    Escalation,
    Milestone,
    Notice,
    NoticeRead,
    Reminder,
    ScheduleBlock,
    Submission,
    User,
)
from app.repositories import (
    audit_repo,
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

# Managers mapped to Gandalf and Elrond
MANAGERS = [("Gandalf the Grey", "gandalf.grey@example.com"), ("Elrond of Rivendell", "manager@edtech.com")]

# name, cohort (index into COHORTS), weekly reports sent, punctuality, latest status, blocker
# Punctuality = days relative to each deadline the trainee hands in (negative = early, positive = late).
# It drives the on-time half of the cohort health score.
TRAINEES = [
    ("Frodo Baggins",     0, 5, -1, "needs_review", None),
    ("Samwise Gamgee",    0, 5, -2, "on_track",     None),
    ("Meriadoc Brandybuck", 0, 5, 1, "needs_review", None),                                               # always a day late
    ("Peregrin Took",     0, 4, 1,  "stalled",      "Stuck on Helm templating; pods keep crash-looping."), # at risk
    ("Aragorn son of Arathorn", 0, 3, 2, "on_track", None),                                              # overdue
    ("Legolas Greenleaf", 0, 2, 3,  "on_track",     None),                                                # overdue
    ("Gimli son of Gloin", 1, 3, 0, "stalled",      "Locked out of the warehouse since the credential rotation."), # at risk
    ("Boromir of Gondor", 2, 2, -1, "needs_review", None),
    ("Faramir Captain of Gondor", 2, 2, -1, "on_track", None),
    ("Eowyn of Rohan",    2, 2, -2, "needs_review", None),
    ("Eomer of Rohan",    2, 1, 1,  "on_track",     None),                                                # overdue
    ("Gollum Smeagol",    2, 0, 0,  None,           None),  # never submitted: overdue
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
UNREAD = {
    ("Gollum Smeagol", 0),
    ("Gollum Smeagol", 2),
    ("Gollum Smeagol", 3),
    ("Legolas Greenleaf", 1),
    ("Legolas Greenleaf", 2),
}

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
    for model in (AuditEvent, Escalation, NoticeRead, Reminder, ScheduleBlock, Submission, Milestone, Notice, User, Cohort):
        db.execute(delete(model))
    for model in (Cohort, User, Milestone, Notice, Submission, ScheduleBlock, Reminder, AuditEvent, Escalation):
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

    # Frodo first and Gandalf second, so ids match v1's seed (u1 = Frodo, u2 = Gandalf). Elrond comes last (u14).
    trainees = {}
    first, *rest = TRAINEES
    trainees[first[0]] = add_user(first[0], email_for(first[0]), "trainee", cohorts[first[1]].id)
    gandalf = add_user(*MANAGERS[0], "manager", None)
    for name, cohort_idx, *_ in rest:
        trainees[name] = add_user(name, email_for(name), "trainee", cohorts[cohort_idx].id)
    add_user(*MANAGERS[1], "manager", None)

    # Each report arrives `punctuality` days from its deadline, at about 6 pm local time.
    submission_count = 0
    sign_offs = []  # (submission, trainee name) for reports a manager has signed off
    for name, cohort_idx, reports, punctuality, latest_status, blocker in TRAINEES:
        handle = name.lower().replace(" ", "")
        for week in range(1, reports + 1):
            is_latest = week == reports
            status = latest_status if is_latest else "on_track"  # older reports were already reviewed
            task = milestones[cohort_idx][week - 1]
            submission = submission_repo.create(
                db,
                trainee_id=trainees[name].id,
                milestone_id=task.id,
                milestone_name=task.title,
                status=status,
                asset_url=f"https://github.com/{handle}/week-{week}",
                notes=blocker if status == "stalled" else NOTES[status],
                submitted_at=task.due_date + timedelta(days=punctuality, hours=-6),
            )
            submission_count += 1
            if status == "on_track":
                sign_offs.append((submission, name))

    read_count = 0
    posted = []
    for idx, (title, body, priority, cohort_idx, age) in enumerate(NOTICES):
        notice = notice_repo.create(
            db,
            title=title,
            body=body,
            priority=priority,
            target_cohort_id=None if cohort_idx is None else cohorts[cohort_idx].id,
            created_at=now - timedelta(days=age),
        )
        posted.append(notice)
        for name, trainee in trainees.items():
            delivered = notice.target_cohort_id in (None, trainee.cohort_id)
            if delivered and (name, idx) not in UNREAD:
                read_at = notice.created_at + timedelta(hours=1 + read_count % 20)
                notice_repo.mark_read(db, notice_id=notice.id, trainee_id=trainee.id, read_at=read_at)
                read_count += 1

    # Gandalf already nudged Legolas about his overdue Week 3, two days ago; he hasn't cleared it yet.
    nudge = reminder_repo.create(
        db,
        trainee_id=trainees["Legolas Greenleaf"].id,
        milestone_id=milestones[0][2].id,
        sent_by=gandalf.id,
        created_at=now - timedelta(days=2),
    )

    # Activity-log history, as if the actions had gone through the API: Gandalf posted the notices,
    # signed off reports a day after they arrived, and sent Legolas's nudge.
    log = lambda action, target_type, target_id, summary, at: audit_repo.record(  # noqa: E731
        db, actor=gandalf, action=action, target_type=target_type, target_id=target_id, summary=summary, at=at
    )
    names = {cohort.id: cohort.name for cohort in cohorts}
    for notice in posted:
        audience = names.get(notice.target_cohort_id, "everyone")
        log("notice.posted", "notice", notice.id,
            f"Posted {'an urgent' if notice.priority == 'urgent' else 'a'} notice “{notice.title}” to {audience}", notice.created_at)
    for submission, name in sign_offs:
        signed_at = submission.submitted_at + timedelta(days=1)
        if signed_at < now:
            log("submission.signed_off", "submission", submission.id,
                f"Signed off {name}'s report for {submission.milestone_name}", signed_at)
    log("reminder.sent", "reminder", nudge.id, f"Nudged Legolas Greenleaf about overdue {milestones[0][2].title}", nudge.created_at)

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
        "activity log entries": db.scalar(select(func.count()).select_from(AuditEvent)),
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