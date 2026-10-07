import pytest

from app.repositories import user_repo

pytestmark = pytest.mark.usefixtures("v1_seed")


def add_trainee(client, cohort_id="c1", email="sam@example.com"):
    resp = client.post("/api/trainees", json={"name": "Sam Lee", "email": email, "cohort_id": cohort_id})
    assert resp.status_code == 201, resp.text
    return resp.json()


def add_notice(client, **overrides):
    body = {"title": "Heads up", "body": "Details here", **overrides}
    resp = client.post("/api/notices", json=body)
    assert resp.status_code == 201, resp.text
    return resp.json()


def add_submission(client, trainee_id="u1", **overrides):
    body = {"trainee_id": trainee_id, "milestone_name": "Week 1", **overrides}
    resp = client.post("/api/submissions", json=body)
    assert resp.status_code == 201, resp.text
    return resp.json()


# --- cohorts & trainees --------------------------------------------------


def test_list_cohorts_includes_trainee_counts(client):
    cohorts = {c["id"]: c for c in client.get("/api/cohorts").json()}
    assert cohorts["c1"]["trainee_count"] == 1
    assert cohorts["c2"]["trainee_count"] == 0
    assert cohorts["c1"]["start_date"] == "2026-10-01"


def test_cohort_roster_excludes_managers(client):
    roster = client.get("/api/cohorts/c1/trainees").json()
    assert [u["id"] for u in roster] == ["u1"]


def test_roster_of_unknown_cohort_is_404(client):
    assert client.get("/api/cohorts/nope/trainees").status_code == 404


def test_create_trainee(client):
    user = add_trainee(client, cohort_id="c2", email="Sam.Lee@Example.com")
    assert user["id"] == "u3"
    assert user["role"] == "trainee"
    assert user["email"] == "sam.lee@example.com"
    assert [u["id"] for u in client.get("/api/cohorts/c2/trainees").json()] == ["u3"]


def test_duplicate_email_is_rejected_case_insensitively(client):
    resp = client.post("/api/trainees", json={"name": "Jane", "email": "JANE.DOE@example.com", "cohort_id": "c1"})
    assert resp.status_code == 409


def test_create_trainee_validation(client):
    unknown_cohort = {"name": "Sam", "email": "sam@example.com", "cohort_id": "c9"}
    assert client.post("/api/trainees", json=unknown_cohort).status_code == 404

    bad_email = {"name": "Sam", "email": "not-an-email", "cohort_id": "c1"}
    assert client.post("/api/trainees", json=bad_email).status_code == 422

    sets_role = {"name": "Sam", "email": "sam@example.com", "cohort_id": "c1", "role": "manager"}
    assert client.post("/api/trainees", json=sets_role).status_code == 422

    blank_name = {"name": "   ", "email": "sam@example.com", "cohort_id": "c1"}
    assert client.post("/api/trainees", json=blank_name).status_code == 422


# --- notices -------------------------------------------------------------


def test_create_notice_defaults(client):
    notice = add_notice(client)
    assert notice["id"] == "n1"
    assert notice["priority"] == "standard"
    assert notice["target_cohort_id"] is None
    assert notice["created_at"]


def test_create_notice_validation(client):
    assert client.post("/api/notices", json={"title": "x", "body": "y", "target_cohort_id": "c9"}).status_code == 404
    assert client.post("/api/notices", json={"title": "x", "body": "y", "priority": "low"}).status_code == 422
    assert client.post("/api/notices", json={"title": "x"}).status_code == 422


def test_cohort_feed_includes_global_and_own_cohort_only(client):
    global_notice = add_notice(client)
    c1_notice = add_notice(client, target_cohort_id="c1")
    c2_notice = add_notice(client, target_cohort_id="c2")

    c1_ids = {n["id"] for n in client.get("/api/notices", params={"cohort_id": "c1"}).json()}
    assert c1_ids == {global_notice["id"], c1_notice["id"]}

    all_ids = {n["id"] for n in client.get("/api/notices").json()}
    assert all_ids == {global_notice["id"], c1_notice["id"], c2_notice["id"]}


def test_urgent_notices_come_first(client):
    add_notice(client, title="routine")
    add_notice(client, title="fire drill", priority="urgent")
    add_notice(client, title="also routine")

    feed = client.get("/api/notices", params={"cohort_id": "c1"}).json()
    assert feed[0]["title"] == "fire drill"


def test_notices_for_unknown_cohort_is_404(client):
    assert client.get("/api/notices", params={"cohort_id": "c9"}).status_code == 404


def test_mark_notice_read_is_idempotent(client):
    notice = add_notice(client, target_cohort_id="c1")

    first = client.post(f"/api/notices/{notice['id']}/read", json={"trainee_id": "u1"})
    assert first.status_code == 200
    assert first.json()["notice_id"] == notice["id"]
    assert first.json()["trainee_id"] == "u1"

    second = client.post(f"/api/notices/{notice['id']}/read", json={"trainee_id": "u1"})
    assert second.json()["read_at"] == first.json()["read_at"]


def test_mark_read_rejects_invalid_requests(client):
    c2_notice = add_notice(client, target_cohort_id="c2")
    global_notice = add_notice(client)

    assert client.post(f"/api/notices/{c2_notice['id']}/read", json={"trainee_id": "u1"}).status_code == 400
    assert client.post(f"/api/notices/{global_notice['id']}/read", json={"trainee_id": "u2"}).status_code == 404
    assert client.post("/api/notices/n99/read", json={"trainee_id": "u1"}).status_code == 404


# --- submissions ---------------------------------------------------------


def test_create_submission(client):
    sub = add_submission(client, asset_url="https://github.com/janedoe/lab", notes="Done")
    assert sub["id"] == "s1"
    assert sub["status"] == "needs_review"
    assert sub["asset_url"] == "https://github.com/janedoe/lab"
    assert sub["submitted_at"]


def test_create_submission_validation(client):
    assert client.post("/api/submissions", json={"trainee_id": "u2", "milestone_name": "W1"}).status_code == 404
    bad_url = {"trainee_id": "u1", "milestone_name": "W1", "asset_url": "not a url"}
    assert client.post("/api/submissions", json=bad_url).status_code == 422
    sets_status = {"trainee_id": "u1", "milestone_name": "W1", "status": "on_track"}
    assert client.post("/api/submissions", json=sets_status).status_code == 422


def test_list_submissions_by_cohort(client):
    other = add_trainee(client, cohort_id="c2")
    jane_sub = add_submission(client, trainee_id="u1")
    add_submission(client, trainee_id=other["id"])

    c1 = client.get("/api/submissions", params={"cohort_id": "c1"}).json()
    assert [s["id"] for s in c1] == [jane_sub["id"]]
    assert len(client.get("/api/submissions").json()) == 2
    assert client.get("/api/submissions", params={"cohort_id": "c9"}).status_code == 404


def test_update_submission_status(client):
    sub = add_submission(client)

    resp = client.patch(f"/api/submissions/{sub['id']}/status", json={"status": "on_track"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "on_track"
    assert client.get("/api/submissions").json()[0]["status"] == "on_track"

    assert client.patch(f"/api/submissions/{sub['id']}/status", json={"status": "done"}).status_code == 422
    assert client.patch("/api/submissions/s99/status", json={"status": "stalled"}).status_code == 404


# --- added in v2 ---------------------------------------------------------


def test_list_submissions_limit(client):
    for week in range(3):
        add_submission(client, milestone_name=f"Week {week + 1}")

    assert [s["milestone_name"] for s in client.get("/api/submissions", params={"limit": 2}).json()] == [
        "Week 3",
        "Week 2",
    ]
    assert client.get("/api/submissions", params={"limit": 0}).status_code == 422


def test_writes_are_committed(client, sessions):
    """A brand-new session only sees the trainee if the request committed it."""
    created = add_trainee(client)
    with sessions() as fresh:
        assert user_repo.get(fresh, created["id"]).email == "sam@example.com"
