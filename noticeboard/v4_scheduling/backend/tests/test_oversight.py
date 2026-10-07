"""The cohort matrix (overdue tracking) and nudges (reminders for overdue tasks)."""

from datetime import UTC, datetime, timedelta

import pytest

pytestmark = pytest.mark.usefixtures("v1_seed")  # c1, c2, u1 Jane (c1), u2 Alex (manager)


def due_in(days: float) -> str:
    return (datetime.now(UTC) + timedelta(days=days)).isoformat()


@pytest.fixture
def setup(manager, jane, client_as):
    """c1 has Jane (u1) and Sam (u3) and three tasks: m1 and m2 are past due, m3 isn't due yet.
    Jane has handed in m1. Returns Sam's client."""
    sam = {"name": "Sam Lee", "email": "sam@example.com", "cohort_id": "c1", "initial_password": "password123"}
    assert manager.post("/api/trainees", json=sam).json()["id"] == "u3"
    for title, due in [("Week 1", due_in(-3)), ("Week 2", due_in(-1)), ("Week 3", due_in(5))]:
        manager.post("/api/milestones", json={"cohort_id": "c1", "title": title, "due_date": due})
    jane.post("/api/submissions", json={"trainee_id": "u1", "milestone_id": "m1"})
    return client_as("sam@example.com")


def matrix(manager):
    resp = manager.get("/api/cohorts/c1/matrix")
    assert resp.status_code == 200
    return resp.json()


def cells(m, name):
    row = next(r for r in m["rows"] if r["trainee"]["name"] == name)
    return {c["milestone_id"]: c for c in row["cells"]}


def nudge(manager, trainee_id, milestone_id):
    return manager.post("/api/reminders", json={"trainee_id": trainee_id, "milestone_id": milestone_id})


# --- matrix ---------------------------------------------------------------


@pytest.mark.usefixtures("setup")
def test_matrix_computes_overdue_from_deadlines(manager):
    m = matrix(manager)
    assert [ms["id"] for ms in m["milestones"]] == ["m1", "m2", "m3"]
    assert [(r["trainee"]["name"], r["overdue_count"]) for r in m["rows"]] == [("Jane Doe", 1), ("Sam Lee", 2)]
    assert m["overdue_total"] == 3

    jane = cells(m, "Jane Doe")
    assert (jane["m1"]["status"], jane["m1"]["overdue"]) == ("under_review", False)  # handed in, even if late
    assert (jane["m2"]["status"], jane["m2"]["overdue"]) == ("pending", True)
    assert (jane["m3"]["status"], jane["m3"]["overdue"]) == ("pending", False)  # not due yet
    assert jane["m1"]["last_submitted_at"] is not None


def test_stalled_work_is_at_risk_not_overdue(manager, jane, setup):
    jane.post("/api/submissions", json={"trainee_id": "u1", "milestone_id": "m2", "status": "stalled"})
    m2 = cells(matrix(manager), "Jane Doe")["m2"]
    assert (m2["status"], m2["overdue"]) == ("in_progress", False)


@pytest.mark.usefixtures("setup")
def test_dashboard_overdue_matches_the_matrix(manager):
    assert manager.get("/api/dashboard/stats").json()["overdue_submissions"] == matrix(manager)["overdue_total"] == 3


def test_matrix_for_an_empty_cohort(manager):
    assert manager.get("/api/cohorts/c2/matrix").json()["rows"] == []
    assert manager.get("/api/cohorts/c9/matrix").status_code == 404


# --- nudging one task ---------------------------------------------------------


@pytest.mark.usefixtures("setup")
def test_nudge_an_overdue_task(manager):
    resp = nudge(manager, "u3", "m1")
    assert resp.status_code == 201
    assert (resp.json()["trainee_id"], resp.json()["sent_by"], resp.json()["dismissed_at"]) == ("u3", "u2", None)
    assert cells(matrix(manager), "Sam Lee")["m1"]["nudged_at"] is not None

    again = nudge(manager, "u3", "m1")
    assert again.status_code == 409  # one unread reminder per task is enough


@pytest.mark.usefixtures("setup")
@pytest.mark.parametrize(
    ("trainee_id", "milestone_id", "status"),
    [
        ("u3", "m3", 400),  # not due yet
        ("u1", "m1", 400),  # Jane already handed it in
        ("u1", "m99", 404),  # no such task
        ("u2", "m1", 404),  # Alex is a manager, not a trainee
    ],
)
def test_only_overdue_tasks_can_be_nudged(manager, trainee_id, milestone_id, status):
    assert nudge(manager, trainee_id, milestone_id).status_code == status


def test_cannot_nudge_about_another_cohorts_task(manager, setup):
    manager.post("/api/milestones", json={"cohort_id": "c2", "title": "Other", "due_date": due_in(-2)})  # m4
    assert nudge(manager, "u3", "m4").status_code == 404


# --- nudging everyone ---------------------------------------------------------


@pytest.mark.usefixtures("setup")
def test_nudge_all_skips_tasks_already_nudged(manager):
    nudge(manager, "u3", "m1")
    resp = manager.post("/api/cohorts/c1/nudges")
    assert resp.status_code == 200
    assert resp.json() == {"created": 2, "already_nudged": 1}  # Jane m2 and Sam m2 are new
    assert manager.post("/api/cohorts/c1/nudges").json() == {"created": 0, "already_nudged": 3}


# --- the trainee's side -------------------------------------------------------


def test_trainee_sees_and_dismisses_their_reminders(manager, jane, setup):
    sam = setup
    manager.post("/api/cohorts/c1/nudges")

    mine = sam.get("/api/reminders/mine").json()
    # Both were sent in the same instant, so compare them in a fixed order.
    assert sorted((r["milestone_title"], r["sender_name"]) for r in mine) == [("Week 1", "Alex Smith"), ("Week 2", "Alex Smith")]
    assert all(r["due_date"] for r in mine)

    first = mine[0]["id"]
    assert jane.post(f"/api/reminders/{first}/dismiss").status_code == 404  # not Jane's
    assert sam.post(f"/api/reminders/{first}/dismiss").json()["dismissed_at"] is not None
    assert sam.post(f"/api/reminders/{first}/dismiss").status_code == 200  # idempotent
    assert len(sam.get("/api/reminders/mine").json()) == 1


def test_handing_in_the_task_clears_its_reminder(manager, setup):
    sam = setup
    nudge(manager, "u3", "m2")
    sam.post("/api/submissions", json={"trainee_id": "u3", "milestone_id": "m2"})

    assert sam.get("/api/reminders/mine").json() == []
    m2 = cells(matrix(manager), "Sam Lee")["m2"]
    assert (m2["overdue"], m2["nudged_at"]) == (False, None)
    assert nudge(manager, "u3", "m2").status_code == 400  # no longer overdue
