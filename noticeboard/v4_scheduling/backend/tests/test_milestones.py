"""Milestones (tasks with due dates) and how each trainee's task status is derived."""

from datetime import UTC, datetime, timedelta

import pytest

pytestmark = pytest.mark.usefixtures("v1_seed")  # c1, c2, u1 Jane (c1), u2 Alex (manager)


def due_in(days: float) -> str:
    """An ISO deadline relative to now, so "overdue" doesn't depend on when the tests run."""
    return (datetime.now(UTC) + timedelta(days=days)).isoformat()


@pytest.fixture
def tasks(manager):
    """Three c1 milestones (m1 overdue, m2-m3 upcoming) and one c2 milestone (m4)."""
    for cohort_id, title, due in [
        ("c1", "Week 1: Linux", due_in(-3)),
        ("c1", "Week 2: Docker", due_in(4)),
        ("c1", "Week 3: Kubernetes", due_in(11)),
        ("c2", "Week 1: SQL", due_in(-3)),
    ]:
        assert manager.post("/api/milestones", json={"cohort_id": cohort_id, "title": title, "due_date": due}).status_code == 201


def report(client, milestone_id, status="needs_review"):
    resp = client.post("/api/submissions", json={"trainee_id": "u1", "milestone_id": milestone_id, "status": status})
    assert resp.status_code == 201, resp.text
    return resp.json()


def statuses(jane):
    return {m["id"]: m["status"] for m in jane.get("/api/milestones/mine").json()}


def test_managers_list_milestones_by_cohort(manager, tasks):
    assert [m["id"] for m in manager.get("/api/milestones", params={"cohort_id": "c1"}).json()] == ["m1", "m2", "m3"]
    assert len(manager.get("/api/milestones").json()) == 4
    assert manager.post("/api/milestones", json={"cohort_id": "c9", "title": "x", "due_date": due_in(1)}).status_code == 404


def test_my_milestones_are_my_cohort_only_and_start_pending(jane, tasks):
    mine = jane.get("/api/milestones/mine").json()
    assert [m["title"] for m in mine] == ["Week 1: Linux", "Week 2: Docker", "Week 3: Kubernetes"]
    assert [m["milestone_order"] for m in mine] == [1, 2, 3]
    assert {m["status"] for m in mine} == {"pending"}
    assert [m["overdue"] for m in mine] == [True, False, False]  # only Week 1's deadline has passed
    assert mine[0]["last_submitted_at"] is None
    assert datetime.fromisoformat(mine[0]["due_date"]) < datetime.now(UTC)


def test_task_status_follows_my_latest_report(manager, jane, tasks):
    report(jane, "m1", "needs_review")
    report(jane, "m2", "stalled")
    sub = report(jane, "m3", "needs_review")
    assert statuses(jane) == {"m1": "under_review", "m2": "in_progress", "m3": "under_review"}

    report(jane, "m2", "needs_review")  # a newer report replaces the stalled one
    manager.patch(f"/api/submissions/{sub['id']}/status", json={"status": "on_track"})  # signed off
    assert statuses(jane) == {"m1": "under_review", "m2": "under_review", "m3": "completed"}


def test_other_trainees_reports_dont_count(manager, jane, tasks):
    sam = {"name": "Sam", "email": "sam@example.com", "cohort_id": "c1", "initial_password": "password123"}
    sam_id = manager.post("/api/trainees", json=sam).json()["id"]
    manager.post("/api/submissions", json={"trainee_id": sam_id, "milestone_id": "m1"})

    assert statuses(jane)["m1"] == "pending"


def test_report_title_defaults_to_the_milestone(jane, tasks):
    assert report(jane, "m2")["milestone_name"] == "Week 2: Docker"
    assert report(jane, "m2")["milestone_id"] == "m2"


def test_reports_must_name_a_task_or_a_title(jane, tasks):
    assert jane.post("/api/submissions", json={"trainee_id": "u1"}).status_code == 422
    free_form = jane.post("/api/submissions", json={"trainee_id": "u1", "milestone_name": "Extra credit"})
    assert free_form.status_code == 201
    assert free_form.json()["milestone_id"] is None


@pytest.mark.parametrize("milestone_id", ["m4", "m99"])  # another cohort's task, a missing task
def test_cannot_report_on_a_task_outside_my_cohort(jane, tasks, milestone_id):
    resp = jane.post("/api/submissions", json={"trainee_id": "u1", "milestone_id": milestone_id})
    assert resp.status_code == 400


def test_my_cohort_lists_my_peers(manager, jane):
    for name, cohort in [("Sam Lee", "c1"), ("Ana Ruiz", "c1"), ("Other Cohort", "c2")]:
        body = {"name": name, "email": f"{name.split()[0].lower()}@example.com", "cohort_id": cohort, "initial_password": "password123"}
        manager.post("/api/trainees", json=body)

    mine = jane.get("/api/cohorts/mine").json()
    assert mine["cohort"]["name"] == "Cloud Native Q4"
    assert [p["name"] for p in mine["peers"]] == ["Ana Ruiz", "Sam Lee"]  # not Jane herself, not other cohorts
