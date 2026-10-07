"""In-memory data store (stand-in for Postgres).

Each dict is a "table" keyed by primary key, and each value is a plain dict
"row" whose keys match the columns in app/schemas.py. Data resets on every
server restart.
"""

from datetime import date

COHORTS = {
    "c1": {"id": "c1", "name": "Cloud Native Q4", "track_type": "group", "start_date": date(2026, 10, 1)},
    "c2": {"id": "c2", "name": "Solo Track - Data", "track_type": "solo", "start_date": date(2026, 9, 15)},
}

USERS = {
    "u1": {"id": "u1", "name": "Jane Doe", "email": "jane.doe@example.com", "role": "trainee", "cohort_id": "c1"},
    "u2": {"id": "u2", "name": "Alex Smith", "email": "alex.smith@example.com", "role": "manager", "cohort_id": None},
}

NOTICES = {}
# Keyed by (notice_id, trainee_id), the table's composite primary key.
NOTICE_READS = {}
SUBMISSIONS = {}


def next_id(prefix: str, table: dict) -> str:
    """Next sequential id for a table, e.g. 'u3' (stand-in for a DB-generated PK)."""
    return f"{prefix}{max((int(k.removeprefix(prefix)) for k in table), default=0) + 1}"
