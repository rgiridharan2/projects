from datetime import UTC, datetime, timedelta

import pytest

from app.repositories import cohort_repo, user_repo
from seed import seed


@pytest.fixture
def demo(db):
    """The full seed.py data set."""
    seed(db, now=datetime.now(UTC))
    db.commit()


def stats(client):
    resp = client.get("/api/dashboard/stats")
    assert resp.status_code == 200
    return resp.json()


def user_id(db, email):
    return user_repo.get_by_email(db, email).id


def test_stats_on_empty_database(client):
    assert stats(client) == {"total_active": 0, "at_risk": 0, "overdue_submissions": 0, "read_rates": 0.0}


@pytest.mark.usefixtures("demo")
def test_stats_on_seed_data(client):
    # 31 of 36 delivered notices read = 0.861
    assert stats(client) == {"total_active": 12, "at_risk": 2, "overdue_submissions": 4, "read_rates": 0.86}


@pytest.mark.usefixtures("demo")
def test_seed_cohort_sizes(client):
    counts = {c["name"]: c["trainee_count"] for c in client.get("/api/cohorts").json()}
    assert counts == {"Cloud Native Q4": 6, "Solo Track - Data": 1, "Full-Stack Foundations": 5}


@pytest.mark.usefixtures("demo")
def test_stats_follow_new_activity(client, db):
    tom = user_id(db, "tom.okafor@example.com")  # latest report stalled
    ethan = user_id(db, "ethan.brooks@example.com")  # never submitted, unread notices

    # A fresh report replaces Tom's stalled one as his latest.
    client.post("/api/submissions", json={"trainee_id": tom, "milestone_name": "Week 5: CI/CD pipelines"})
    # Ethan's first report means he's no longer overdue.
    client.post("/api/submissions", json={"trainee_id": ethan, "milestone_name": "Week 1: HTML & CSS"})
    # Ethan reads the welcome notice: 32 of 36.
    client.post("/api/notices/n1/read", json={"trainee_id": ethan})

    assert stats(client) == {"total_active": 12, "at_risk": 1, "overdue_submissions": 3, "read_rates": 0.89}


@pytest.mark.usefixtures("demo")
def test_manager_review_clears_at_risk(client, db):
    aisha = user_id(db, "aisha.khan@example.com")
    latest = next(s for s in client.get("/api/submissions").json() if s["trainee_id"] == aisha)
    assert latest["status"] == "stalled"

    client.patch(f"/api/submissions/{latest['id']}/status", json={"status": "on_track"})
    assert stats(client)["at_risk"] == 1


@pytest.mark.usefixtures("demo")
def test_cohorts_that_have_not_started_are_not_active(client, db):
    future = cohort_repo.create(
        db, name="Spring Cohort", track_type="group", start_date=(datetime.now(UTC) + timedelta(days=30)).date()
    )
    db.commit()
    client.post("/api/trainees", json={"name": "New Starter", "email": "new@example.com", "cohort_id": future.id})

    assert stats(client)["total_active"] == 12
