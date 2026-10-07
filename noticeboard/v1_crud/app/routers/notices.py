from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Query, status

from app import data
from app.lookups import get_cohort_or_404, get_trainee_or_404
from app.schemas import Notice, NoticeCreate, NoticeReadCreate, NoticeReadStatus

router = APIRouter(prefix="/api/notices", tags=["Notices"])


@router.post("", response_model=Notice, status_code=status.HTTP_201_CREATED)
def create_notice(payload: NoticeCreate):
    """Post a notice to one cohort, or to all trainees when `target_cohort_id` is null."""
    if payload.target_cohort_id is not None:
        get_cohort_or_404(payload.target_cohort_id)

    notice = {
        "id": data.next_id("n", data.NOTICES),
        **payload.model_dump(),
        "created_at": datetime.now(UTC),
    }
    data.NOTICES[notice["id"]] = notice
    return notice


@router.get("", response_model=list[Notice])
def list_notices(
    cohort_id: str | None = Query(
        default=None,
        description="Return this cohort's notices plus global ones. Omit to list every notice.",
    ),
):
    """Notices applicable to a cohort, urgent first, then newest first."""
    notices = list(data.NOTICES.values())
    if cohort_id is not None:
        get_cohort_or_404(cohort_id)
        notices = [n for n in notices if n["target_cohort_id"] in (None, cohort_id)]

    newest_first = sorted(notices, key=lambda n: n["created_at"], reverse=True)
    return sorted(newest_first, key=lambda n: n["priority"] != "urgent")


@router.post("/{notice_id}/read", response_model=NoticeReadStatus)
def mark_notice_read(notice_id: str, payload: NoticeReadCreate):
    """Mark a notice as read by a trainee. Idempotent: repeat calls keep the first `read_at`."""
    notice = data.NOTICES.get(notice_id)
    if notice is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Notice '{notice_id}' not found")
    trainee = get_trainee_or_404(payload.trainee_id)
    if notice["target_cohort_id"] not in (None, trainee["cohort_id"]):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Notice is not addressed to this trainee's cohort")

    key = (notice_id, trainee["id"])
    if key not in data.NOTICE_READS:
        data.NOTICE_READS[key] = {"notice_id": notice_id, "trainee_id": trainee["id"], "read_at": datetime.now(UTC)}
    return data.NOTICE_READS[key]
