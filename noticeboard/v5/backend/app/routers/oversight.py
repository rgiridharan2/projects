"""Manager oversight: cohort health, the cohort matrix, nudging everyone who's overdue, and CSV reports."""

import csv
import io
import re
from datetime import UTC, datetime

from fastapi import APIRouter, Response

from app.auth import Manager
from app.db import DB
from app.lookups import get_cohort_or_404
from app.repositories import analytics_repo, audit_repo, escalation_repo, milestone_repo, reminder_repo, user_repo
from app.schemas import CohortHealth, CohortMatrix, NudgeAllResult

router = APIRouter(prefix="/api/cohorts", tags=["Manager oversight"])

REPORT_COLUMNS = [
    "trainee_id", "name", "email", "cohort", "tasks_due", "on_time", "on_time_rate", "overdue",
    "completed", "under_review", "in_progress", "notices_delivered", "notices_read", "read_rate", "last_submission_at",
]


@router.get("/health", response_model=list[CohortHealth])
def list_cohort_health(db: DB, user: Manager):
    """Every cohort's health score, worst first: 60% on-time submissions + 40% notices read, 0-100.
    Below 60 the cohort is flagged at_risk."""
    return analytics_repo.cohort_health(db, now=datetime.now(UTC))


@router.get("/{cohort_id}/report.csv", response_class=Response, responses={200: {"content": {"text/csv": {}}}})
def download_cohort_report(cohort_id: str, db: DB, user: Manager):
    """Per-trainee performance report for one cohort, as a CSV file. Managers only."""
    cohort = get_cohort_or_404(db, cohort_id)
    now = datetime.now(UTC)
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(REPORT_COLUMNS)
    rate = lambda value: "" if value is None else f"{value:.2f}"  # noqa: E731
    for m in analytics_repo.trainee_metrics(db, now=now, cohort_id=cohort_id):
        writer.writerow([
            m.trainee_id, m.name, m.email, m.cohort_name, m.tasks_due, m.on_time, rate(m.on_time_rate), m.overdue,
            m.completed, m.under_review, m.in_progress, m.notices_delivered, m.notices_read, rate(m.read_rate),
            m.last_submission_at.isoformat() if m.last_submission_at else "",
        ])
    slug = re.sub(r"[^a-z0-9]+", "-", cohort.name.lower()).strip("-")
    filename = f"{slug}-report-{now.date().isoformat()}.csv"
    # utf-8-sig adds a byte-order mark so Excel opens accented names correctly.
    return Response(
        buffer.getvalue().encode("utf-8-sig"),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/{cohort_id}/matrix", response_model=CohortMatrix)
def read_cohort_matrix(cohort_id: str, db: DB, user: Manager):
    """Trainees x milestones for one cohort. Each cell is that trainee's status on that task, whether
    it's overdue right now (deadline passed, nothing submitted) and whether they've been nudged."""
    cohort = get_cohort_or_404(db, cohort_id)
    now = datetime.now(UTC)
    nudged = reminder_repo.active_in_cohort(db, cohort_id)
    escalated = escalation_repo.active_in_cohort(db, cohort_id)

    # One row per trainee (by name), filled with their cells in milestone order.
    rows = {t.id: {"trainee": t, "cells": []} for t in user_repo.list_trainees(db, cohort_id)}
    for state in milestone_repo.task_states(db, now=now, cohort_id=cohort_id):
        rows[state.trainee_id]["cells"].append(
            {
                "milestone_id": state.milestone.id,
                "status": state.status,
                "overdue": state.overdue,
                "last_submitted_at": state.last_submitted_at,
                "nudged_at": nudged.get((state.trainee_id, state.milestone.id)),
                "escalated": (state.trainee_id, state.milestone.id) in escalated,
            }
        )
    for row in rows.values():
        row["overdue_count"] = sum(cell["overdue"] for cell in row["cells"])

    return {
        "cohort": cohort,
        "milestones": milestone_repo.list_for_cohort(db, cohort_id),
        "rows": list(rows.values()),
        "overdue_total": sum(row["overdue_count"] for row in rows.values()),
    }


@router.post("/{cohort_id}/nudges", response_model=NudgeAllResult)
def nudge_all_overdue(cohort_id: str, db: DB, user: Manager):
    """Send a reminder for every overdue task in the cohort that doesn't already have an unread one."""
    cohort = get_cohort_or_404(db, cohort_id)
    now = datetime.now(UTC)
    nudged = reminder_repo.active_in_cohort(db, cohort_id)

    created = skipped = 0
    for state in milestone_repo.task_states(db, now=now, cohort_id=cohort_id):
        if not state.overdue:
            continue
        if (state.trainee_id, state.milestone.id) in nudged:
            skipped += 1
            continue
        reminder_repo.create(
            db, trainee_id=state.trainee_id, milestone_id=state.milestone.id, sent_by=user.id, created_at=now
        )
        created += 1
    if created:
        audit_repo.record(
            db,
            actor=user,
            action="reminder.bulk_sent",
            target_type="cohort",
            target_id=cohort.id,
            summary=f"Nudged {created} overdue task{'s' if created != 1 else ''} in {cohort.name}",
            at=now,
        )
    db.commit()
    return {"created": created, "already_nudged": skipped}
