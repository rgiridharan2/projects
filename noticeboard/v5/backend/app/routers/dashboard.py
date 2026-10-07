from datetime import UTC, datetime

from fastapi import APIRouter

from app.auth import Manager
from app.db import DB
from app.repositories import dashboard_repo
from app.schemas import DashboardStats

router = APIRouter(prefix="/api/dashboard", tags=["Dashboard"])


@router.get("/stats", response_model=DashboardStats)
def get_dashboard_stats(db: DB, user: Manager):
    """Headline numbers for the Training Manager dashboard. Managers only."""
    return dashboard_repo.get_stats(db, now=datetime.now(UTC))
