"""Phase 5 backend: CSV import, audit log, escalations, cohort health and the CSV report."""

import csv
import io
from datetime import UTC, datetime, timedelta

import pytest

from app.repositories import user_repo
from app.routers.escalations import run_escalations


def due_in(days: float) -> str:
    return (datetime.now(UTC) + timedelta(days=days)).isoformat()


def actions(manager):
    return [e["action"] for e in manager.get("/api/audit").json()]


# --- bulk CSV import ------------------------------------------------------------------------------

CSV = """name,email,cohort_id
Sam Lee,sam.lee@example.com,c1
Ana Ruiz,ANA.RUIZ@example.com,c2
No Cohort,nocohort@example.com,
"""


@pytest.mark.usefixtures("v1_seed")
class TestImport:
    def preview(self, manager, text):
        return manager.post("/api/trainees/import", json={"csv": text})

    def test_dry_run_reports_and_saves_nothing(self, manager):
        resp = self.preview(manager, CSV)
        assert resp.status_code == 200
        report = resp.json()
        assert (report["dry_run"], report["valid_count"], report["invalid_count"], report["created"]) == (True, 3, 0, [])
        assert [r["email"] for r in report["rows"]] == ["sam.lee@example.com", "ana.ruiz@example.com", "nocohort@example.com"]
        assert [r["line"] for r in report["rows"]] == [2, 3, 4]
        assert manager.get("/api/cohorts/c1/trainees").json()[-1]["name"] == "Jane Doe"  # nothing added

    def test_every_row_is_checked_against_the_database_and_the_file(self, manager):
        text = """email,NAME,cohort_id
jane.doe@example.com,Jane Again,c1
not-an-email,Bad Email,c1
dup@example.com,First,c1
DUP@example.com,Second,c1
,No Email,c1
x@example.com,,c1
y@example.com,Wrong Cohort,c99
"""
        rows = {r["line"]: r["errors"] for r in self.preview(manager, text).json()["rows"]}
        assert rows == {
            2: ["Already has an account"],
            3: ["Not a valid email address"],
            4: [],
            5: ["Same email as line 4"],
            6: ["Email is required"],
            7: ["Name is required"],
            8: ["No cohort 'c99'"],
        }

    @pytest.mark.parametrize(
        ("text", "message"),
        [
            ("name,email\nSam,sam@example.com\n", "Missing column(s): cohort_id"),
            ("name,email,cohort_id\n", "header but no data rows"),
        ],
    )
    def test_unusable_files_are_rejected(self, manager, text, message):
        resp = self.preview(manager, text)
        assert resp.status_code == 400
        assert message in resp.json()["detail"]

    def test_import_creates_trainees_who_can_log_in(self, manager, client_as):
        resp = manager.post("/api/trainees/import", json={"csv": CSV, "dry_run": False, "initial_password": "welcome-2026"})
        assert resp.status_code == 201
        assert [u["email"] for u in resp.json()["created"]] == ["sam.lee@example.com", "ana.ruiz@example.com", "nocohort@example.com"]
        assert client_as("ana.ruiz@example.com", "welcome-2026").get("/api/auth/me").json()["cohort_id"] == "c2"
        assert "trainees.imported" in actions(manager)

    def test_import_needs_a_password_and_clean_rows(self, manager, db):
        assert manager.post("/api/trainees/import", json={"csv": CSV, "dry_run": False}).status_code == 422
        bad = CSV + "Jane,jane.doe@example.com,c1\n"
        refused = manager.post("/api/trainees/import", json={"csv": bad, "dry_run": False, "initial_password": "welcome-2026"})
        assert refused.status_code == 400
        assert user_repo.get_by_email(db, "sam.lee@example.com") is None  # all-or-nothing

        partial = manager.post(
            "/api/trainees/import", json={"csv": bad, "dry_run": False, "initial_password": "welcome-2026", "skip_invalid": True}
        )
        assert (partial.status_code, len(partial.json()["created"]), partial.json()["invalid_count"]) == (201, 3, 1)

    def test_excel_byte_order_mark_is_ignored(self, manager):
        assert self.preview(manager, "﻿" + CSV).json()["valid_count"] == 3


# --- audit log --------------------------------------------------------------------------------------


@pytest.mark.usefixtures("v1_seed")
def test_admin_actions_are_logged_with_actor_and_summary(manager, jane):
    manager.post("/api/notices", json={"title": "Fire drill", "body": "At 3pm", "priority": "urgent", "target_cohort_id": "c1"})
    manager.post("/api/milestones/dispatch", json={"title": "Demo", "assignments": [{"cohort_id": "c1", "due_date": due_in(3)}]})
    sub = jane.post("/api/submissions", json={"trainee_id": "u1", "milestone_id": "m1"}).json()
    manager.patch(f"/api/submissions/{sub['id']}/status", json={"status": "on_track"})
    jane.patch(f"/api/submissions/{sub['id']}/status", json={"status": "stalled"})

    log = manager.get("/api/audit").json()
    assert [e["action"] for e in log] == [
        "submission.status_changed",
        "submission.signed_off",
        "milestone.dispatched",
        "notice.posted",
    ]
    assert log[0]["actor_name"] == "Jane Doe"
    assert log[0]["summary"] == "Changed their own report for Demo from on_track to stalled"
    assert log[1]["summary"] == "Signed off Jane Doe's report for Demo"
    assert log[3]["summary"] == "Posted an urgent notice “Fire drill” to Cloud Native Q4"


@pytest.mark.usefixtures("v1_seed")
def test_audit_log_pages_backwards(manager):
    for i in range(5):
        manager.post("/api/notices", json={"title": f"N{i}", "body": "x"})
    first = manager.get("/api/audit", params={"limit": 3}).json()
    rest = manager.get("/api/audit", params={"limit": 3, "before": first[-1]["created_at"]}).json()
    assert [e["target_id"] for e in first + rest] == ["n5", "n4", "n3", "n2", "n1"]  # newest first, no gaps or repeats


@pytest.mark.usefixtures("v1_seed")
def test_unchanged_status_is_not_logged(manager, jane):
    sub = jane.post("/api/submissions", json={"trainee_id": "u1", "milestone_name": "Free-form"}).json()
    manager.patch(f"/api/submissions/{sub['id']}/status", json={"status": "needs_review"})  # already needs_review
    assert actions(manager) == []


# --- escalations --------------------------------------------------------------------------------------


@pytest.fixture
def late_tasks(manager, v1_seed):
    """c1 (Jane): m1 is 3 days late, m2 one day late, m3 not due."""
    for title, due in [("W1", due_in(-3)), ("W2", due_in(-1)), ("W3", due_in(4))]:
        manager.post("/api/milestones", json={"cohort_id": "c1", "title": title, "due_date": due})


@pytest.mark.usefixtures("late_tasks")
def test_escalation_flags_only_tasks_48h_past_deadline(manager, db):
    run = manager.post("/api/escalations/run").json()
    assert run == {"created": 1, "active": 1}  # m1 only; m2 is overdue but under 48h
    [item] = manager.get("/api/escalations").json()
    assert (item["trainee_name"], item["milestone_title"], item["cohort_name"]) == ("Jane Doe", "W1", "Cloud Native Q4")

    assert manager.post("/api/escalations/run").json() == {"created": 0, "active": 1}  # idempotent
    matrix = manager.get("/api/cohorts/c1/matrix").json()
    assert [c["escalated"] for c in matrix["rows"][0]["cells"]] == [True, False, False]
    assert "escalation.raised" in actions(manager)


@pytest.mark.usefixtures("late_tasks")
def test_background_check_logs_as_the_system_and_submission_resolves(manager, jane, db):
    assert run_escalations(db, actor=None, now=datetime.now(UTC)) == 1  # what the background loop calls
    entry = manager.get("/api/audit").json()[0]
    assert (entry["action"], entry["actor_name"]) == ("escalation.raised", None)

    jane.post("/api/submissions", json={"trainee_id": "u1", "milestone_id": "m1"})
    assert manager.get("/api/escalations").json() == []


# --- cohort health and the CSV report --------------------------------------------------------------------


@pytest.fixture
def demo(db):
    from seed import seed

    seed(db, now=datetime.now(UTC))
    db.commit()


@pytest.fixture
def morgan(demo, client_as):
    return client_as("manager@edtech.com")


def test_cohort_health_on_seed_data_worst_first(morgan):
    health = morgan.get("/api/cohorts/health").json()
    assert [(h["cohort"]["name"], h["score"], h["status"]) for h in health] == [
        ("Cloud Native Q4", 56, "at_risk"),  # 0.6 x 10/30 on time + 0.4 x 16/18 read
        ("Full-Stack Foundations", 68, "watch"),  # 0.6 x 6/10 + 0.4 x 12/15
        ("Solo Track - Data", 100, "healthy"),
    ]
    assert (health[0]["on_time_rate"], health[0]["read_rate"], health[0]["overdue"]) == (0.33, 0.89, 6)


def test_health_score_moves_with_reading(morgan, client_as):
    liam = client_as("legolas.greenleaf@example.com")
    for notice in ("n2", "n3"):  # his two unread notices
        liam.post(f"/api/notices/{notice}/read")
    c1 = morgan.get("/api/cohorts/health").json()[0]
    assert (c1["cohort"]["name"], c1["read_rate"], c1["score"]) == ("Cloud Native Q4", 1.0, 60)


def test_csv_report_matches_the_health_numbers(morgan):
    resp = morgan.get("/api/cohorts/c1/report.csv")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/csv")
    assert resp.headers["content-disposition"].startswith('attachment; filename="cloud-native-q4-report-')

    rows = list(csv.DictReader(io.StringIO(resp.content.decode("utf-8-sig"))))
    assert [r["name"] for r in rows] == [
        "Aragorn son of Arathorn", "Frodo Baggins", "Legolas Greenleaf", "Meriadoc Brandybuck", "Peregrin Took", "Samwise Gamgee"
    ]
    jane = rows[1]  # Frodo: always a day early
    assert (jane["tasks_due"], jane["on_time"], jane["on_time_rate"], jane["overdue"], jane["read_rate"]) == ("5", "5", "1.00", "0", "1.00")
    # The report's totals reproduce the cohort's on-time rate: 10 of 30.
    assert (sum(int(r["on_time"]) for r in rows), sum(int(r["tasks_due"]) for r in rows)) == (10, 30)


def test_cohort_with_nothing_to_measure_has_no_score(manager, v1_seed):
    manager.post("/api/cohorts", json={"name": "Next year", "start_date": "2027-01-04"})
    entry = next(h for h in manager.get("/api/cohorts/health").json() if h["cohort"]["name"] == "Next year")
    assert (entry["score"], entry["status"]) == (None, "no_data")
