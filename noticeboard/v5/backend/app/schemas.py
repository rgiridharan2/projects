"""Pydantic data contracts.

Each *read* model (User, Cohort, Notice, NoticeReadStatus, Submission) mirrors a
table in app/models.py. Because they set `from_attributes=True`, routers can return
SQLAlchemy objects and FastAPI serializes them through these. Only the fields
declared here are sent, so `users.hashed_password` can never leak into a response.

*Input* models (…Create / …Update / LoginRequest) are the request bodies. They leave
out server-owned fields (id, role, timestamps) and reject unknown fields.
"""

from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    HttpUrl,
    StringConstraints,
    model_validator,
)

Role = Literal["manager", "trainee"]
TrackType = Literal["group", "solo"]
Priority = Literal["urgent", "standard"]
SubmissionStatus = Literal["on_track", "needs_review", "stalled"]
# A milestone as one trainee sees it, derived from their latest report for it (see milestone_repo).
TaskStatus = Literal["pending", "in_progress", "under_review", "completed"]

# Spaces in a password are significant, so this overrides InputModel's whitespace stripping.
# bcrypt only uses the first 72 bytes, so longer passwords are rejected rather than silently cut.
Password = Annotated[str, StringConstraints(strip_whitespace=False, min_length=8, max_length=72)]


class ReadModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class InputModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


# --- auth ----------------------------------------------------------------


class LoginRequest(BaseModel):
    # Not an InputModel: whitespace in a password is significant, so nothing here is stripped.
    model_config = ConfigDict(extra="forbid")

    identifier: str = Field(min_length=1, description="Email address or user id.", examples=["jane.doe@example.com"])
    password: str = Field(min_length=1, examples=["password123"])


class SignupRequest(InputModel):
    """Public sign-up. There is no role field: everyone who signs up is a trainee (extra fields get a 422)."""

    name: str = Field(min_length=1, max_length=100, examples=["Sam Lee"])
    email: EmailStr = Field(examples=["sam.lee@example.com"])
    password: Password = Field(examples=["password123"])
    cohort_id: str | None = Field(
        default=None, description="One of GET /api/cohorts/public-list, or null to be assigned later.", examples=["c1"]
    )


class User(ReadModel):
    id: str
    name: str
    email: EmailStr
    role: Role
    cohort_id: str | None  # FK -> cohorts.id; null for managers


class TokenResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    user: User


class SwitchOption(BaseModel):
    id: str
    name: str
    role: Role
    cohort_name: str | None


# --- users ---------------------------------------------------------------


class TraineeCreate(InputModel):
    name: str = Field(min_length=1, max_length=100, examples=["Sam Lee"])
    email: EmailStr = Field(examples=["sam.lee@example.com"])
    cohort_id: str = Field(examples=["c1"])
    initial_password: Password = Field(examples=["password123"])


# --- cohorts -------------------------------------------------------------


class Cohort(ReadModel):
    id: str
    name: str
    track_type: TrackType
    start_date: date
    open_for_signup: bool


class PublicCohort(BaseModel):
    """What the sign-up dropdown needs, and nothing more."""

    id: str
    name: str
    track_type: TrackType
    start_date: date


class CohortCreate(InputModel):
    name: str = Field(min_length=1, max_length=100, examples=["Spring Data Engineering"])
    track_type: TrackType = "group"
    start_date: date = Field(examples=["2026-11-02"])
    open_for_signup: bool = True


class Peer(BaseModel):
    id: str
    name: str


class MyCohort(BaseModel):
    cohort: Cohort | None  # null until the trainee is assigned to one
    peers: list[Peer]  # the other trainees in it


class CohortSummary(Cohort):
    trainee_count: int  # computed, not a column


# --- notices -------------------------------------------------------------


class Notice(ReadModel):
    id: str
    title: str
    body: str
    priority: Priority
    target_cohort_id: str | None  # FK -> cohorts.id; null = all trainees
    created_at: datetime


class NoticeFeedItem(Notice):
    read_at: datetime | None  # when the current trainee acknowledged it; null = not yet


class NoticeCreate(InputModel):
    title: str = Field(min_length=1, max_length=200, examples=["Lab environment maintenance"])
    body: str = Field(min_length=1, examples=["The k8s sandbox is down Friday 6-8pm."])
    priority: Priority = "standard"
    target_cohort_id: str | None = Field(
        default=None,
        description="Cohort to target, or null to send to all trainees.",
        examples=["c1"],
    )


class NoticeReadStatus(ReadModel):
    notice_id: str  # composite PK (notice_id, trainee_id)
    trainee_id: str
    read_at: datetime


# --- milestones (tasks) --------------------------------------------------


class Milestone(ReadModel):
    id: str
    cohort_id: str  # FK -> cohorts.id
    milestone_order: int  # 1, 2, 3... within the cohort
    title: str
    due_date: datetime  # ISO timestamp with a timezone, e.g. 2026-10-09T23:59:00Z


# Deadlines must say which timezone they're in, or "17:00" would mean different moments to different people.
DueDate = Annotated[AwareDatetime, Field(examples=["2026-11-06T17:00:00Z"])]


class MilestoneCreate(InputModel):
    cohort_id: str = Field(examples=["c1"])
    title: str = Field(min_length=1, max_length=200, examples=["Week 9: Capstone demo"])
    due_date: DueDate
    milestone_order: int | None = Field(
        default=None, ge=1, description="Position in the cohort's sequence. Omit to add it at the end."
    )


class DispatchAssignment(InputModel):
    cohort_id: str = Field(examples=["c1"])
    due_date: DueDate


class MilestoneDispatch(InputModel):
    """One task sent to several cohorts at once, each with its own deadline."""

    title: str = Field(min_length=1, max_length=200, examples=["Capstone demo day"])
    assignments: list[DispatchAssignment] = Field(min_length=1)

    @model_validator(mode="after")
    def one_assignment_per_cohort(self):
        cohort_ids = [a.cohort_id for a in self.assignments]
        if len(cohort_ids) != len(set(cohort_ids)):
            raise ValueError("Each cohort can only appear once")
        return self


class MyMilestone(Milestone):
    status: TaskStatus
    overdue: bool  # past due_date with no report yet
    last_submitted_at: datetime | None  # the trainee's latest report for this task, if any


# --- schedule (agenda) ---------------------------------------------------


class ScheduleBlock(ReadModel):
    id: str
    cohort_id: str
    milestone_id: str | None  # the module this session belongs to
    title: str
    starts_at: datetime
    ends_at: datetime


class ScheduleBlockCreate(InputModel):
    cohort_id: str = Field(examples=["c1"])
    milestone_id: str | None = Field(default=None, examples=["m6"])
    title: str = Field(min_length=1, max_length=200, examples=["Lab: Prometheus dashboards"])
    starts_at: AwareDatetime = Field(examples=["2026-10-07T13:00:00Z"])
    ends_at: AwareDatetime = Field(examples=["2026-10-07T15:00:00Z"])

    @model_validator(mode="after")
    def ends_after_it_starts(self):
        if self.ends_at <= self.starts_at:
            raise ValueError("ends_at must be after starts_at")
        return self


# --- reminders (nudges) --------------------------------------------------


class Reminder(ReadModel):
    id: str
    trainee_id: str
    milestone_id: str
    sent_by: str
    created_at: datetime
    dismissed_at: datetime | None


class MyReminder(Reminder):
    milestone_title: str
    due_date: datetime
    sender_name: str


class ReminderCreate(InputModel):
    trainee_id: str = Field(examples=["u7"])
    milestone_id: str = Field(examples=["m3"])


class NudgeAllResult(BaseModel):
    created: int  # new reminders sent
    already_nudged: int  # overdue tasks that still had an unread reminder, so were skipped


# --- cohort matrix (manager) ---------------------------------------------


class MatrixCell(BaseModel):
    milestone_id: str
    status: TaskStatus
    overdue: bool
    last_submitted_at: datetime | None
    nudged_at: datetime | None  # when the current, still-unread reminder was sent
    escalated: bool  # flagged by the 48-hour escalation check and not yet handed in


class MatrixRow(BaseModel):
    trainee: Peer
    overdue_count: int
    cells: list[MatrixCell]  # same order as CohortMatrix.milestones


class CohortMatrix(BaseModel):
    cohort: Cohort
    milestones: list[Milestone]
    rows: list[MatrixRow]
    overdue_total: int


# --- submissions ---------------------------------------------------------


class Submission(ReadModel):
    id: str
    trainee_id: str  # FK -> users.id
    milestone_id: str | None  # FK -> milestones.id
    milestone_name: str
    status: SubmissionStatus
    asset_url: str | None
    notes: str | None
    submitted_at: datetime


class SubmissionCreate(InputModel):
    trainee_id: str = Field(
        description="Must be your own id unless you're a manager.", examples=["u1"]
    )
    milestone_id: str | None = Field(
        default=None, description="The task this report is for. Must belong to the trainee's cohort.", examples=["m1"]
    )
    milestone_name: str | None = Field(
        default=None,
        min_length=1,
        max_length=200,
        description="Defaults to the milestone's title. Required for a free-form report with no milestone_id.",
    )
    status: SubmissionStatus = Field(
        default="needs_review", description="Self-reported progress; pick `stalled` if you're blocked."
    )
    asset_url: HttpUrl | None = Field(default=None, examples=["https://github.com/janedoe/docker-lab"])
    notes: str | None = Field(default=None, max_length=2000, examples=["Finished all exercises."])

    @model_validator(mode="after")
    def needs_milestone_or_name(self):
        if self.milestone_id is None and self.milestone_name is None:
            raise ValueError("Provide milestone_id, milestone_name, or both")
        return self


class SubmissionStatusUpdate(InputModel):
    status: SubmissionStatus


# --- bulk import -----------------------------------------------------------


class TraineeImportRequest(InputModel):
    csv: str = Field(
        min_length=1,
        max_length=200_000,
        description="CSV text with a header row: name,email,cohort_id (cohort_id may be blank).",
        examples=["name,email,cohort_id\nSam Lee,sam.lee@example.com,c1\nAna Ruiz,ana.ruiz@example.com,c3"],
    )
    dry_run: bool = Field(default=True, description="true = only validate and report; nothing is saved.")
    initial_password: Password | None = Field(default=None, description="Required to import; shared by the whole batch.")
    skip_invalid: bool = Field(default=False, description="Import the valid rows even if some rows have errors.")

    @model_validator(mode="after")
    def password_needed_to_import(self):
        if not self.dry_run and self.initial_password is None:
            raise ValueError("initial_password is required when dry_run is false")
        return self


class ImportRow(BaseModel):
    line: int  # line in the file (header = 1)
    name: str
    email: str
    cohort_id: str | None
    errors: list[str]  # empty = importable


class ImportReport(BaseModel):
    dry_run: bool
    rows: list[ImportRow]
    valid_count: int
    invalid_count: int
    created: list[User]  # empty for a dry run


# --- audit log ---------------------------------------------------------------


class AuditEntry(ReadModel):
    id: str
    actor_id: str | None
    actor_name: str | None  # null = the system (e.g. the background escalation check)
    action: str
    target_type: str
    target_id: str | None
    summary: str
    created_at: datetime


# --- escalations, health ----------------------------------------------------


class EscalationItem(BaseModel):
    id: str
    trainee_id: str
    trainee_name: str
    milestone_id: str
    milestone_title: str
    cohort_name: str
    due_date: datetime
    escalated_at: datetime


class EscalationRunResult(BaseModel):
    created: int  # newly flagged by this run
    active: int  # all unresolved escalations after the run


HealthStatus = Literal["healthy", "watch", "at_risk", "no_data"]


class CohortHealth(BaseModel):
    cohort: Cohort
    score: int | None = Field(description="0-100: 60% on-time submission rate + 40% notice read rate.")
    status: HealthStatus = Field(description="healthy >= 75, watch 60-74, at_risk < 60, no_data if nothing to measure.")
    on_time_rate: float | None
    read_rate: float | None
    trainees: int
    overdue: int
    stalled: int


# --- dashboard -----------------------------------------------------------


class DashboardStats(BaseModel):
    total_active: int = Field(description="Trainees in a cohort that has already started.")
    at_risk: int = Field(description="Active trainees whose latest submission is `stalled`.")
    overdue_submissions: int = Field(
        description="Tasks past their due date that an active trainee hasn't submitted anything for "
        "(one per trainee per task)."
    )
    read_rates: float = Field(
        description="Share of notices delivered to active trainees that have been read, 0-1 (two decimals)."
    )
