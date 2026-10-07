from datetime import UTC, datetime, timedelta

import pytest

from app.repositories import cohort_repo, user_repo
from app.security import hash_password
from seed import seed


@pytest.fixture
def demo(db):
    """The full seed.py data set."""
    seed(db, now=datetime.now(UTC))
    db.commit()


@pytest.fixture
def manager(demo, client_as):
    """Alex, the seed's manager (overrides the conftest fixture, which uses the smaller v1 seed)."""
    return client_as("gandalf.grey@example.com")


def stats(manager):
    resp = manager.get("/api/dashboard/stats")
    assert resp.status_code == 200
    return resp.json()


def user_id(db, email):
    return user_repo.get_by_email(db, email).id


def test_stats_on_empty_database(db, client_as):
    # The dashboard needs a manager to log in, so this "empty" database has just that one account.
    user_repo.create(
        db, name="M", email="m@example.com", role="manager", cohort_id=None, hashed_password=hash_password("password123")
    )
    db.commit()
    assert stats(client_as("m@example.com")) == {
        "total_active": 0,
        "at_risk": 0,
        "overdue_submissions": 0,
        "read_rates": 0.0,
    }


def test_stats_on_seed_data(manager):
    # Overdue = past-deadline tasks with no report: Peregrin 1, Aragorn 2, Legolas 3, Eomer 1, Gollum 2.
    # Read rate: 31 of 36 delivered notices = 0.861.
    assert stats(manager) == {"total_active": 12, "at_risk": 2, "overdue_submissions": 9, "read_rates": 0.86}


def test_seed_cohort_sizes(manager):
    counts = {c["name"]: c["trainee_count"] for c in manager.get("/api/cohorts").json()}
    assert counts == {"Cloud Native Q4": 6, "Solo Track - Data": 1, "Full-Stack Foundations": 5}


def test_every_seed_account_can_log_in(manager, client_as):
    options = manager.get("/api/users/switch-options").json()
    assert len(options) == 14  # 12 trainees + 2 managers
    for option in options:
        assert client_as(option["id"]).get("/api/auth/me").json()["id"] == option["id"]


@pytest.mark.usefixtures("demo")
def test_seed_gives_jane_a_realistic_task_list(client_as):
    jane = client_as("frodo.baggins@example.com")
    mine = jane.get("/api/milestones/mine").json()
    assert [m["milestone_order"] for m in mine] == list(range(1, 9))
    assert [m["status"] for m in mine] == ["completed"] * 4 + ["under_review"] + ["pending"] * 3
    assert not any(m["overdue"] for m in mine)
    # Week 6 is due at 23:59 today, local time.
    due = datetime.fromisoformat(mine[5]["due_date"]).astimezone()
    assert (due.date(), due.strftime("%H:%M")) == (datetime.now().astimezone().date(), "23:59")
    assert [p["name"] for p in jane.get("/api/cohorts/mine").json()["peers"]] == [
        "Aragorn son of Arathorn", "Legolas Greenleaf", "Meriadoc Brandybuck", "Peregrin Took", "Samwise Gamgee"
    ]


@pytest.mark.usefixtures("demo")
def test_seed_manager_account_from_the_brief_works(client_as):
    morgan = client_as("manager@edtech.com")
    assert morgan.get("/api/auth/me").json()["role"] == "manager"
    assert morgan.get("/api/dashboard/stats").status_code == 200


def test_stats_follow_new_activity(manager, client_as):
    tom = client_as("peregrin.took@example.com")  # latest report stalled
    ethan = client_as("gollum.smeagol@example.com")  # never submitted, unread notices
    tom_id, ethan_id = tom.get("/api/auth/me").json()["id"], ethan.get("/api/auth/me").json()["id"]

    # Tom hands in his overdue Week 5 (m5): his latest report is no longer stalled, and one fewer overdue task.
    tom.post("/api/submissions", json={"trainee_id": tom_id, "milestone_id": "m5"})
    # Ethan hands in his overdue Week 1 (m15): one fewer overdue task.
    ethan.post("/api/submissions", json={"trainee_id": ethan_id, "milestone_id": "m15"})
    # Ethan reads the welcome notice: 32 of 36.
    ethan.post("/api/notices/n1/read")

    assert stats(manager) == {"total_active": 12, "at_risk": 1, "overdue_submissions": 7, "read_rates": 0.89}


def test_a_trainee_self_reporting_stalled_is_at_risk(manager, client_as):
    jane = client_as("frodo.baggins@example.com")
    jane.post("/api/submissions", json={"trainee_id": "u1", "milestone_name": "Week 6", "status": "stalled"})
    assert stats(manager)["at_risk"] == 3


def test_manager_review_clears_at_risk(manager, db):
    aisha = user_id(db, "gimli.son.of.gloin@example.com")
    latest = next(s for s in manager.get("/api/submissions").json() if s["trainee_id"] == aisha)
    assert latest["status"] == "stalled"

    manager.patch(f"/api/submissions/{latest['id']}/status", json={"status": "on_track"})
    assert stats(manager)["at_risk"] == 1


def test_cohorts_that_have_not_started_are_not_active(manager, db):
    future = cohort_repo.create(
        db, name="Spring Cohort", track_type="group", start_date=(datetime.now(UTC) + timedelta(days=30)).date()
    )
    db.commit()
    body = {"name": "New Starter", "email": "new@example.com", "cohort_id": future.id, "initial_password": "password123"}
    assert manager.post("/api/trainees", json=body).status_code == 201

    assert stats(manager)["total_active"] == 12
