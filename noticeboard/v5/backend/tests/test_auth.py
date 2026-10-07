"""Authentication (who are you?) and authorization (what may you do?)."""

from datetime import UTC, datetime, timedelta

import jwt
import pytest

from app.config import settings
from app.repositories import user_repo

pytestmark = pytest.mark.usefixtures("v1_seed")

JANE_USER = {"id": "u1", "name": "Jane Doe", "email": "jane.doe@example.com", "role": "trainee", "cohort_id": "c1"}


def login(client, identifier, password="password123"):
    return client.post("/api/auth/login", json={"identifier": identifier, "password": password})


def bearer(token):
    return {"Authorization": f"Bearer {token}"}


def make_token(**claims):
    """A token signed with the real secret, for crafting edge cases."""
    claims.setdefault("exp", datetime.now(UTC) + timedelta(minutes=5))
    return jwt.encode(claims, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def add_trainee(manager, email):
    body = {"name": "Sam Lee", "email": email, "cohort_id": "c1", "initial_password": "password123"}
    return manager.post("/api/trainees", json=body).json()


# --- logging in ----------------------------------------------------------


def test_login_by_email_returns_token_and_user(client):
    resp = login(client, "Jane.Doe@Example.com")
    assert resp.status_code == 200
    body = resp.json()
    assert body["token_type"] == "bearer"
    assert body["user"] == JANE_USER

    claims = jwt.decode(body["access_token"], settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    assert (claims["sub"], claims["role"], claims["cohort_id"]) == ("u1", "trainee", "c1")
    assert claims["exp"] > claims["iat"]


def test_login_by_id(client):
    assert login(client, "u2").json()["user"]["role"] == "manager"


@pytest.mark.parametrize(
    ("identifier", "password"),
    [("u1", "wrong-password"), ("nobody@example.com", "password123"), ("u99", "password123")],
)
def test_bad_credentials_all_get_the_same_401(client, identifier, password):
    resp = login(client, identifier, password)
    assert resp.status_code == 401
    assert resp.json()["detail"] == "Incorrect email/ID or password"


def test_user_without_a_password_cannot_log_in(client, manager, db):
    user_repo.create(db, name="Legacy", email="legacy@example.com", role="trainee", cohort_id="c1", hashed_password=None)
    db.commit()

    assert login(client, "legacy@example.com").status_code == 401
    assert "Legacy" not in {o["name"] for o in manager.get("/api/users/switch-options").json()}


def test_swagger_form_login(client):
    resp = client.post("/api/auth/token", data={"username": "jane.doe@example.com", "password": "password123"})
    assert resp.status_code == 200
    assert client.get("/api/auth/me", headers=bearer(resp.json()["access_token"])).json() == JANE_USER


def test_switch_options_need_a_login(client):
    assert client.get("/api/users/switch-options").status_code == 401


def test_switch_options_list_everyone_with_cohort_names(jane):
    assert jane.get("/api/users/switch-options").json() == [
        {"id": "u2", "name": "Alex Smith", "role": "manager", "cohort_name": None},
        {"id": "u1", "name": "Jane Doe", "role": "trainee", "cohort_name": "Cloud Native Q4"},
    ]


def test_password_hashes_never_leave_the_api(client, manager):
    for resp in [
        login(client, "u1"),
        manager.get("/api/auth/me"),
        manager.get("/api/cohorts/c1/trainees"),
        manager.get("/api/users/switch-options"),
    ]:
        assert "hashed_password" not in resp.text
        assert "$2b$" not in resp.text


# --- tokens --------------------------------------------------------------


@pytest.mark.parametrize(
    "headers", [{}, {"Authorization": "Bearer not-a-jwt"}, {"Authorization": "Basic dTE6cGFzc3dvcmQxMjM="}]
)
def test_protected_routes_need_a_valid_token(client, headers):
    resp = client.get("/api/cohorts", headers=headers)
    assert resp.status_code == 401
    assert resp.headers["WWW-Authenticate"] == "Bearer"


def test_expired_token_is_rejected(client):
    token = make_token(sub="u1", exp=datetime.now(UTC) - timedelta(seconds=1))
    assert client.get("/api/auth/me", headers=bearer(token)).status_code == 401


def test_forged_token_is_rejected(client):
    forged = jwt.encode(
        {"sub": "u2", "role": "manager", "exp": datetime.now(UTC) + timedelta(minutes=5)},
        "a-different-secret-the-attacker-chose-1234567890",
        algorithm="HS256",
    )
    assert client.get("/api/dashboard/stats", headers=bearer(forged)).status_code == 401


def test_token_for_unknown_user_is_rejected(client):
    assert client.get("/api/auth/me", headers=bearer(make_token(sub="u99"))).status_code == 401


def test_role_comes_from_the_database_not_the_token(client):
    """Even a validly signed token claiming 'manager' can't promote a trainee."""
    token = make_token(sub="u1", role="manager")
    assert client.get("/api/dashboard/stats", headers=bearer(token)).status_code == 403


# --- roles ---------------------------------------------------------------

MANAGER_ONLY = [
    ("GET", "/api/cohorts/c1/trainees"),
    ("POST", "/api/trainees"),
    ("POST", "/api/notices"),
    ("GET", "/api/notices"),
    ("GET", "/api/submissions"),
    ("GET", "/api/dashboard/stats"),
    ("POST", "/api/cohorts"),
    ("POST", "/api/milestones"),
    ("GET", "/api/milestones"),
    ("POST", "/api/milestones/dispatch"),
    ("POST", "/api/schedule"),
    ("GET", "/api/schedule"),
    ("POST", "/api/reminders"),
    ("GET", "/api/cohorts/c1/matrix"),
    ("POST", "/api/cohorts/c1/nudges"),
    ("POST", "/api/trainees/import"),
    ("GET", "/api/cohorts/health"),
    ("GET", "/api/cohorts/c1/report.csv"),
    ("GET", "/api/escalations"),
    ("POST", "/api/escalations/run"),
    ("GET", "/api/audit"),
]
TRAINEE_ONLY = [
    ("GET", "/api/notices/mine"),
    ("POST", "/api/notices/n1/read"),
    ("GET", "/api/submissions/mine"),
    ("GET", "/api/milestones/mine"),
    ("GET", "/api/cohorts/mine"),
    ("GET", "/api/schedule/mine"),
    ("GET", "/api/reminders/mine"),
    ("POST", "/api/reminders/r1/dismiss"),
]


@pytest.mark.parametrize(("method", "path"), MANAGER_ONLY)
def test_trainees_get_403_on_manager_routes(jane, method, path):
    resp = jane.request(method, path, json={})
    assert resp.status_code == 403
    assert resp.json()["detail"] == "Requires role: manager"


@pytest.mark.parametrize(("method", "path"), TRAINEE_ONLY)
def test_managers_get_403_on_trainee_routes(manager, method, path):
    assert manager.request(method, path).status_code == 403


# --- owning your own progress reports ------------------------------------


def test_trainee_cannot_submit_for_someone_else(manager, jane):
    sam = add_trainee(manager, "sam@example.com")
    resp = jane.post("/api/submissions", json={"trainee_id": sam["id"], "milestone_name": "Week 1"})
    assert resp.status_code == 403


def test_manager_can_submit_on_a_trainees_behalf(manager):
    resp = manager.post("/api/submissions", json={"trainee_id": "u1", "milestone_name": "Week 1"})
    assert resp.status_code == 201


def test_trainee_can_update_only_their_own_submissions(manager, jane, client_as):
    sam = add_trainee(manager, "sam@example.com")
    sams_sub = client_as("sam@example.com").post(
        "/api/submissions", json={"trainee_id": sam["id"], "milestone_name": "Week 1"}
    ).json()
    janes_sub = jane.post("/api/submissions", json={"trainee_id": "u1", "milestone_name": "Week 1"}).json()

    assert jane.patch(f"/api/submissions/{sams_sub['id']}/status", json={"status": "on_track"}).status_code == 403
    assert jane.patch(f"/api/submissions/{janes_sub['id']}/status", json={"status": "stalled"}).status_code == 200
    assert manager.patch(f"/api/submissions/{sams_sub['id']}/status", json={"status": "on_track"}).status_code == 200
