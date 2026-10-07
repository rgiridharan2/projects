"""Tests run against a separate database (TEST_DATABASE_URL), never the one seed.py fills.

Once per run: create the test database if it's missing and migrate it with Alembic, so the
migrations themselves are tested. Before every test: wipe all rows and restart the id sequences.
"""

from datetime import date
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, make_url, text
from sqlalchemy.orm import sessionmaker

from app.config import settings
from app.db import get_db
from app.main import app
from app.repositories import cohort_repo, user_repo
from app.security import hash_password, pwd_context
from seed import DEMO_PASSWORD, wipe

# bcrypt at cost 4 instead of 12: ~1 ms per hash instead of ~250 ms, so the suite stays fast.
pwd_context.update(bcrypt__rounds=4)

PROJECT_DIR = Path(__file__).resolve().parent.parent
TEST_URL = make_url(settings.test_database_url)


def create_database_if_missing(url) -> None:
    # CREATE DATABASE can't run inside a transaction, hence AUTOCOMMIT on the built-in "postgres" database.
    admin = create_engine(url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        if not conn.scalar(text("SELECT 1 FROM pg_database WHERE datname = :name"), {"name": url.database}):
            conn.execute(text(f'CREATE DATABASE "{url.database}"'))
    admin.dispose()


@pytest.fixture(scope="session")
def alembic_config():
    cfg = Config(str(PROJECT_DIR / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", TEST_URL.render_as_string(hide_password=False))
    return cfg


@pytest.fixture(scope="session")
def sessions(alembic_config):
    create_database_if_missing(TEST_URL)
    command.upgrade(alembic_config, "head")
    engine = create_engine(TEST_URL)
    yield sessionmaker(engine, expire_on_commit=False)
    engine.dispose()


@pytest.fixture
def db(sessions):
    with sessions() as session:
        wipe(session)
        session.commit()
        yield session


@pytest.fixture
def client(sessions, db):
    """An anonymous client (no token)."""

    def get_test_db():
        with sessions() as session:
            yield session

    app.dependency_overrides[get_db] = get_test_db
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def client_as(client):
    """client_as("u1") logs in and returns a client that sends that user's Bearer token on every request."""

    def log_in(identifier: str, password: str = DEMO_PASSWORD) -> TestClient:
        resp = client.post("/api/auth/login", json={"identifier": identifier, "password": password})
        assert resp.status_code == 200, resp.text
        return TestClient(app, headers={"Authorization": f"Bearer {resp.json()['access_token']}"})

    return log_in


@pytest.fixture
def v1_seed(db):
    """The v1 seed rows: c1, c2, u1 (Jane, trainee in c1) and u2 (Alex, manager), password `password123`."""
    hashed = hash_password(DEMO_PASSWORD)
    c1 = cohort_repo.create(db, name="Cloud Native Q4", track_type="group", start_date=date(2026, 10, 1))
    c2 = cohort_repo.create(db, name="Solo Track - Data", track_type="solo", start_date=date(2026, 9, 15))
    user_repo.create(
        db, name="Jane Doe", email="jane.doe@example.com", role="trainee", cohort_id=c1.id, hashed_password=hashed
    )
    user_repo.create(
        db, name="Alex Smith", email="alex.smith@example.com", role="manager", cohort_id=None, hashed_password=hashed
    )
    db.commit()
    assert (c1.id, c2.id) == ("c1", "c2")


@pytest.fixture
def manager(v1_seed, client_as):
    return client_as("u2")


@pytest.fixture
def jane(v1_seed, client_as):
    return client_as("u1")
