"""Timed deadlines, milestone order, the multi-cohort dispatcher and the agenda's schedule blocks."""

from datetime import UTC, datetime, timedelta

import pytest

pytestmark = pytest.mark.usefixtures("v1_seed")  # c1, c2, u1 Jane (c1), u2 Alex (manager)

NOW = datetime.now(UTC)


def at(days: float = 0, hours: float = 0) -> str:
    return (NOW + timedelta(days=days, hours=hours)).isoformat()


def add_milestone(manager, cohort_id="c1", title="Task", due=None, **extra):
    return manager.post("/api/milestones", json={"cohort_id": cohort_id, "title": title, "due_date": due or at(7), **extra})


# --- milestone order and timed deadlines ---------------------------------


def test_new_milestones_go_to_the_end_of_their_cohort(manager):
    orders = [add_milestone(manager, cohort, f"T{i}").json()["milestone_order"] for i, cohort in enumerate(["c1", "c1", "c2", "c1"])]
    assert orders == [1, 2, 1, 3]  # numbered per cohort


def test_explicit_order_must_be_free(manager):
    assert add_milestone(manager, milestone_order=5).json()["milestone_order"] == 5
    clash = add_milestone(manager, milestone_order=5)
    assert clash.status_code == 409
    assert add_milestone(manager).json()["milestone_order"] == 6  # "end" means after the highest
    assert add_milestone(manager, milestone_order=0).status_code == 422


def test_deadlines_are_exact_moments_with_a_timezone(manager):
    created = add_milestone(manager, due="2026-11-06T17:00:00-05:00").json()
    assert datetime.fromisoformat(created["due_date"]) == datetime(2026, 11, 6, 22, 0, tzinfo=UTC)

    assert add_milestone(manager, due="2026-11-06T17:00:00").status_code == 422  # no timezone: ambiguous
    assert add_milestone(manager, due="2026-11-06").status_code == 422


def test_milestones_list_in_sequence_order(manager):
    add_milestone(manager, title="Second", milestone_order=2, due=at(1))
    add_milestone(manager, title="First", milestone_order=1, due=at(9))  # due later, but first in sequence
    assert [m["title"] for m in manager.get("/api/milestones", params={"cohort_id": "c1"}).json()] == ["First", "Second"]


# --- dispatcher -----------------------------------------------------------


def test_dispatch_sends_one_task_to_several_cohorts(manager, jane):
    add_milestone(manager, "c1", "Existing")
    resp = manager.post(
        "/api/milestones/dispatch",
        json={"title": "Demo day", "assignments": [{"cohort_id": "c1", "due_date": at(3)}, {"cohort_id": "c2", "due_date": at(5)}]},
    )
    assert resp.status_code == 201
    created = resp.json()
    assert [(m["cohort_id"], m["milestone_order"], m["title"]) for m in created] == [("c1", 2, "Demo day"), ("c2", 1, "Demo day")]
    assert created[0]["due_date"] != created[1]["due_date"]  # each cohort keeps its own deadline
    assert [m["title"] for m in jane.get("/api/milestones/mine").json()] == ["Existing", "Demo day"]


def test_dispatch_is_all_or_nothing(manager):
    resp = manager.post(
        "/api/milestones/dispatch",
        json={"title": "Demo day", "assignments": [{"cohort_id": "c1", "due_date": at(3)}, {"cohort_id": "c9", "due_date": at(3)}]},
    )
    assert resp.status_code == 404
    assert manager.get("/api/milestones").json() == []


@pytest.mark.parametrize(
    "assignments",
    [[], [{"cohort_id": "c1", "due_date": at(1)}, {"cohort_id": "c1", "due_date": at(2)}]],
    ids=["no cohorts", "same cohort twice"],
)
def test_dispatch_validation(manager, assignments):
    assert manager.post("/api/milestones/dispatch", json={"title": "x", "assignments": assignments}).status_code == 422


# --- schedule blocks (agenda) ----------------------------------------------


def add_block(manager, title="Lab", start=0, hours=2, **extra):
    body = {"cohort_id": "c1", "title": title, "starts_at": at(hours=start), "ends_at": at(hours=start + hours), **extra}
    return manager.post("/api/schedule", json=body)


def my_agenda(jane, start_hours, end_hours):
    return jane.get("/api/schedule/mine", params={"start": at(hours=start_hours), "end": at(hours=end_hours)})


def test_trainees_see_their_cohorts_blocks_in_a_range(manager, jane):
    module = add_milestone(manager).json()
    add_block(manager, "Lecture", start=1, milestone_id=module["id"])
    add_block(manager, "Lab", start=4)
    add_block(manager, "Next week", start=24 * 7)
    manager.post("/api/schedule", json={"cohort_id": "c2", "title": "Other cohort", "starts_at": at(hours=1), "ends_at": at(hours=2)})

    agenda = my_agenda(jane, 0, 24)
    assert agenda.status_code == 200
    assert [(b["title"], b["milestone_id"]) for b in agenda.json()] == [("Lecture", module["id"]), ("Lab", None)]


def test_blocks_running_across_the_range_start_are_included(manager, jane):
    add_block(manager, "Long lab", start=-1, hours=3)  # started an hour ago, still running
    assert [b["title"] for b in my_agenda(jane, 0, 1).json()] == ["Long lab"]


def test_block_validation(manager):
    assert add_block(manager, hours=-1).status_code == 422  # ends before it starts
    other_cohort_task = add_milestone(manager, "c2").json()
    assert add_block(manager, milestone_id=other_cohort_task["id"]).status_code == 400
    assert manager.post("/api/schedule", json={"cohort_id": "c9", "title": "x", "starts_at": at(), "ends_at": at(1)}).status_code == 404


def test_agenda_range_rules(jane):
    assert my_agenda(jane, 0, 24 * 63).status_code == 400  # more than 62 days
    assert my_agenda(jane, 5, 1).status_code == 400  # ends before it starts
    naive = jane.get("/api/schedule/mine", params={"start": "2026-10-01T00:00:00", "end": "2026-10-02T00:00:00"})
    assert naive.status_code == 422


def test_managers_list_any_cohorts_schedule(manager):
    add_block(manager, "Lab")
    blocks = manager.get("/api/schedule", params={"cohort_id": "c1", "start": at(-1), "end": at(1)})
    assert [b["title"] for b in blocks.json()] == ["Lab"]
