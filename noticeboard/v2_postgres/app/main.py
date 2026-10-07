from fastapi import FastAPI
from fastapi.responses import RedirectResponse

from app.routers import cohorts, dashboard, notices, submissions

app = FastAPI(
    title="NoticeBoardTracker API",
    version="0.2.0",
    description="Phase 2: PostgreSQL via SQLAlchemy, Alembic migrations, and a manager dashboard.",
)

app.include_router(cohorts.router)
app.include_router(notices.router)
app.include_router(submissions.router)
app.include_router(dashboard.router)


@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse("/docs")
