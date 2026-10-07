from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Query, status

from app.db import DB
from app.lookups import get_cohort_or_404, get_trainee_or_404
from app.repositories import notice_repo
from app.schemas import Notice, NoticeCreate, NoticeReadCreate, NoticeReadStatus

router = APIRouter(prefix="/api/notices", tags=["Notices"])


@router.post("", response_model=Notice, status_code=status.HTTP_201_CREATED)
def create_notice(payload: NoticeCreate, db: DB):
    """Post a notice to one cohort, or to all trainees when `target_cohort_id` is null."""
    if payload.target_cohort_id is not None:
        get_cohort_or_404(db, payload.target_cohort_id)

    notice = notice_repo.create(db, **payload.model_dump(), created_at=datetime.now(UTC))
    db.commit()
    return notice


@router.get("", response_model=list[Notice])
def list_notices(
    db: DB,
    cohort_id: str | None = Query(
        default=None,
        description="Return this cohort's notices plus global ones. Omit to list every notice.",
    ),
):
    """Notices applicable to a cohort, urgent first, then newest first."""
    if cohort_id is not None:
        get_cohort_or_404(db, cohort_id)
    return notice_repo.list_for_cohort(db, cohort_id)


@router.post("/{notice_id}/read", response_model=NoticeReadStatus)
def mark_notice_read(notice_id: str, payload: NoticeReadCreate, db: DB):
    """Mark a notice as read by a trainee. Idempotent: repeat calls keep the first `read_at`."""
    notice = notice_repo.get(db, notice_id)
    if notice is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Notice '{notice_id}' not found")
    trainee = get_trainee_or_404(db, payload.trainee_id)
    if notice.target_cohort_id not in (None, trainee.cohort_id):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Notice is not addressed to this trainee's cohort")

    receipt = notice_repo.mark_read(db, notice_id=notice_id, trainee_id=trainee.id, read_at=datetime.now(UTC))
    db.commit()
    return receipt
