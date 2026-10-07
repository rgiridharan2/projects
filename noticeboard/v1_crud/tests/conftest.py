from copy import deepcopy

import pytest
from fastapi.testclient import TestClient

from app import data
from app.main import app

TABLES = [data.COHORTS, data.USERS, data.NOTICES, data.NOTICE_READS, data.SUBMISSIONS]


@pytest.fixture(autouse=True)
def reset_store():
    """Give every test a fresh copy of the seed data."""
    snapshot = [deepcopy(table) for table in TABLES]
    yield
    for table, saved in zip(TABLES, snapshot):
        table.clear()
        table.update(saved)


@pytest.fixture
def client():
    return TestClient(app)
