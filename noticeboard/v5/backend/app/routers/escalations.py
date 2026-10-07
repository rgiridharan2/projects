from datetime import UTC, datetime

from fastapi import APIRouter
from sqlalchemy.orm import Session

from app.auth import Manager
from app.db import DB
from app.models import User
from app.repositories import audit_repo, escalation_repo
from app.schemas import EscalationItem, EscalationRunResult

router = APIRouter(prefix="/api/escalations", tags=["Escalations"])


def run_escalations(db: Session, *, actor: User | None, now: datetime) -> int:
    """Flag tasks 48h+ past their deadline with nothing submitted, log it, and commit. Returns how many
    were newly flagged. Used by the API trigger below and by the background check in main.py."""
    created = escalation_repo.run_check(db, now)
    if created:
        audit_repo.record(
            db,
            actor=actor,
            action="escalation.raised",
            target_type="escalation",
            target_id=None,
            summary=f"Escalated {len(created)} task{'s' if len(created) != 1 else ''} more than 48 hours past deadline with nothing submitted",
            at=now,
        )
    db.commit()
    return len(created)


@router.get("", response_model=list[EscalationItem])
def list_escalations(db: DB, user: Manager):
    """Unresolved escalations across all cohorts, oldest deadline first. Managers only."""
    return [
        EscalationItem(
            id=escalation.id,
            trainee_id=escalation.trainee_id,
            trainee_name=trainee_name,
            milestone_id=milestone.id,
            milestone_title=milestone.title,
            cohort_name=cohort_name,
            due_date=milestone.due_date,
            escalated_at=escalation.escalated_at,
        )
        for escalation, trainee_name, milestone, cohort_name in escalation_repo.list_active(db)
    ]


@router.post("/run", response_model=EscalationRunResult)
def run_escalation_check(db: DB, user: Manager):
    """Run the 48-hour escalation check now (it also runs in the background every 15 minutes)."""
    created = run_escalations(db, actor=user, now=datetime.now(UTC))
    return {"created": created, "active": len(escalation_repo.list_active(db))}
