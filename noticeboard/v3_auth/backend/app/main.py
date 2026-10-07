from fastapi import FastAPI
from fastapi.responses import RedirectResponse

from app.routers import auth, cohorts, dashboard, notices, submissions

app = FastAPI(
    title="NoticeBoardTracker API",
    version="0.3.0",
    description=(
        "Phase 3: JWT authentication and role-based access. Click **Authorize** and log in with an "
        "email or user id (demo password `password123`), or call `POST /api/auth/login`."
    ),
)

app.include_router(auth.router)
app.include_router(cohorts.router)
app.include_router(notices.router)
app.include_router(submissions.router)
app.include_router(dashboard.router)


@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse("/docs")
