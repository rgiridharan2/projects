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

from pydantic import BaseModel, ConfigDict, EmailStr, Field, HttpUrl, StringConstraints

Role = Literal["manager", "trainee"]
TrackType = Literal["group", "solo"]
Priority = Literal["urgent", "standard"]
SubmissionStatus = Literal["on_track", "needs_review", "stalled"]

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


# --- submissions ---------------------------------------------------------


class Submission(ReadModel):
    id: str
    trainee_id: str  # FK -> users.id
    milestone_name: str
    status: SubmissionStatus
    asset_url: str | None
    notes: str | None
    submitted_at: datetime


class SubmissionCreate(InputModel):
    trainee_id: str = Field(
        description="Must be your own id unless you're a manager.", examples=["u1"]
    )
    milestone_name: str = Field(min_length=1, max_length=200, examples=["Week 1: Docker basics"])
    status: SubmissionStatus = Field(
        default="needs_review", description="Self-reported progress; pick `stalled` if you're blocked."
    )
    asset_url: HttpUrl | None = Field(default=None, examples=["https://github.com/janedoe/docker-lab"])
    notes: str | None = Field(default=None, max_length=2000, examples=["Finished all exercises."])


class SubmissionStatusUpdate(InputModel):
    status: SubmissionStatus


# --- dashboard -----------------------------------------------------------


class DashboardStats(BaseModel):
    total_active: int = Field(description="Trainees in a cohort that has already started.")
    at_risk: int = Field(description="Active trainees whose latest submission is `stalled`.")
    overdue_submissions: int = Field(
        description="Active trainees with no submission in the last 7 days "
        "(or none at all, once their cohort is more than 7 days old)."
    )
    read_rates: float = Field(
        description="Share of notices delivered to active trainees that have been read, 0-1 (two decimals)."
    )
