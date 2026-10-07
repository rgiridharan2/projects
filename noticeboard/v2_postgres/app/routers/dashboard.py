from datetime import UTC, datetime

from fastapi import APIRouter

from app.db import DB
from app.repositories import dashboard_repo
from app.schemas import DashboardStats

router = APIRouter(prefix="/api/dashboard", tags=["Dashboard"])


@router.get("/stats", response_model=DashboardStats)
def get_dashboard_stats(db: DB):
    """Headline numbers for the Training Manager dashboard."""
    return dashboard_repo.get_stats(db, now=datetime.now(UTC))
