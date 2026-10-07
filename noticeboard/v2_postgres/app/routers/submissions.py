from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Query, status

from app.db import DB
from app.lookups import get_cohort_or_404, get_trainee_or_404
from app.repositories import submission_repo
from app.schemas import Submission, SubmissionCreate, SubmissionStatusUpdate

router = APIRouter(prefix="/api/submissions", tags=["Submissions"])


@router.post("", response_model=Submission, status_code=status.HTTP_201_CREATED)
def create_submission(payload: SubmissionCreate, db: DB):
    """Trainee logs a milestone report. New reports start as `needs_review`."""
    get_trainee_or_404(db, payload.trainee_id)

    submission = submission_repo.create(
        db,
        trainee_id=payload.trainee_id,
        milestone_name=payload.milestone_name,
        status="needs_review",
        asset_url=str(payload.asset_url) if payload.asset_url else None,
        notes=payload.notes,
        submitted_at=datetime.now(UTC),
    )
    db.commit()
    return submission


@router.get("", response_model=list[Submission])
def list_submissions(
    db: DB,
    cohort_id: str | None = Query(
        default=None,
        description="Only submissions from trainees in this cohort. Omit to list every submission.",
    ),
    limit: int = Query(default=50, ge=1, le=200, description="Maximum number of submissions to return."),
):
    """Recent submissions, newest first."""
    if cohort_id is not None:
        get_cohort_or_404(db, cohort_id)
    return submission_repo.list_recent(db, cohort_id=cohort_id, limit=limit)


@router.patch("/{submission_id}/status", response_model=Submission)
def update_submission_status(submission_id: str, payload: SubmissionStatusUpdate, db: DB):
    """Manager sets the review status of a submission."""
    submission = submission_repo.get(db, submission_id)
    if submission is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Submission '{submission_id}' not found")

    submission_repo.set_status(db, submission, payload.status)
    db.commit()
    return submission
