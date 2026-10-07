from fastapi import APIRouter, Query
from pydantic import AwareDatetime

from app.auth import Manager
from app.db import DB
from app.repositories import audit_repo
from app.schemas import AuditEntry

router = APIRouter(prefix="/api/audit", tags=["Audit log"])


@router.get("", response_model=list[AuditEntry])
def list_audit_events(
    db: DB,
    user: Manager,
    limit: int = Query(default=30, ge=1, le=100),
    before: AwareDatetime | None = Query(default=None, description="For the next page: the created_at of the last entry you have."),
):
    """Administrative actions, newest first: sign-offs, notices, dispatches, nudges, imports, escalations..."""
    return [
        AuditEntry(**{c: getattr(event, c) for c in AuditEntry.model_fields if c != "actor_name"}, actor_name=actor_name)
        for event, actor_name in audit_repo.list_recent(db, limit=limit, before=before)
    ]
