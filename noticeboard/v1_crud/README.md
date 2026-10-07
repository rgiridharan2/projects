# NoticeBoardTracker — v1 (in-memory CRUD)

Phase 1 backend: Pydantic data contracts and REST endpoints running on in-memory dicts.
There is no database yet, and all data resets when the server restarts.

## Run it

```powershell
cd v1_crud
py -3.12 -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt

uvicorn app.main:app --reload     # Swagger UI at http://localhost:8000/docs
python -m pytest -v                       # 17 API tests
```

## Layout

```
app/
  schemas.py        Pydantic contracts (read models = future tables, *Create = request bodies)
  data.py           In-memory "tables" + seed data
  lookups.py        get_cohort_or_404 / get_trainee_or_404
  routers/
    cohorts.py      cohorts & trainees
    notices.py      notice distribution + read receipts
    submissions.py  progress reports + manager review
  main.py           FastAPI app; "/" redirects to /docs
tests/              pytest suite (seed data is restored before each test)
```

## Seed data

| Table   | Rows |
|---------|------|
| COHORTS | `c1` Cloud Native Q4 (group), `c2` Solo Track - Data (solo) |
| USERS   | `u1` Jane Doe (trainee, c1), `u2` Alex Smith (manager) |
| NOTICES, NOTICE_READS, SUBMISSIONS | empty |

New records get sequential ids: `u3`, `n1`, `s1`, and so on.

## Endpoints

| Method | Path | Success | Errors |
|--------|------|---------|--------|
| GET    | `/api/cohorts` | 200, cohorts with `trainee_count` | |
| GET    | `/api/cohorts/{cohort_id}/trainees` | 200, roster | 404 unknown cohort |
| POST   | `/api/trainees` | 201, new trainee | 404 unknown cohort, 409 duplicate email |
| POST   | `/api/notices` | 201, new notice | 404 unknown target cohort |
| GET    | `/api/notices?cohort_id=` | 200, cohort + global notices, urgent first then newest | 404 unknown cohort |
| POST   | `/api/notices/{notice_id}/read` | 200, read receipt | 404 unknown notice/trainee, 400 notice not for trainee's cohort |
| POST   | `/api/submissions` | 201, new submission (`needs_review`) | 404 unknown trainee |
| GET    | `/api/submissions?cohort_id=` | 200, newest first | 404 unknown cohort |
| PATCH  | `/api/submissions/{submission_id}/status` | 200, updated submission | 404 unknown submission |

Any request body that fails validation returns 422. That covers a bad enum value, a malformed email or URL, a blank string, or an unknown field.

## Business rules

- **No duplicate trainees.** Emails are unique, compared case-insensitively, and stored in lowercase.
- **Server-owned fields can't be set by clients.** `id`, `role`, `status`, and all timestamps are assigned by the server. Sending one returns 422 (`extra="forbid"`).
- **Notice scoping.** `target_cohort_id: null` means the notice goes to all trainees. `GET /api/notices?cohort_id=c1` returns c1's notices plus the global ones. Without `cohort_id`, it returns every notice (manager view).
- **Read receipts are idempotent.** Marking a notice read twice keeps the first `read_at`. A trainee can only mark notices addressed to their own cohort or to everyone.
- **Submission review flow.** New submissions start as `needs_review`. Managers move them to `on_track` or `stalled` with the PATCH route.
- **Trainee-only actions.** A manager's id (e.g. `u2`) is rejected with 404 wherever a trainee is required.

## Implementation walkthrough

What each part does, how it's done, and why. The links go to the relevant lines.

### 1. Data contracts: [app/schemas.py](app/schemas.py)

**What.** Pydantic models for the five entities in the brief, plus the request bodies.

**How.**
- **Fixed sets of values** are `Literal` types ([schemas.py:17-20](app/schemas.py#L17-L20)), e.g. `Role = Literal["manager", "trainee"]`. Pydantic rejects anything else with a 422, and Swagger shows the allowed values as a dropdown.
- **Two base classes:**
  - `ReadModel` ([schemas.py:23-24](app/schemas.py#L23-L24)) sets `from_attributes=True`, so it can read SQLAlchemy objects later as well as dicts now.
  - `InputModel` ([schemas.py:27-28](app/schemas.py#L27-L28)) sets `extra="forbid"`, which rejects unknown fields, and `str_strip_whitespace=True`, so a value like `"   "` fails `min_length=1`.
- **Read models are the future tables:**
  - `User` ([34](app/schemas.py#L34))
  - `Cohort` ([51](app/schemas.py#L51))
  - `Notice` ([65](app/schemas.py#L65))
  - `NoticeReadStatus` ([85](app/schemas.py#L85))
  - `Submission` ([98](app/schemas.py#L98))
- **Input models leave out fields the server sets.** For example, `TraineeCreate` ([42](app/schemas.py#L42)) has no `id` or `role`, and `SubmissionCreate` ([108](app/schemas.py#L108)) has no `status` or `submitted_at`.
- **Field rules and examples:**
  - `EmailStr` and `HttpUrl` validate email and URL formats.
  - `Field(examples=[...])` prefills Swagger's "Try it out" with valid seed IDs (`c1`, `u1`).
- `CohortSummary` ([58](app/schemas.py#L58)) extends `Cohort` with a computed `trainee_count`. That number is calculated, so it isn't stored as a column.

**Why.** Keeping response models separate from request models stops clients from setting things they shouldn't, such as `role: "manager"` or a submission status. Each read model has exactly the columns of its future Postgres table, so moving to SQLAlchemy is a 1:1 mapping (see [Moving to Postgres](#moving-to-postgres)).

### 2. In-memory store: [app/data.py](app/data.py)

**What.** Module-level dicts act as tables, each keyed by its primary key.

**How.**
- `COHORTS` ([data.py:10](app/data.py#L10)) and `USERS` ([15](app/data.py#L15)) hold the seed rows from the brief. I added `email` and `start_date`, which the brief's seed didn't have.
- `NOTICES`, `NOTICE_READS` and `SUBMISSIONS` ([20-23](app/data.py#L20-L23)) start empty. `NOTICE_READS` is keyed by a `(notice_id, trainee_id)` tuple, which is the same composite key the table will have in Postgres.
- `next_id()` ([26-28](app/data.py#L26-L28)) takes the largest numeric suffix in a table and adds 1, giving `u3`, `n1`, `s1`, and so on.

**Why.** Rows are plain dicts whose keys match the schema fields, so the response models can validate them directly. The composite key makes duplicate read receipts impossible by design, just like a primary key would in Postgres.

### 3. Shared lookups: [app/lookups.py](app/lookups.py)

**What.** `get_cohort_or_404` ([lookups.py:8](app/lookups.py#L8)) and `get_trainee_or_404` ([15](app/lookups.py#L15)).

**How.** Each one fetches a record by ID and raises `HTTPException(404)` if it's missing. The trainee lookup also returns 404 when the ID belongs to a manager.

**Why.** Every route that receives an ID checks it the same way and returns the same error message. Treating a manager's ID as "not a trainee" means managers can't submit reports or mark notices read.

### 4. Cohorts & trainees: [app/routers/cohorts.py](app/routers/cohorts.py)

| Route | How it works | Why |
|---|---|---|
| `GET /api/cohorts` ([12-16](app/routers/cohorts.py#L12-L16)) | A `Counter` counts trainees per cohort in one pass ([line 15](app/routers/cohorts.py#L15)), and each cohort is returned with its `trainee_count` | Gives managers a summary of every cohort, so nobody has to tally the spreadsheet by hand |
| `GET /api/cohorts/{id}/trainees` ([19-23](app/routers/cohorts.py#L19-L23)) | Checks the cohort exists, then keeps only `role == "trainee"` users in that cohort | One roster per cohort, so trainees can't go untracked |
| `POST /api/trainees` ([26-42](app/routers/cohorts.py#L26-L42)) | Lowercases the email ([30](app/routers/cohorts.py#L30)) and rejects it with **409** if it already exists ([31-32](app/routers/cohorts.py#L31-L32)). The server sets `role="trainee"` and the ID | Addresses the "duplicated entries" pain point. In Postgres this becomes a `UNIQUE` constraint on `email` |

### 5. Notices: [app/routers/notices.py](app/routers/notices.py)

| Route | How it works | Why |
|---|---|---|
| `POST /api/notices` ([12-24](app/routers/notices.py#L12-L24)) | Checks the target cohort only if one was given. `target_cohort_id: null` means everyone. The server sets `created_at` | A single field covers both "send to one cohort" and "send to everyone" |
| `GET /api/notices?cohort_id=` ([27-41](app/routers/notices.py#L27-L41)) | Keeps notices where `target_cohort_id in (None, cohort_id)` ([38](app/routers/notices.py#L38)), sorts newest first, then sorts again by urgency ([40-41](app/routers/notices.py#L40-L41)). Python's sort keeps the newest-first order within each urgency level | A trainee sees their cohort's notices plus the global ones, with urgent items on top. Leaving out `cohort_id` returns every notice for managers |
| `POST /api/notices/{id}/read` ([44-57](app/routers/notices.py#L44-L57)) | Returns 400 if the notice was sent to a different cohort ([51](app/routers/notices.py#L51)). Writes a receipt only if one doesn't already exist ([54-57](app/routers/notices.py#L54-L57)) | Marking a notice read twice keeps the first `read_at`. That replaces chasing people over 1:1 messages with a record of who has read what |

### 6. Submissions: [app/routers/submissions.py](app/routers/submissions.py)

| Route | How it works | Why |
|---|---|---|
| `POST /api/submissions` ([12-27](app/routers/submissions.py#L12-L27)) | Only trainees can submit. The status is always set to `"needs_review"` ([21](app/routers/submissions.py#L21)). `HttpUrl` is converted to `str` before storing ([22](app/routers/submissions.py#L22)) | Every new report goes into the manager's review queue. The URL is stored as a string because the database column will be `TEXT` |
| `GET /api/submissions?cohort_id=` ([30-44](app/routers/submissions.py#L30-L44)) | Builds a set of the cohort's trainee IDs ([41](app/routers/submissions.py#L41)) and keeps their submissions, newest first ([44](app/routers/submissions.py#L44)) | Managers see recent progress per cohort without waiting for updates. In Postgres this becomes a `JOIN users` |
| `PATCH /api/submissions/{id}/status` ([47-55](app/routers/submissions.py#L47-L55)) | Accepts only `{"status": ...}` (`SubmissionStatusUpdate`, [schemas.py:115](app/schemas.py#L115)) and updates the stored row | Managers can only change the status. The rest of the report stays as the trainee submitted it |

### 7. App wiring: [app/main.py](app/main.py)

The three routers are registered at [main.py:12-14](app/main.py#L12-L14). Their `tags` group the Swagger page into "Cohorts & Trainees", "Notices" and "Submissions". Visiting `/` redirects to `/docs` ([17-19](app/main.py#L17-L19)), which opens Swagger UI.

### 8. Tests: [tests/](tests/)

- The `reset_store` fixture in [conftest.py:12-19](tests/conftest.py#L12-L19) runs around every test (`autouse=True`). It deep-copies every table before the test and restores it afterwards, so tests start from the same seed data and can't affect each other.
- [test_api.py](tests/test_api.py) has 17 tests that cover the success case, the 404/409/400 business-rule errors, and the 422 validation errors for every route.
- `pytest.ini` sets `pythonpath = .` so that `import app` works when you run plain `pytest`.

## Moving to Postgres

Each read model in `schemas.py` maps to one table, field for field:

| Schema | Table | Keys |
|--------|-------|------|
| `User` | `users` | PK `id`, unique `email`, FK `cohort_id → cohorts.id` (nullable) |
| `Cohort` | `cohorts` | PK `id` |
| `Notice` | `notices` | PK `id`, FK `target_cohort_id → cohorts.id` (nullable) |
| `NoticeReadStatus` | `notice_reads` | composite PK `(notice_id, trainee_id)` |
| `Submission` | `submissions` | PK `id`, FK `trainee_id → users.id` |

The read models already set `from_attributes=True`, so they can serialize SQLAlchemy rows unchanged.
The swap touches `data.py` (becomes models + a session) and the dict lookups inside the routers. The schemas and the API contract stay the same.
