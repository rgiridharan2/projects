from fastapi import FastAPI
from fastapi.responses import RedirectResponse

from app.routers import auth, cohorts, dashboard, milestones, notices, oversight, reminders, schedule, submissions

app = FastAPI(
    title="NoticeBoardTracker API",
    version="0.4.0",
    description=(
        "Phase 4: scheduling (timed deadlines, agenda), cohort matrix and nudges. Click **Authorize** and log "
        "in with an email or user id (demo password `password123`, e.g. `manager@edtech.com`), or call "
        "`POST /api/auth/login`."
    ),
)

app.include_router(auth.router)
app.include_router(cohorts.router)
app.include_router(oversight.router)
app.include_router(notices.router)
app.include_router(milestones.router)
app.include_router(schedule.router)
app.include_router(reminders.router)
app.include_router(submissions.router)
app.include_router(dashboard.router)


@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse("/docs")
