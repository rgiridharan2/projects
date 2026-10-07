"""Public sign-up and the cohort list that feeds its dropdown."""

from datetime import date

import pytest

from app.repositories import cohort_repo

pytestmark = pytest.mark.usefixtures("v1_seed")  # c1, c2 (both open), u1 Jane, u2 Alex


def signup(client, **overrides):
    body = {"name": "Sam Lee", "email": "sam@example.com", "password": "password123", **overrides}
    return client.post("/api/auth/signup", json=body)


@pytest.fixture
def closed_cohort(db):
    cohort = cohort_repo.create(db, name="Private Track", track_type="solo", start_date=date(2026, 9, 1), open_for_signup=False)
    db.commit()
    return cohort


def test_signup_creates_a_trainee_and_logs_in(client):
    resp = signup(client, cohort_id="c1")
    assert resp.status_code == 201
    body = resp.json()
    assert body["token_type"] == "bearer"
    assert body["user"] == {"id": "u3", "name": "Sam Lee", "email": "sam@example.com", "role": "trainee", "cohort_id": "c1"}

    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {body['access_token']}"})
    assert me.json()["id"] == "u3"


def test_new_account_can_log_in_with_its_password(client, client_as):
    signup(client, email="Sam@Example.com")
    assert client_as("sam@example.com").get("/api/auth/me").json()["role"] == "trainee"


def test_signup_cannot_choose_a_role(client):
    resp = signup(client, role="manager")
    assert resp.status_code == 422
    assert resp.json()["detail"][0]["loc"] == ["body", "role"]


def test_signup_without_a_cohort_sees_only_global_things(client, manager):
    token = signup(client).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    manager.post("/api/notices", json={"title": "Global", "body": "For everyone"})
    manager.post("/api/notices", json={"title": "C1 only", "body": "Cohort 1", "target_cohort_id": "c1"})

    assert [n["title"] for n in client.get("/api/notices/mine", headers=headers).json()] == ["Global"]
    assert client.get("/api/milestones/mine", headers=headers).json() == []
    assert client.get("/api/cohorts/mine", headers=headers).json() == {"cohort": None, "peers": []}


@pytest.mark.parametrize(
    ("overrides", "status"),
    [
        ({"email": "JANE.DOE@example.com"}, 409),  # already registered
        ({"cohort_id": "c99"}, 400),  # no such cohort
        ({"password": "short"}, 422),
        ({"email": "not-an-email"}, 422),
        ({"name": "  "}, 422),
    ],
)
def test_signup_validation(client, overrides, status):
    assert signup(client, **overrides).status_code == status


def test_closed_cohorts_are_hidden_and_cannot_be_joined(client, closed_cohort):
    listed = client.get("/api/cohorts/public-list")
    assert listed.status_code == 200  # no token needed
    assert [c["id"] for c in listed.json()] == ["c2", "c1"]  # by start date; the closed one is missing
    assert set(listed.json()[0]) == {"id", "name", "track_type", "start_date"}

    resp = signup(client, cohort_id=closed_cohort.id)
    assert resp.status_code == 400
    assert resp.json()["detail"] == f"Cohort '{closed_cohort.id}' is not open for sign-up"


def test_managers_create_cohorts_and_choose_whether_they_are_public(client, manager):
    hidden = manager.post(
        "/api/cohorts", json={"name": "Invite only", "start_date": "2026-11-02", "open_for_signup": False}
    )
    public = manager.post("/api/cohorts", json={"name": "Spring Data", "start_date": "2026-11-09"})
    assert hidden.status_code == public.status_code == 201
    assert public.json()["track_type"] == "group"

    names = {c["name"] for c in client.get("/api/cohorts/public-list").json()}
    assert "Spring Data" in names and "Invite only" not in names
