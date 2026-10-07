# NoticeBoardTracker — v2 (PostgreSQL)

Phase 2 replaces v1's in-memory dicts with PostgreSQL, using SQLAlchemy 2.0, psycopg 3 and Alembic.
It also adds a seed script and a manager dashboard endpoint.
The API contract is unchanged from v1: same routes, same request and response shapes, same ID format.

**New to Postgres?** Start with [SETUP_POSTGRES.md](SETUP_POSTGRES.md).

## Run and check

Run these from `v2_postgres` in PowerShell.

| # | Run | Check |
|---|-----|-------|
| 1 | `docker compose up -d` | `docker compose ps` shows `noticeboard-v2-db … (healthy)` |
| 2 | `python -m venv .venv`<br>`.venv\Scripts\activate`<br>`pip install -r requirements.txt` | Installs without errors |
| 3 | `alembic upgrade head` | Prints `Running upgrade  -> 0001, initial schema` |
| 4 | `alembic current`<br>`alembic check` | `0001 (head)`<br>`No new upgrade operations detected.` (models and DB match) |
| 5 | `python seed.py` | Prints counts: 3 cohorts, 12 trainees, 1 manager, 5 notices, 31 read receipts, 34 submissions |
| 6 | `pytest` | `27 passed` (uses its own `noticeboard_test` database, so your seed data is untouched) |
| 7 | `uvicorn app.main:app --reload` | http://localhost:8000/docs shows 4 groups, including **Dashboard**. Stop the v1 server first, or add `--port 8001` |
| 8 | `docker exec -it noticeboard-v2-db psql -U noticeboard -c "\d users"` | Lists `fk_users_cohort_id_cohorts` under "Foreign-key constraints" |

### Swagger checks after seeding

| Do | Expect |
|----|--------|
| `GET /api/dashboard/stats` | `{"total_active": 12, "at_risk": 2, "overdue_submissions": 4, "read_rates": 0.86}` |
| `GET /api/cohorts` | c1 Cloud Native Q4 = 6, c2 Solo Track - Data = 1, c3 Full-Stack Foundations = 5 |
| `GET /api/notices?cohort_id=c1` | n2 (urgent) first, then n3, n1. No n4 or n5 (those target c3 and c2) |
| `GET /api/submissions?cohort_id=c2` | Aisha's 3 reports, newest (`stalled`) first |
| `POST /api/submissions` `{"trainee_id": "u5", "milestone_name": "Week 5: CI/CD pipelines"}` | 201. Then stats show `at_risk: 1`, because Tom's latest report is no longer stalled |
| `POST /api/notices/n1/read` `{"trainee_id": "u13"}` | 200. Then `read_rates: 0.89` (Ethan read the welcome notice: 32 of 36) |
| `POST /api/submissions` `{"trainee_id": "u13", "milestone_name": "Week 1: HTML & CSS"}` | Then `overdue_submissions: 3` |
| Stop and restart uvicorn, then `GET /api/cohorts` | Your changes are still there, unlike v1 |
| `python seed.py` | Resets everything back to the numbers above |

The [v1 Swagger checklist](../v1_crud/README.md) also passes on v2. Run it on a freshly wiped database, or expect the next IDs after seeding to be `u14`, `n6`, `s35` instead of `u3`, `n1`, `s1`.

## What changed from v1

| | v1 | v2 |
|---|---|---|
| Storage | Dicts in `data.py`, lost on restart | Postgres tables ([app/models.py](app/models.py)) that persist |
| Creating tables | n/a | Alembic migration ([0001_initial_schema.py](alembic/versions/0001_initial_schema.py)) |
| Data access | Routers read and write dicts | Routers call a **repository layer** ([app/repositories/](app/repositories/)) |
| IDs | `max + 1` computed in Python | Same `u14` format, numbered by a Postgres sequence |
| New endpoints | | `GET /api/dashboard/stats`, `limit` on `GET /api/submissions` |
| Demo data | 2 hard-coded rows | `python seed.py`: wipes and reloads a realistic dataset |
| Tests | 17, in-memory | 27, against a real Postgres test database, including migration tests |

## Layout

```
docker-compose.yml        Postgres 16 on localhost:5433
alembic.ini, alembic/     migrations (env.py + versions/0001_initial_schema.py)
seed.py                   wipe + load demo data
app/
  config.py               DATABASE_URL / TEST_DATABASE_URL (env vars or .env)
  db.py                   engine, session factory, get_db dependency
  models.py               SQLAlchemy tables
  schemas.py              Pydantic contracts (v1 + DashboardStats)
  lookups.py              fetch-or-404 checks
  repositories/           all SQL: cohort_, user_, notice_, submission_, dashboard_repo + ids
  routers/                cohorts, notices, submissions, dashboard
tests/                    conftest (test DB setup), test_api, test_dashboard, test_migrations
```

## Seed data

Dates are relative to the day you run `seed.py`, so the dashboard numbers come out the same every time.
Each trainee is there to exercise a specific case:

| Trainee (id) | Cohort | Reports | Latest | Dashboard effect |
|---|---|---|---|---|
| Jane Doe (u1) | c1 | 5 | 2 days ago, needs_review | |
| Marcus Chen (u3), Priya Patel (u4) | c1 | 5 each | 1–3 days ago | |
| Tom Okafor (u5) | c1 | 4 | 4 days ago, **stalled** | at risk |
| Sofia Rossi (u6) | c1 | 3 | **12 days ago** | overdue |
| Liam Murphy (u7) | c1 | 2 | **20 days ago** | overdue, 2 unread notices |
| Aisha Khan (u8) | c2 (solo) | 3 | 5 days ago, **stalled** | at risk |
| Diego, Hannah, Kenji (u9–u11) | c3 | 2 each | 1–3 days ago | |
| Grace Mensah (u12) | c3 | 1 | **10 days ago** | overdue |
| Ethan Brooks (u13) | c3 | **0** | never | overdue, 3 unread notices (the "untracked trainee") |

Alex Smith (u2) is the manager. The 5 notices are 2 global, 1 each for c1, c2 and c3, with 2 of them urgent. That's 36 deliveries, of which 31 have been read.

## Dashboard definitions

`GET /api/dashboard/stats`. These definitions also appear in Swagger under the `DashboardStats` schema.

| Field | Definition |
|---|---|
| `total_active` | Trainees in a cohort whose `start_date` is today or earlier |
| `at_risk` | Active trainees whose **most recent** submission is `stalled`. A newer report or a manager review clears it |
| `overdue_submissions` | Active trainees with no submission in the last 7 days. Trainees who have never submitted count once their cohort is more than 7 days old |
| `read_rates` | Of all (notice, active trainee) pairs a notice was meant for, the fraction with a read receipt, rounded to 2 decimals. `0.0` when there are no notices |

None of these were defined in the brief, so I chose them. Change them in [dashboard_repo.py](app/repositories/dashboard_repo.py).

---

## Implementation walkthrough

What each part does, how it works, and why. Links go to the exact lines.

### 1. Connection: [app/config.py](app/config.py), [app/db.py](app/db.py)

**What.** The settings, the database engine, and one session per request.

**How.**
- `Settings` ([config.py:8-14](app/config.py#L8-L14)) reads `DATABASE_URL` and `TEST_DATABASE_URL` from environment variables or `.env`. The defaults match `docker-compose.yml`, so no `.env` is needed.
- [db.py:9-11](app/db.py#L9-L11) creates the engine and a `sessionmaker` with `expire_on_commit=False`.
- `get_db()` ([db.py:14-17](app/db.py#L14-L17)) opens a session for each request and closes it afterwards.
- `DB = Annotated[Session, Depends(get_db)]` ([db.py:20](app/db.py#L20)) lets every route ask for a session with just `db: DB`.

**Why.** Routes never create connections themselves. The tests swap in a test database by overriding one dependency (see section 8).

### 2. Tables: [app/models.py](app/models.py)

**What.** One SQLAlchemy class per v1 read model, with the same column names.

**How.**
- **The three required foreign keys:**
  - `users.cohort_id → cohorts.id` ([models.py:51](app/models.py#L51))
  - `notices.target_cohort_id → cohorts.id` ([63](app/models.py#L63))
  - `submissions.trainee_id → users.id` ([82](app/models.py#L82))
- **`notice_reads`** ([67-73](app/models.py#L67-L73)) has a composite primary key `(notice_id, trainee_id)`, and both columns are also foreign keys.
- **Constraints and indexes.**
  - `users.email` is `unique=True` ([49](app/models.py#L49)). Every foreign-key column is indexed, because Postgres doesn't index them automatically.
  - A naming convention ([14-23](app/models.py#L14-L23)) gives every constraint a predictable name, such as `fk_users_cohort_id_cohorts`.
- **Plain string columns for enum fields.** Role, priority and status are plain `String` columns, with no Postgres `ENUM`, `CHECK` or triggers. The Pydantic `Literal` types in [schemas.py](app/schemas.py) already enforce the allowed values (see the docstring at [models.py:1-5](app/models.py#L1-L5)).
- **IDs.** Each class declares an `id_prefix` and its own Postgres `Sequence` (e.g. [34](app/models.py#L34)).

**Why.**
- **Foreign keys** make bad references impossible at the database level, even if a bug skips the Python checks.
- **Named constraints** let future migrations alter or drop them by name.
- **Plain strings** keep migrations simple: adding a status later doesn't need an `ALTER TYPE`.
- **Sequence-based IDs** keep v1's `u14` format so the API contract doesn't change. A sequence never hands out the same number twice, which fixes the race in v1's `max + 1` approach.

### 3. Migrations: [alembic/](alembic/)

**What.** Alembic creates and versions the schema. `alembic upgrade head` builds the tables, and `alembic downgrade base` removes them.

**How.**
- [env.py:16](alembic/env.py#L16) points Alembic at `Base.metadata`. This lets `--autogenerate` and `alembic check` compare the models against the database.
- [env.py:19](alembic/env.py#L19) uses `DATABASE_URL` unless the caller passes its own URL (the tests do).
- [0001_initial_schema.py](alembic/versions/0001_initial_schema.py) was autogenerated, then tidied. The foreign keys are at [45](alembic/versions/0001_initial_schema.py#L45), [59](alembic/versions/0001_initial_schema.py#L59), [71-72](alembic/versions/0001_initial_schema.py#L71-L72) and [85](alembic/versions/0001_initial_schema.py#L85).
- Autogenerate can't detect standalone sequences, so I added them by hand ([22-27](alembic/versions/0001_initial_schema.py#L22-L27)).
- `downgrade()` ([91-104](alembic/versions/0001_initial_schema.py#L91-L104)) drops child tables before parents, then the sequences.

**Why.** Schema changes become versioned files that every machine applies the same way, instead of hand-run SQL. To change the schema later:
1. Edit `models.py`.
2. Run `alembic revision --autogenerate --rev-id 0002 -m "describe change"`.
3. Review the generated file.
4. Run `alembic upgrade head`.

### 4. Repository layer: [app/repositories/](app/repositories/)

**What.** Every SQL query lives here, one module per table plus `dashboard_repo`.

**How.**
- **The rule** ([\_\_init\_\_.py](app/repositories/__init__.py)): repository functions take a `Session`, call `flush()` after writes, and **never commit**.
- `next_id()` ([ids.py:5-7](app/repositories/ids.py#L5-L7)) builds an ID like `u14` from the model's prefix plus `nextval` on its sequence.
- `list_with_trainee_counts()` ([cohort_repo.py:14-22](app/repositories/cohort_repo.py#L14-L22)) counts trainees with one `LEFT JOIN … GROUP BY`. v1 looped over every user in Python instead.
- `list_for_cohort()` ([notice_repo.py:15-21](app/repositories/notice_repo.py#L15-L21)) puts urgent notices first with `ORDER BY CASE`, then newest first.
- `mark_read()` ([notice_repo.py:40-50](app/repositories/notice_repo.py#L40-L50)) uses `INSERT … ON CONFLICT DO NOTHING`. A second read is a no-op, even if two requests arrive at the same moment.
- `list_recent()` ([submission_repo.py:14-19](app/repositories/submission_repo.py#L14-L19)) filters by cohort with a `JOIN users`.

**Why.**
- **One place for SQL.** Routers contain only HTTP logic.
- **Reuse.** The seed script and the tests reuse the same functions.
- **Caller-controlled transactions.** Because repositories don't commit, the caller decides what is one transaction. A route is one transaction, and the whole seed run is one transaction.

### 5. Relationship rules in Python: [app/lookups.py](app/lookups.py) and [app/routers/](app/routers/)

**What.** The routes and validation rules are the same as v1, now backed by Postgres.

**How.**
- Before any write, `get_cohort_or_404` / `get_trainee_or_404` ([lookups.py:14-25](app/lookups.py#L14-L25)) confirm the referenced row exists, and that a trainee ID really belongs to a trainee.
- Duplicate emails are caught with `get_by_email` before inserting ([cohorts.py:31](app/routers/cohorts.py#L31)).
- Each write route commits exactly once, at the end:
  - [cohorts.py:35](app/routers/cohorts.py#L35)
  - [notices.py:20](app/routers/notices.py#L20) and [notices.py:49](app/routers/notices.py#L49)
  - [submissions.py:27](app/routers/submissions.py#L27) and [submissions.py:54](app/routers/submissions.py#L54)

**Why.** The brief asked for relationship constraints to be handled in Python, which also gives clean 404/409 errors instead of raw database errors. The database constraints stay as a backstop: if two requests race with the same email, the `UNIQUE` index still prevents a duplicate.

### 6. Dashboard: [app/repositories/dashboard_repo.py](app/repositories/dashboard_repo.py)

**What.** `GET /api/dashboard/stats` ([routers/dashboard.py](app/routers/dashboard.py)), computed with two aggregate queries.

**How.**
1. **`active`** ([16-21](app/repositories/dashboard_repo.py#L16-L21)) is a subquery of trainees whose cohort has started.
2. **`latest`** ([24-32](app/repositories/dashboard_repo.py#L24-L32)) numbers each trainee's submissions newest first with `row_number() OVER (PARTITION BY trainee_id …)` and keeps row 1.
3. **The first query** ([39-47](app/repositories/dashboard_repo.py#L39-L47)) produces all three trainee counts at once, using `count(*) FILTER (WHERE …)` with the overdue condition from [35-38](app/repositories/dashboard_repo.py#L35-L38). The `LEFT JOIN` keeps trainees who have never submitted.
4. **The second query** ([50-63](app/repositories/dashboard_repo.py#L50-L63)) builds every (notice, intended trainee) pair and left-joins the read receipts. The rate is rounded at [69](app/repositories/dashboard_repo.py#L69).
5. The response shape is `DashboardStats` ([schemas.py:121](app/schemas.py#L121)), with each definition in its field description.

**Why.** The counting happens in Postgres, so the endpoint costs two queries however many trainees there are. Using "latest submission" for at-risk means managers see the current state, not old history. Counting "never submitted" as overdue targets the brief's "untracked/missing trainees" pain point.

### 7. Seed script: [seed.py](seed.py)

**What.** `python seed.py` wipes the database and loads the demo data shown above.

**How.**
- **Data.** The data is plain tables at the top of the file ([23-61](seed.py#L23-L61)). Each trainee row encodes its story: reports sent, days since the last one, latest status.
- **`wipe()`** ([69-75](seed.py#L69-L75)) deletes child tables before parents, so no foreign key is ever left dangling, then restarts the sequences so IDs start again at `c1`, `u1`, `n1` and `s1`.
- **`seed()`** ([78-142](seed.py#L78-L142)) inserts everything through the repository functions:
  - Weekly reports are spaced 7 days apart, counting back from each trainee's latest ([101-115](seed.py#L101-L115)).
  - A read receipt is created for every delivered notice except the pairs listed in `UNREAD` ([128-133](seed.py#L128-L133)).
- **`main()`** ([145-162](seed.py#L145-L162)) runs the wipe and the seed in **one transaction**. A clear message appears if Postgres is down or the migrations haven't run.

**Why.** Relative dates keep the dashboard numbers stable no matter when you run the script. The single transaction means a failed seed changes nothing. The tests import `wipe` and `seed` too, so the seed script itself is tested.

### 8. Tests: [tests/](tests/)

**What.** 27 tests against a real Postgres database called `noticeboard_test`.

**How.**
- **Setup, once per run.** [conftest.py](tests/conftest.py) creates the test database if it's missing ([27-34](tests/conftest.py#L27-L34)) and migrates it with Alembic ([46](tests/conftest.py#L46)).
- **Before each test,** it calls `wipe()` ([55](tests/conftest.py#L55)) and points the app's `get_db` at the test database ([66](tests/conftest.py#L66)).
- **The files:**
  - [test_api.py](tests/test_api.py): v1's 17 tests, unchanged, on the v1 seed rows ([`v1_seed`](tests/conftest.py#L71-L79)), plus 2 new tests for `limit` and for writes being committed.
  - [test_dashboard.py](tests/test_dashboard.py): the dashboard on an empty database and on the seed data, and how it responds to new reports, reads, manager reviews, and cohorts that haven't started yet.
  - [test_migrations.py](tests/test_migrations.py): `alembic check` (models match the migrations) and a full downgrade and upgrade.

**Why.** Passing v1's tests unchanged proves the API contract survived the switch to Postgres. Running the real migrations in the tests catches drift between models and schema.
