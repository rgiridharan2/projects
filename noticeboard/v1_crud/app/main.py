from fastapi import FastAPI
from fastapi.responses import RedirectResponse

from app.routers import cohorts, notices, submissions

app = FastAPI(
    title="NoticeBoardTracker API",
    version="0.1.0",
    description="Phase 1: core CRUD on an in-memory store. Data resets when the server restarts.",
)

app.include_router(cohorts.router)
app.include_router(notices.router)
app.include_router(submissions.router)


@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse("/docs")
