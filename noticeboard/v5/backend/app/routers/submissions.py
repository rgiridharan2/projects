from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Query, status

from app.auth import CurrentUser, Manager, Trainee, ensure_owner_or_manager
from app.db import DB
from app.lookups import get_cohort_or_404, get_trainee_or_404
from app.repositories import audit_repo, escalation_repo, milestone_repo, reminder_repo, submission_repo, user_repo
from app.schemas import Submission, SubmissionCreate, SubmissionStatusUpdate

router = APIRouter(prefix="/api/submissions", tags=["Submissions"])


@router.post("", response_model=Submission, status_code=status.HTTP_201_CREATED)
def create_submission(payload: SubmissionCreate, db: DB, user: CurrentUser):
    """Log a milestone report. Trainees can only submit for themselves; managers can submit for anyone.

    Pass `milestone_id` to report on an assigned task (its title becomes the default `milestone_name`).
    """
    ensure_owner_or_manager(user, payload.trainee_id)
    trainee = get_trainee_or_404(db, payload.trainee_id)

    milestone = None
    if payload.milestone_id is not None:
        milestone = milestone_repo.get(db, payload.milestone_id)
        if milestone is None or milestone.cohort_id != trainee.cohort_id:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "That milestone isn't assigned to this trainee's cohort")

    now = datetime.now(UTC)
    submission = submission_repo.create(
        db,
        trainee_id=payload.trainee_id,
        milestone_id=payload.milestone_id,
        milestone_name=payload.milestone_name or milestone.title,
        status=payload.status,
        asset_url=str(payload.asset_url) if payload.asset_url else None,
        notes=payload.notes,
        submitted_at=now,
    )
    if milestone is not None:
        # The task is handed in, so any "you're overdue" nudges about it are done with.
        reminder_repo.dismiss_for_task(db, trainee_id=trainee.id, milestone_id=milestone.id, at=now)
        escalation_repo.resolve_for_task(db, trainee_id=trainee.id, milestone_id=milestone.id, at=now)
    db.commit()
    return submission


@router.get("", response_model=list[Submission])
def list_submissions(
    db: DB,
    user: Manager,
    cohort_id: str | None = Query(
        default=None,
        description="Only submissions from trainees in this cohort. Omit to list every submission.",
    ),
    limit: int = Query(default=50, ge=1, le=200, description="Maximum number of submissions to return."),
):
    """Recent submissions across trainees, newest first. Managers only (trainees use /mine)."""
    if cohort_id is not None:
        get_cohort_or_404(db, cohort_id)
    return submission_repo.list_recent(db, cohort_id=cohort_id, limit=limit)


@router.get("/mine", response_model=list[Submission])
def list_my_submissions(db: DB, user: Trainee):
    """The current trainee's own submissions, newest first."""
    return submission_repo.list_for_trainee(db, user.id)


@router.patch("/{submission_id}/status", response_model=Submission)
def update_submission_status(submission_id: str, payload: SubmissionStatusUpdate, db: DB, user: CurrentUser):
    """Change a submission's status. Managers can review anyone's; trainees can only update their own."""
    submission = submission_repo.get(db, submission_id)
    if submission is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Submission '{submission_id}' not found")
    ensure_owner_or_manager(user, submission.trainee_id)

    previous = submission.status
    submission_repo.set_status(db, submission, payload.status)
    if payload.status != previous:
        owner = "their own" if user.id == submission.trainee_id else f"{user_repo.get(db, submission.trainee_id).name}'s"
        signed_off = payload.status == "on_track" and user.role == "manager"
        audit_repo.record(
            db,
            actor=user,
            action="submission.signed_off" if signed_off else "submission.status_changed",
            target_type="submission",
            target_id=submission.id,
            summary=(
                f"Signed off {owner} report for {submission.milestone_name}"
                if signed_off
                else f"Changed {owner} report for {submission.milestone_name} from {previous} to {payload.status}"
            ),
            at=datetime.now(UTC),
        )
    db.commit()
    return submission
