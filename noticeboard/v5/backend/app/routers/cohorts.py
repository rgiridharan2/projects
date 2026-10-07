from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Response, status

from app.auth import CurrentUser, Manager, Trainee
from app.db import DB
from app.lookups import get_cohort_or_404
from app.repositories import audit_repo, cohort_repo, user_repo
from app.schemas import (
    Cohort,
    CohortCreate,
    CohortSummary,
    ImportReport,
    MyCohort,
    PublicCohort,
    TraineeCreate,
    TraineeImportRequest,
    User,
)
from app.security import hash_password
from app.services.trainee_import import CsvFormatError, parse_and_validate

router = APIRouter(prefix="/api", tags=["Cohorts & Trainees"])


@router.get("/cohorts", response_model=list[CohortSummary])
def list_cohorts(db: DB, user: CurrentUser):
    """List all cohorts with how many trainees each one has. Any logged-in user."""
    return [
        CohortSummary(**Cohort.model_validate(cohort).model_dump(), trainee_count=count)
        for cohort, count in cohort_repo.list_with_trainee_counts(db)
    ]


@router.get("/cohorts/public-list", response_model=list[PublicCohort])
def list_public_cohorts(db: DB):
    """Cohorts that accept sign-ups, for the registration dropdown. Public."""
    return cohort_repo.list_open_for_signup(db)


@router.get("/cohorts/mine", response_model=MyCohort)
def read_my_cohort(db: DB, user: Trainee):
    """The current trainee's cohort and the other trainees in it."""
    if user.cohort_id is None:
        return {"cohort": None, "peers": []}
    return {
        "cohort": cohort_repo.get(db, user.cohort_id),
        "peers": user_repo.list_peers(db, cohort_id=user.cohort_id, exclude_id=user.id),
    }


@router.post("/cohorts", response_model=Cohort, status_code=status.HTTP_201_CREATED)
def create_cohort(payload: CohortCreate, db: DB, user: Manager):
    """Create a cohort. Managers only. Set `open_for_signup: false` to keep it out of public sign-up."""
    cohort = cohort_repo.create(db, **payload.model_dump())
    audit_repo.record(
        db,
        actor=user,
        action="cohort.created",
        target_type="cohort",
        target_id=cohort.id,
        summary=f"Created cohort {cohort.name} ({'open' if cohort.open_for_signup else 'closed'} for sign-up)",
        at=datetime.now(UTC),
    )
    db.commit()
    return cohort


@router.get("/cohorts/{cohort_id}/trainees", response_model=list[User])
def list_cohort_trainees(cohort_id: str, db: DB, user: Manager):
    """Roster of trainees in one cohort, by name. Managers only."""
    get_cohort_or_404(db, cohort_id)
    return user_repo.list_trainees(db, cohort_id)


@router.post("/trainees", response_model=User, status_code=status.HTTP_201_CREATED)
def create_trainee(payload: TraineeCreate, db: DB, user: Manager):
    """Onboard a trainee with an initial password. Managers only. Emails are unique (case-insensitive)."""
    cohort = get_cohort_or_404(db, payload.cohort_id)
    if user_repo.get_by_email(db, payload.email) is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, f"A user with email '{payload.email.lower()}' already exists")

    trainee = user_repo.create(
        db,
        name=payload.name,
        email=payload.email,
        role="trainee",
        cohort_id=payload.cohort_id,
        hashed_password=hash_password(payload.initial_password),
    )
    audit_repo.record(
        db,
        actor=user,
        action="trainee.onboarded",
        target_type="user",
        target_id=trainee.id,
        summary=f"Onboarded {trainee.name} into {cohort.name}",
        at=datetime.now(UTC),
    )
    db.commit()
    return trainee


@router.post("/trainees/import", response_model=ImportReport)
def import_trainees(payload: TraineeImportRequest, db: DB, user: Manager, response: Response):
    """Bulk-onboard trainees from CSV (name,email,cohort_id). Managers only.

    1. Send it with `dry_run: true` (the default) to get a row-by-row report: invalid emails, emails
       that already have an account, duplicates inside the file, unknown cohorts. Nothing is saved.
    2. Send it again with `dry_run: false` and an `initial_password` to import. Every row is validated
       again first. If any row has errors the import is refused, unless `skip_invalid: true`, in which
       case only the valid rows are imported. Either way it's one transaction.
    """
    try:
        rows = parse_and_validate(db, payload.csv)
    except CsvFormatError as error:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(error))
    valid = [row for row in rows if not row["errors"]]
    report = {"dry_run": payload.dry_run, "rows": rows, "valid_count": len(valid), "invalid_count": len(rows) - len(valid), "created": []}
    if payload.dry_run:
        return report

    if report["invalid_count"] and not payload.skip_invalid:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"{report['invalid_count']} row(s) have errors. Fix them, or set skip_invalid to import only the valid rows.",
        )
    if not valid:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "No valid rows to import")

    hashed = hash_password(payload.initial_password)  # one bcrypt hash for the whole batch
    report["created"] = [
        user_repo.create(db, name=row["name"], email=row["email"], role="trainee", cohort_id=row["cohort_id"], hashed_password=hashed)
        for row in valid
    ]
    skipped = f", skipped {report['invalid_count']} invalid row(s)" if report["invalid_count"] else ""
    audit_repo.record(
        db,
        actor=user,
        action="trainees.imported",
        target_type="user",
        target_id=None,
        summary=f"Imported {len(valid)} trainee{'s' if len(valid) != 1 else ''} from CSV{skipped}",
        at=datetime.now(UTC),
    )
    db.commit()
    response.status_code = status.HTTP_201_CREATED
    return report
