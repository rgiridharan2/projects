from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Query, status

from app import data
from app.lookups import get_cohort_or_404, get_trainee_or_404
from app.schemas import Submission, SubmissionCreate, SubmissionStatusUpdate

router = APIRouter(prefix="/api/submissions", tags=["Submissions"])


@router.post("", response_model=Submission, status_code=status.HTTP_201_CREATED)
def create_submission(payload: SubmissionCreate):
    """Trainee logs a milestone report. New reports start as `needs_review`."""
    get_trainee_or_404(payload.trainee_id)

    submission = {
        "id": data.next_id("s", data.SUBMISSIONS),
        "trainee_id": payload.trainee_id,
        "milestone_name": payload.milestone_name,
        "status": "needs_review",
        "asset_url": str(payload.asset_url) if payload.asset_url else None,
        "notes": payload.notes,
        "submitted_at": datetime.now(UTC),
    }
    data.SUBMISSIONS[submission["id"]] = submission
    return submission


@router.get("", response_model=list[Submission])
def list_submissions(
    cohort_id: str | None = Query(
        default=None,
        description="Only submissions from trainees in this cohort. Omit to list every submission.",
    ),
):
    """Recent submissions, newest first."""
    submissions = list(data.SUBMISSIONS.values())
    if cohort_id is not None:
        get_cohort_or_404(cohort_id)
        roster = {u["id"] for u in data.USERS.values() if u["cohort_id"] == cohort_id}
        submissions = [s for s in submissions if s["trainee_id"] in roster]

    return sorted(submissions, key=lambda s: s["submitted_at"], reverse=True)


@router.patch("/{submission_id}/status", response_model=Submission)
def update_submission_status(submission_id: str, payload: SubmissionStatusUpdate):
    """Manager sets the review status of a submission."""
    submission = data.SUBMISSIONS.get(submission_id)
    if submission is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Submission '{submission_id}' not found")

    submission["status"] = payload.status
    return submission
