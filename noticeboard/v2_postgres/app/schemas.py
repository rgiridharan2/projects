"""Pydantic data contracts (unchanged from v1 apart from DashboardStats).

Each *read* model (User, Cohort, Notice, NoticeReadStatus, Submission) mirrors a
table in app/models.py column-for-column. Because they set `from_attributes=True`,
routers can return SQLAlchemy objects and FastAPI serializes them through these.

*Input* models (…Create / …Update) are the request bodies. They leave out
server-owned fields (id, role, status, timestamps) and reject unknown fields.
"""

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, HttpUrl

Role = Literal["manager", "trainee"]
TrackType = Literal["group", "solo"]
Priority = Literal["urgent", "standard"]
SubmissionStatus = Literal["on_track", "needs_review", "stalled"]


class ReadModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class InputModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


# --- users ---------------------------------------------------------------


class User(ReadModel):
    id: str
    name: str
    email: EmailStr
    role: Role
    cohort_id: str | None  # FK -> cohorts.id; null for managers


class TraineeCreate(InputModel):
    name: str = Field(min_length=1, max_length=100, examples=["Sam Lee"])
    email: EmailStr = Field(examples=["sam.lee@example.com"])
    cohort_id: str = Field(examples=["c1"])


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


class NoticeReadCreate(InputModel):
    trainee_id: str = Field(examples=["u1"])


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
    trainee_id: str = Field(examples=["u1"])
    milestone_name: str = Field(min_length=1, max_length=200, examples=["Week 1: Docker basics"])
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
