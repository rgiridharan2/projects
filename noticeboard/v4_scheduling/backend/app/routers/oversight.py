"""Manager oversight: the cohort matrix (who has done what) and nudging everyone who's overdue."""

from datetime import UTC, datetime

from fastapi import APIRouter

from app.auth import Manager
from app.db import DB
from app.lookups import get_cohort_or_404
from app.repositories import milestone_repo, reminder_repo, user_repo
from app.schemas import CohortMatrix, NudgeAllResult

router = APIRouter(prefix="/api/cohorts", tags=["Manager oversight"])


@router.get("/{cohort_id}/matrix", response_model=CohortMatrix)
def read_cohort_matrix(cohort_id: str, db: DB, user: Manager):
    """Trainees x milestones for one cohort. Each cell is that trainee's status on that task, whether
    it's overdue right now (deadline passed, nothing submitted) and whether they've been nudged."""
    cohort = get_cohort_or_404(db, cohort_id)
    now = datetime.now(UTC)
    nudged = reminder_repo.active_in_cohort(db, cohort_id)

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
    get_cohort_or_404(db, cohort_id)
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
    db.commit()
    return {"created": created, "already_nudged": skipped}
