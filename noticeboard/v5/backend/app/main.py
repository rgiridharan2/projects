import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import UTC, datetime

from fastapi import FastAPI
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import RedirectResponse

from app.config import settings
from app.db import SessionLocal
from app.routers import (
    audit,
    auth,
    cohorts,
    dashboard,
    escalations,
    milestones,
    notices,
    oversight,
    reminders,
    schedule,
    submissions,
)
from app.routers.escalations import run_escalations

log = logging.getLogger("noticeboard.escalations")


def escalation_check_once() -> None:
    with SessionLocal() as db:
        created = run_escalations(db, actor=None, now=datetime.now(UTC))  # actor None = "System" in the log
    if created:
        log.warning("Escalated %d task(s) more than 48 hours past deadline", created)


async def escalation_loop(interval_minutes: int) -> None:
    """Runs the escalation check at startup and then every few minutes, inside the API process.
    (A separate worker or a cron job would do this in production; see the README.)"""
    while True:
        try:
            await run_in_threadpool(escalation_check_once)  # the check uses blocking DB calls
        except Exception:  # keep the loop alive if the database is briefly unreachable
            log.exception("Escalation check failed")
        await asyncio.sleep(interval_minutes * 60)


@asynccontextmanager
async def lifespan(app: FastAPI):
    task = None
    if settings.escalation_interval_minutes > 0:
        task = asyncio.create_task(escalation_loop(settings.escalation_interval_minutes))
    yield
    if task:
        task.cancel()


app = FastAPI(
    title="NoticeBoardTracker API",
    version="0.5.0",
    description=(
        "Phase 5: audit log, escalations, cohort health, CSV import/export. Click **Authorize** and log "
        "in with an email or user id (demo password `password123`, e.g. `manager@edtech.com`), or call "
        "`POST /api/auth/login`."
    ),
    lifespan=lifespan,
)

app.include_router(auth.router)
app.include_router(cohorts.router)
app.include_router(oversight.router)
app.include_router(notices.router)
app.include_router(milestones.router)
app.include_router(schedule.router)
app.include_router(reminders.router)
app.include_router(escalations.router)
app.include_router(submissions.router)
app.include_router(dashboard.router)
app.include_router(audit.router)


@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse("/docs")
