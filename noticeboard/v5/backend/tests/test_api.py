"""The v2 API tests, now made through logged-in clients.

`manager` is Alex (u2) and `jane` is Jane (u1, trainee in c1); both come from tests/conftest.py.
Access-control rules have their own file: test_auth.py.
"""

from app.repositories import user_repo


def add_trainee(manager, cohort_id="c1", email="sam@example.com"):
    body = {"name": "Sam Lee", "email": email, "cohort_id": cohort_id, "initial_password": "password123"}
    resp = manager.post("/api/trainees", json=body)
    assert resp.status_code == 201, resp.text
    return resp.json()


def add_notice(manager, **overrides):
    body = {"title": "Heads up", "body": "Details here", **overrides}
    resp = manager.post("/api/notices", json=body)
    assert resp.status_code == 201, resp.text
    return resp.json()


def add_submission(client, trainee_id="u1", **overrides):
    body = {"trainee_id": trainee_id, "milestone_name": "Week 1", **overrides}
    resp = client.post("/api/submissions", json=body)
    assert resp.status_code == 201, resp.text
    return resp.json()


# --- cohorts & trainees --------------------------------------------------


def test_list_cohorts_includes_trainee_counts(jane):
    cohorts = {c["id"]: c for c in jane.get("/api/cohorts").json()}
    assert cohorts["c1"]["trainee_count"] == 1
    assert cohorts["c2"]["trainee_count"] == 0
    assert cohorts["c1"]["start_date"] == "2026-10-01"


def test_cohort_roster_excludes_managers(manager):
    roster = manager.get("/api/cohorts/c1/trainees").json()
    assert [u["id"] for u in roster] == ["u1"]


def test_roster_of_unknown_cohort_is_404(manager):
    assert manager.get("/api/cohorts/nope/trainees").status_code == 404


def test_create_trainee_can_log_in(manager, client_as):
    user = add_trainee(manager, cohort_id="c2", email="Sam.Lee@Example.com")
    assert user["id"] == "u3"
    assert user["role"] == "trainee"
    assert user["email"] == "sam.lee@example.com"
    assert [u["id"] for u in manager.get("/api/cohorts/c2/trainees").json()] == ["u3"]

    assert client_as("sam.lee@example.com").get("/api/auth/me").json()["id"] == "u3"


def test_duplicate_email_is_rejected_case_insensitively(manager):
    body = {"name": "Jane", "email": "JANE.DOE@example.com", "cohort_id": "c1", "initial_password": "password123"}
    assert manager.post("/api/trainees", json=body).status_code == 409


def test_create_trainee_validation(manager):
    valid = {"name": "Sam", "email": "sam@example.com", "cohort_id": "c1", "initial_password": "password123"}

    assert manager.post("/api/trainees", json={**valid, "cohort_id": "c9"}).status_code == 404
    assert manager.post("/api/trainees", json={**valid, "email": "not-an-email"}).status_code == 422
    assert manager.post("/api/trainees", json={**valid, "role": "manager"}).status_code == 422
    assert manager.post("/api/trainees", json={**valid, "name": "   "}).status_code == 422
    assert manager.post("/api/trainees", json={**valid, "initial_password": "short"}).status_code == 422
    assert manager.post("/api/trainees", json={**valid, "initial_password": "x" * 73}).status_code == 422


def test_initial_password_keeps_its_spaces(manager, client_as):
    body = {"name": "Sam", "email": "sam@example.com", "cohort_id": "c1", "initial_password": "  spaced pw  "}
    assert manager.post("/api/trainees", json=body).status_code == 201
    assert client_as("sam@example.com", "  spaced pw  ").get("/api/auth/me").status_code == 200


# --- notices -------------------------------------------------------------


def test_create_notice_defaults(manager):
    notice = add_notice(manager)
    assert notice["id"] == "n1"
    assert notice["priority"] == "standard"
    assert notice["target_cohort_id"] is None
    assert notice["created_at"]


def test_create_notice_validation(manager):
    assert manager.post("/api/notices", json={"title": "x", "body": "y", "target_cohort_id": "c9"}).status_code == 404
    assert manager.post("/api/notices", json={"title": "x", "body": "y", "priority": "low"}).status_code == 422
    assert manager.post("/api/notices", json={"title": "x"}).status_code == 422


def test_manager_list_filters_by_cohort(manager):
    global_notice = add_notice(manager)
    c1_notice = add_notice(manager, target_cohort_id="c1")
    c2_notice = add_notice(manager, target_cohort_id="c2")

    c1_ids = {n["id"] for n in manager.get("/api/notices", params={"cohort_id": "c1"}).json()}
    assert c1_ids == {global_notice["id"], c1_notice["id"]}

    all_ids = {n["id"] for n in manager.get("/api/notices").json()}
    assert all_ids == {global_notice["id"], c1_notice["id"], c2_notice["id"]}
    assert manager.get("/api/notices", params={"cohort_id": "c9"}).status_code == 404


def test_my_feed_shows_my_cohort_unread_urgent_first(manager, jane):
    add_notice(manager, title="routine")
    add_notice(manager, title="fire drill", priority="urgent", target_cohort_id="c1")
    add_notice(manager, title="other cohort", target_cohort_id="c2")
    read_one = add_notice(manager, title="already read")
    jane.post(f"/api/notices/{read_one['id']}/read")

    feed = jane.get("/api/notices/mine").json()
    assert [n["title"] for n in feed] == ["fire drill", "routine", "already read"]
    assert [n["read_at"] is None for n in feed] == [True, True, False]


def test_mark_notice_read_is_idempotent(manager, jane):
    notice = add_notice(manager, target_cohort_id="c1")

    first = jane.post(f"/api/notices/{notice['id']}/read")
    assert first.status_code == 200
    assert first.json()["notice_id"] == notice["id"]
    assert first.json()["trainee_id"] == "u1"

    second = jane.post(f"/api/notices/{notice['id']}/read")
    assert second.json()["read_at"] == first.json()["read_at"]


def test_mark_read_rejects_invalid_requests(manager, jane):
    c2_notice = add_notice(manager, target_cohort_id="c2")

    assert jane.post(f"/api/notices/{c2_notice['id']}/read").status_code == 400
    assert jane.post("/api/notices/n99/read").status_code == 404


# --- submissions ---------------------------------------------------------


def test_create_submission(jane):
    sub = add_submission(jane, asset_url="https://github.com/janedoe/lab", notes="Done")
    assert sub["id"] == "s1"
    assert sub["status"] == "needs_review"
    assert sub["asset_url"] == "https://github.com/janedoe/lab"
    assert sub["submitted_at"]


def test_trainee_can_self_report_status(jane):
    assert add_submission(jane, status="stalled")["status"] == "stalled"


def test_create_submission_validation(manager, jane):
    assert manager.post("/api/submissions", json={"trainee_id": "u2", "milestone_name": "W1"}).status_code == 404
    bad_url = {"trainee_id": "u1", "milestone_name": "W1", "asset_url": "not a url"}
    assert jane.post("/api/submissions", json=bad_url).status_code == 422
    bad_status = {"trainee_id": "u1", "milestone_name": "W1", "status": "done"}
    assert jane.post("/api/submissions", json=bad_status).status_code == 422


def test_list_submissions_by_cohort(manager, jane):
    other = add_trainee(manager, cohort_id="c2")
    jane_sub = add_submission(jane, trainee_id="u1")
    add_submission(manager, trainee_id=other["id"])

    c1 = manager.get("/api/submissions", params={"cohort_id": "c1"}).json()
    assert [s["id"] for s in c1] == [jane_sub["id"]]
    assert len(manager.get("/api/submissions").json()) == 2
    assert manager.get("/api/submissions", params={"cohort_id": "c9"}).status_code == 404


def test_my_submissions_only_shows_mine(manager, jane):
    other = add_trainee(manager, cohort_id="c2")
    add_submission(jane, milestone_name="Week 1")
    add_submission(jane, milestone_name="Week 2")
    add_submission(manager, trainee_id=other["id"])

    assert [s["milestone_name"] for s in jane.get("/api/submissions/mine").json()] == ["Week 2", "Week 1"]


def test_update_submission_status(manager, jane):
    sub = add_submission(jane)

    resp = manager.patch(f"/api/submissions/{sub['id']}/status", json={"status": "on_track"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "on_track"
    assert jane.get("/api/submissions/mine").json()[0]["status"] == "on_track"

    assert manager.patch(f"/api/submissions/{sub['id']}/status", json={"status": "done"}).status_code == 422
    assert manager.patch("/api/submissions/s99/status", json={"status": "stalled"}).status_code == 404


def test_list_submissions_limit(manager, jane):
    for week in range(3):
        add_submission(jane, milestone_name=f"Week {week + 1}")

    assert [s["milestone_name"] for s in manager.get("/api/submissions", params={"limit": 2}).json()] == [
        "Week 3",
        "Week 2",
    ]
    assert manager.get("/api/submissions", params={"limit": 0}).status_code == 422


def test_writes_are_committed(manager, sessions):
    """A brand-new session only sees the trainee if the request committed it."""
    created = add_trainee(manager)
    with sessions() as fresh:
        assert user_repo.get(fresh, created["id"]).email == "sam@example.com"
