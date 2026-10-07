from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Query, status

from app.auth import Manager, Trainee
from app.db import DB
from app.lookups import get_cohort_or_404
from app.repositories import audit_repo, notice_repo
from app.schemas import Notice, NoticeCreate, NoticeFeedItem, NoticeReadStatus

router = APIRouter(prefix="/api/notices", tags=["Notices"])


@router.post("", response_model=Notice, status_code=status.HTTP_201_CREATED)
def create_notice(payload: NoticeCreate, db: DB, user: Manager):
    """Post a notice to one cohort, or to all trainees when `target_cohort_id` is null. Managers only."""
    audience = "everyone"
    if payload.target_cohort_id is not None:
        audience = get_cohort_or_404(db, payload.target_cohort_id).name

    notice = notice_repo.create(db, **payload.model_dump(), created_at=datetime.now(UTC))
    audit_repo.record(
        db,
        actor=user,
        action="notice.posted",
        target_type="notice",
        target_id=notice.id,
        summary=f"Posted {'an urgent' if notice.priority == 'urgent' else 'a'} notice “{notice.title}” to {audience}",
        at=notice.created_at,
    )
    db.commit()
    return notice


@router.get("", response_model=list[Notice])
def list_notices(
    db: DB,
    user: Manager,
    cohort_id: str | None = Query(
        default=None,
        description="Return this cohort's notices plus global ones. Omit to list every notice.",
    ),
):
    """Notices for any cohort, urgent first, then newest. Managers only (trainees use /mine)."""
    if cohort_id is not None:
        get_cohort_or_404(db, cohort_id)
    return notice_repo.list_for_cohort(db, cohort_id)


@router.get("/mine", response_model=list[NoticeFeedItem])
def list_my_notices(db: DB, user: Trainee):
    """The current trainee's notice feed, with `read_at` showing what they've acknowledged."""
    return [
        NoticeFeedItem(**Notice.model_validate(notice).model_dump(), read_at=read_at)
        for notice, read_at in notice_repo.list_feed(db, trainee_id=user.id, cohort_id=user.cohort_id)
    ]


@router.post("/{notice_id}/read", response_model=NoticeReadStatus)
def mark_notice_read(notice_id: str, db: DB, user: Trainee):
    """Acknowledge a notice as the current trainee (taken from the token, not the request body).

    Idempotent: repeat calls keep the first `read_at`.
    """
    notice = notice_repo.get(db, notice_id)
    if notice is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Notice '{notice_id}' not found")
    if notice.target_cohort_id not in (None, user.cohort_id):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Notice is not addressed to this trainee's cohort")

    receipt = notice_repo.mark_read(db, notice_id=notice_id, trainee_id=user.id, read_at=datetime.now(UTC))
    db.commit()
    return receipt
