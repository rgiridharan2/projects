# NoticeBoardTracker — v3 (Auth + React)

Phase 3 adds three things to the v2 API:
- **JWT authentication** with bcrypt-hashed passwords.
- **Role-based access**: managers vs trainees, plus "you can only change your own reports".
- **A React frontend** with a password-protected user switcher and the trainee interface.

```
v3_auth/
  backend/    FastAPI + Postgres (v2 + auth). Its own database container on port 5434
  frontend/   Vite + React + Tailwind + TanStack Query + Axios + Lucide icons
```

The demo password for every seeded account is **`password123`**.

---

## Run plan

### One-time setup

`.venv` and `node_modules` already exist on your machine, so the install steps are only needed on a fresh clone.

**Backend** (PowerShell, from `v3_auth/backend`):

```powershell
docker compose up -d                 # Postgres for v3 on localhost:5434
python -m venv .venv                 # skip if .venv exists
.venv\Scripts\activate
pip install -r requirements.txt
alembic upgrade head                 # runs 0001 (tables) and 0002 (password column)
python seed.py                       # demo data; every account gets password123
```

**Frontend** (from `v3_auth/frontend`):

```powershell
npm install                          # skip if node_modules exists
```

### Every time: two terminals

| Terminal | Folder | Command | URL |
|---|---|---|---|
| 1 | `v3_auth/backend` (venv active) | `uvicorn app.main:app --reload` | http://localhost:8000/docs |
| 2 | `v3_auth/frontend` | `npm run dev` | **http://localhost:5173** |

Stop any v1 or v2 server first, since they also use port 8000. You can also stop the older databases to free memory:
`docker stop noticeboard-v2-db noticeboard-db`. Their data is kept, and `docker start` brings them back.

### Backend checks

| # | Do | Expect |
|---|---|---|
| 1 | `docker compose ps` | `noticeboard-v3-db … (healthy)` |
| 2 | `alembic current`, then `alembic check` | `0002 (head)`, then `No new upgrade operations detected.` |
| 3 | `pytest` | `59 passed` (on the separate `noticeboard_test` database) |
| 4 | Swagger: call `GET /api/cohorts` without logging in | **401** `Not authenticated` |
| 5 | Swagger: click **Authorize** (top right), username `jane.doe@example.com`, password `password123` | The padlocks close |
| 6 | As Jane, call `GET /api/notices/mine` and `GET /api/submissions/mine` | Only Jane's notices (with `read_at`) and her 5 reports |
| 7 | As Jane, call `GET /api/dashboard/stats` | **403** `Requires role: manager` |
| 8 | As Jane, `POST /api/submissions` with `{"trainee_id": "u3", "milestone_name": "x"}` | **403** `Trainees can only manage their own submissions` |
| 9 | **Authorize → Logout**, then log in as `u2` (Alex) and call `GET /api/dashboard/stats` | **200** `{12, 2, 4, 0.86}` |

### Frontend checks

| # | Do | Expect |
|---|---|---|
| 1 | Open http://localhost:5173 | "Choose your account" with 13 accounts, the manager first |
| 2 | Click **Jane Doe** and type a wrong password | The modal shows `Incorrect email/ID or password` and you stay logged out |
| 3 | Enter `password123` | The trainee view: notices on the left, the "Log progress" form and "My submissions" (5 reports) on the right |
| 4 | **Switch user → Ethan Brooks**, enter the password | Ethan's view: **3 new** notices and an empty timeline. None of Jane's data remains |
| 5 | Click **Acknowledge** on a notice | It turns to "✓ Acknowledged" instantly, and the badge drops to **2 new** |
| 6 | Fill the form (status **Stalled / blocked**, add a link and notes), then **Submit report** | "Submitted" appears, and the report shows at the top of the timeline with a red **Stalled** pill |
| 7 | **Switch user → Alex Smith** | The manager dashboard shows **12 / 3 / 3 / 89%**. Ethan's actions moved at-risk, overdue and read rate |
| 8 | Refresh the page | You stay logged in, because the token is saved in `localStorage` |
| 9 | Switch to **Liam Murphy** | His unread **urgent** notice is a red card with a red Acknowledge button |
| 10 | DevTools → Network → any `/api/...` request | Request headers include `Authorization: Bearer eyJ…` |
| 11 | The log-out icon (top right) | Back to the account picker |

`python seed.py` resets everything to the starting data.

---

## What changed from v2

| | v2 | v3 |
|---|---|---|
| Who can call the API | Anyone | Everyone except login needs a JWT; routes are restricted by role (table below) |
| `users` table | | `hashed_password` column (migration [0002](backend/alembic/versions/0002_add_user_password.py)) |
| `POST /api/trainees` | Anyone; name, email, cohort | Managers only; also requires `initial_password` |
| `POST /api/notices/{id}/read` | `trainee_id` in the body | **No body**: the trainee comes from the token, so nobody can acknowledge for someone else |
| `POST /api/submissions` | `status` was always `needs_review` | The trainee may choose a status (the brief's "Status Select"); `trainee_id` must be their own unless they're a manager |
| `PATCH /api/submissions/{id}/status` | Anyone | A manager, or the trainee who owns the report |
| New routes | | `POST /api/auth/login`, `POST /api/auth/token`, `GET /api/auth/me`, `GET /api/users/switch-options`, `GET /api/notices/mine`, `GET /api/submissions/mine` |
| Frontend | | React app in `frontend/` |
| Database | Port 5433 | Its own container on port 5434, so v2 keeps working unchanged |

### Who can call what

| Route | Public | Trainee | Manager |
|---|:-:|:-:|:-:|
| `POST /api/auth/login`, `POST /api/auth/token`, `GET /api/users/switch-options` | ✓ | ✓ | ✓ |
| `GET /api/auth/me`, `GET /api/cohorts` | | ✓ | ✓ |
| `GET /api/notices/mine`, `POST /api/notices/{id}/read`, `GET /api/submissions/mine` | | ✓ | |
| `POST /api/submissions`, `PATCH /api/submissions/{id}/status` | | own only | anyone's |
| `GET /api/cohorts/{id}/trainees`, `POST /api/trainees`, `POST /api/notices`, `GET /api/notices`, `GET /api/submissions`, `GET /api/dashboard/stats` | | | ✓ |

No token, or an invalid or expired one, returns **401**. The wrong role returns **403**.

---

## Implementation walkthrough

What each part does, how it works, and why. Links go to the exact lines.

## Backend

### 1. Password storage: [backend/app/security.py](backend/app/security.py)

**What.** Passwords are stored only as bcrypt hashes and checked with passlib.

**How.**
- **Hashing context.** `pwd_context` ([security.py:11](backend/app/security.py#L11)) is a passlib `CryptContext` using bcrypt. The cost factor comes from settings ([config.py:22](backend/app/config.py#L22)), default 12, which is about 0.25 s per hash.
- **Hashing.** `hash_password()` ([14-16](backend/app/security.py#L14-L16)) salts every hash randomly, so two users with the same password get different hashes.
- **Checking.** `verify_password()` ([19-28](backend/app/security.py#L19-L28)) runs `dummy_verify()` when the account doesn't exist ([25-27](backend/app/security.py#L25-L27)).
- **Storage.** The hash lives in `users.hashed_password` ([models.py:53](backend/app/models.py#L53)). Migration [0002](backend/alembic/versions/0002_add_user_password.py#L23) adds that column as **nullable**: a migration can't invent passwords for existing rows (docstring at [line 7](backend/alembic/versions/0002_add_user_password.py#L7)).
- **Where passwords come from.**
  - Managers set an `initial_password` when onboarding a trainee ([cohorts.py:42](backend/app/routers/cohorts.py#L42)).
  - The seed hashes `password123` once and reuses it ([seed.py:33](backend/seed.py#L33), [94](backend/seed.py#L94)).
- **Password field rules.** The `Password` type ([schemas.py:24](backend/app/schemas.py#L24)) turns off the whitespace-stripping every other input field gets, because spaces in a password matter. It also caps passwords at 72 characters, the most bcrypt uses.

**Why.**
- **bcrypt is deliberately slow and salted,** so a leaked table can't be reversed with lookup tables.
- **The dummy check** makes "no such user" take as long as "wrong password", so response times don't reveal which emails exist.
- **`bcrypt==4.0.1` is pinned** in [requirements.txt](backend/requirements.txt). passlib 1.7.4 (the brief's choice) is unmaintained and crashes with bcrypt 5, and 4.0.1 is the last version that works with it cleanly.

### 2. Tokens and login: [security.py](backend/app/security.py), [routers/auth.py](backend/app/routers/auth.py)

**What.** A successful login returns a signed JWT containing `{sub, role, cohort_id, iat, exp}`, as the brief specifies.

**How.**
- **Creating a token.** `create_access_token()` ([security.py:31-40](backend/app/security.py#L31-L40)) signs the claims with HS256 and `JWT_SECRET` ([config.py:17-19](backend/app/config.py#L17-L19)). It expires after 8 hours.
- **Decoding a token.** `decode_access_token()` ([43-47](backend/app/security.py#L43-L47)) rejects tokens with a bad signature or an expired `exp`, and tokens missing `sub` or `exp`.
- **`issue_token()`** ([auth.py:15-22](backend/app/routers/auth.py#L15-L22)):
  - looks the user up by email or ID (`get_by_identifier`, [user_repo.py:16](backend/app/repositories/user_repo.py#L16));
  - returns the same 401 message for a wrong account and a wrong password.
- **Two login routes share it:**
  - `POST /api/auth/login` ([25-28](backend/app/routers/auth.py#L25-L28)) takes JSON and is used by React.
  - `POST /api/auth/token` ([31-35](backend/app/routers/auth.py#L31-L35)) takes form fields, which is what Swagger's **Authorize** button sends.
- **`GET /api/auth/me`** ([38-41](backend/app/routers/auth.py#L38-L41)) returns whoever the token belongs to.

**Why.**
- **No server-side sessions.** Any request carrying a valid token can be checked on its own.
- **Swagger needs its own route.** The `/token` twin makes Swagger's built-in login work, so you can test locked routes without copying tokens by hand.

### 3. Reusable dependencies: [backend/app/auth.py](backend/app/auth.py)

**What.** These are `get_current_user`, `require_role([...])` and the shortcuts routes use: `CurrentUser`, `Manager` and `Trainee`.

**How.**
- **Reading the token.** `OAuth2PasswordBearer` ([auth.py:20](backend/app/auth.py#L20)) reads the `Authorization: Bearer` header. If it's missing, it returns 401.
- **`get_current_user`** ([23-41](backend/app/auth.py#L23-L41)) decodes the token, then **loads the user from the database** ([38](backend/app/auth.py#L38)).
- **`require_role(roles)`** ([47-55](backend/app/auth.py#L47-L55)) is a factory: it returns a dependency that returns 403 unless the user's role is in the list.
- **Shortcuts.** `Manager` and `Trainee` ([58-59](backend/app/auth.py#L58-L59)) are `require_role(["manager"])` and `require_role(["trainee"])` wrapped in `Annotated`. A route protects itself just by adding a parameter, e.g. `user: Manager`.
- **`ensure_owner_or_manager()`** ([62-65](backend/app/auth.py#L62-L65)) is the self-ownership rule.

**Why.**
- **The database decides the role, not the token.** Re-reading the user means a demoted or deleted account loses access straight away. The test at [test_auth.py:126](backend/tests/test_auth.py#L126) shows that even a validly signed token that *claims* `role: manager` can't promote a trainee.
- **Parameters make the guard visible.** Each route's guard shows in its signature, and Swagger shows a padlock on it.

### 4. Route guards and ownership: [backend/app/routers/](backend/app/routers/)

**What.** These are the rules in the access table above.

**How.**
- **Manager-only routes** add `user: Manager`:
  - [cohorts.py:23](backend/app/routers/cohorts.py#L23) and [30](backend/app/routers/cohorts.py#L30)
  - [notices.py:15](backend/app/routers/notices.py#L15) and [26](backend/app/routers/notices.py#L26)
  - [submissions.py:34](backend/app/routers/submissions.py#L34)
  - [dashboard.py:14](backend/app/routers/dashboard.py#L14)
- **Self-ownership on reports.** `create_submission` checks the ownership rule **before** anything else ([submissions.py:17](backend/app/routers/submissions.py#L17)), and `update_submission_status` checks it against the stored report's owner ([61](backend/app/routers/submissions.py#L61)).
- **Acknowledging a notice** takes the trainee from the token, not the body ([notices.py:50](backend/app/routers/notices.py#L50), [61](backend/app/routers/notices.py#L61)). It still checks the notice is addressed to their cohort ([58](backend/app/routers/notices.py#L58)).
- **Trainees choose a status** when submitting. It's stored as sent ([submissions.py:24](backend/app/routers/submissions.py#L24)) and defaults to `needs_review` ([schemas.py:142](backend/app/schemas.py#L142)).

**Why.**
- **Identity comes from the token.** Anything that identifies "who is acting" is taken from the verified token instead of the request body, which removes impersonation.
- **Managers bypass the ownership check,** as the brief requires, so they can review anyone's report or log one on a trainee's behalf.

### 5. Trainee endpoints: `/mine`

**What.** `GET /api/notices/mine` and `GET /api/submissions/mine` return only the caller's own data.

**How.**
- **The notice feed.** `notice_repo.list_feed()` ([notice_repo.py:31-41](backend/app/repositories/notice_repo.py#L31-L41)) LEFT JOINs read receipts **for this trainee only** ([38](backend/app/repositories/notice_repo.py#L38)). Each notice comes back with the trainee's own `read_at`, ordered unread first, then urgent, then newest ([40](backend/app/repositories/notice_repo.py#L40)).
- **The response.** The router wraps each row in `NoticeFeedItem` ([notices.py:41-46](backend/app/routers/notices.py#L41-L46), [schemas.py:103](backend/app/schemas.py#L103)).
- **Submissions.** `submission_repo.list_for_trainee()` ([submission_repo.py:22](backend/app/repositories/submission_repo.py#L22)) serves "my submissions" ([submissions.py:50](backend/app/routers/submissions.py#L50)).

**Why.**
- **Fixed scope.** Separate `/mine` routes keep manager lists (filter by any cohort) and trainee lists (always "me") simple. There's no route where a trainee could pass someone else's ID.
- **Acknowledge buttons need read status.** The UI needs each trainee's own `read_at` to know which notices still show an Acknowledge button. v2 had no way to read receipts back.

### 6. Switch-user options: [user_repo.py:27-35](backend/app/repositories/user_repo.py#L27-L35)

**What.** `GET /api/users/switch-options` ([routers/auth.py:44-51](backend/app/routers/auth.py#L44-L51)) returns `{id, name, role, cohort_name}` for each account, managers first.

**How.** One query LEFT JOINs `cohorts` for the cohort name. It also leaves out accounts with no password ([32](backend/app/repositories/user_repo.py#L32)), because they can't log in.

**Why it's public.** The login screen uses the same list before anyone is signed in. A real system wouldn't publish its user directory, so this is a deliberate demo shortcut (see [Trade-offs](#trade-offs)). Picking an account still requires its password.

### 7. No hash leaks: [schemas.py](backend/app/schemas.py)

Responses are built from the Pydantic schemas, which send only the fields they declare. `User` ([schemas.py:46](backend/app/schemas.py#L46)) has no `hashed_password`, so it can never be serialized, even though routes return the full SQLAlchemy object. [test_auth.py:85](backend/tests/test_auth.py#L85) checks the responses for `hashed_password` and `$2b$`.

### 8. Tests: [backend/tests/](backend/tests/)

59 tests, about 4 s.

- **Fast hashing.** [conftest.py:25](backend/tests/conftest.py#L25) drops bcrypt to cost 4 for tests, about 1 ms per hash instead of 250 ms.
- **Logged-in clients.** `client_as("u1")` ([78-86](backend/tests/conftest.py#L78-L86)) logs in and returns a client that sends that Bearer token on every request. `manager` and `jane` ([106-112](backend/tests/conftest.py#L106-L112)) are ready-made ones.
- **[test_auth.py](backend/tests/test_auth.py)** covers:
  - login by email or ID;
  - one identical 401 for every kind of bad credential;
  - the Swagger form login;
  - expired, forged and unknown-user tokens;
  - the role check against the database;
  - every manager-only and trainee-only route ([134-158](backend/tests/test_auth.py#L134-L158));
  - the ownership rules ([164-184](backend/tests/test_auth.py#L164-L184)).
- **[test_api.py](backend/tests/test_api.py)** and **[test_dashboard.py](backend/tests/test_dashboard.py)** are the v2 tests, now run through logged-in clients, plus checks that every seeded account can log in and that a self-reported "stalled" counts as at risk.

## Frontend

### 9. Dev proxy: [frontend/vite.config.js](frontend/vite.config.js)

**What and how.** The browser only talks to `localhost:5173`. Vite forwards `/api/*` to FastAPI ([vite.config.js:9-11](frontend/vite.config.js#L9-L11)).

**Why.**
- **No CORS setup.** The browser sees one origin, so the backend needs no CORS configuration.
- **`127.0.0.1`, not `localhost`.** Node can resolve `localhost` to IPv6 `::1`, and uvicorn only listens on IPv4. That mismatch causes a confusing `ECONNREFUSED` on Windows.

### 10. API client: [frontend/src/api.js](frontend/src/api.js)

**What.** This is the single Axios instance every request goes through.

**How.**
- **Attaching the token.** A request interceptor adds `Authorization: Bearer <token>` to every call ([api.js:18-22](frontend/src/api.js#L18-L22)).
- **Logging out on 401.** A response interceptor treats any 401 other than from login as "token expired" and logs out ([24-31](frontend/src/api.js#L24-L31)).
- **Readable errors.** `errorMessage()` ([34-40](frontend/src/api.js#L34-L40)) turns FastAPI's error shapes, including the list of 422 validation errors, into one readable line.

**Why.** No component handles tokens itself, so a new API call is automatically authenticated.

### 11. AuthContext: [frontend/src/auth/AuthContext.jsx](frontend/src/auth/AuthContext.jsx)

**What.** It exposes `currentToken`, `currentUser`, `login` and `logout` to every component through `useAuth()`.

**How.**
- **Restoring the session.** The saved session is loaded from `localStorage` before the first render ([AuthContext.jsx:15-17](frontend/src/auth/AuthContext.jsx#L15-L17)), so a page refresh keeps you logged in.
- **`login()`** ([25-39](frontend/src/auth/AuthContext.jsx#L25-L39)) calls `/api/auth/login`, then:
  1. hands the token to Axios;
  2. saves it to `localStorage`;
  3. **clears the TanStack Query cache** ([34](frontend/src/auth/AuthContext.jsx#L34));
  4. updates `currentUser`, which re-renders every view as the new user.
- **`logout()`** ([41-46](frontend/src/auth/AuthContext.jsx#L41-L46)) undoes all of that. It's also registered as the 401 handler ([49](frontend/src/auth/AuthContext.jsx#L49)).

**Why `clear()` rather than `invalidateQueries()`.** Invalidating would immediately refetch the *old* user's queries with the *new* token, storing the new user's data under the old user's cache keys. Clearing drops everything, and because every cache key includes the user ID ([queries.js:5-11](frontend/src/queries.js#L5-L11)), the new user's views fetch fresh data straight away. The result is what the brief asks for (views refresh immediately), with no chance of showing one person's data under another's login.

### 12. Data hooks: [frontend/src/queries.js](frontend/src/queries.js)

Every API call the UI makes is a TanStack Query hook in this one file.

- **`useAcknowledgeNotice`** ([26-45](frontend/src/queries.js#L26-L45)) is an **optimistic update**. It marks the card as read in the cache before the server answers, rolls back on error, then refetches to confirm. That's why "Acknowledge" feels instant.
- **`useMySubmissions`** ([47-54](frontend/src/queries.js#L47-L54)) refetches every 15 s and whenever the window regains focus. When a manager reviews a report, the trainee's status pill updates without a reload.
- **`useCreateSubmission`** attaches `trainee_id: currentUser.id` itself ([63](frontend/src/queries.js#L63)), so the form never asks for it. It then refreshes the timeline ([64](frontend/src/queries.js#L64)).

### 13. Password-guarded switcher: [Header.jsx](frontend/src/components/Header.jsx), [PasswordModal.jsx](frontend/src/components/PasswordModal.jsx), [LoginScreen.jsx](frontend/src/views/LoginScreen.jsx)

**What.** The top bar shows who you are. **Switch user** lists the other accounts, and choosing one asks for that account's password.

**How.**
- **Header.**
  - The identity badge ([Header.jsx:35-42](frontend/src/components/Header.jsx#L35-L42)) shows your avatar, name, and role with your cohort.
  - The switch menu ([44-77](frontend/src/components/Header.jsx#L44-L77)) lists `switch-options` minus yourself. It closes when you click outside it ([15-21](frontend/src/components/Header.jsx#L15-L21)).
  - Picking an account opens the modal ([91](frontend/src/components/Header.jsx#L91)).
- **PasswordModal.** It shows the chosen person's name and role, plus a password field. Submit calls `login()` ([PasswordModal.jsx:21-32](frontend/src/components/PasswordModal.jsx#L21-L32)). A wrong password shows the API's message inside the modal, and you stay signed in as before. Esc or clicking the backdrop closes it ([15-19](frontend/src/components/PasswordModal.jsx#L15-L19), [37](frontend/src/components/PasswordModal.jsx#L37)).
- **LoginScreen.** It reuses the same modal for the first sign-in.
- **App.** [App.jsx:15](frontend/src/App.jsx#L15) shows the trainee or manager view based on the role.

**Why.** Switching identities is a full re-login with a new token, not a client-side pretend. The backend enforces whatever the new token allows.

### 14. Trainee view: [TraineeView.jsx](frontend/src/views/TraineeView.jsx)

| Component | What and how | Why |
|---|---|---|
| [NoticeStream.jsx](frontend/src/components/NoticeStream.jsx) | **Unread urgent** notices are red cards and **read urgent** ones are amber ([tone, 40-47](frontend/src/components/NoticeStream.jsx#L40-L47)). The "N new" badge counts unread notices. **Acknowledge** calls the optimistic mutation ([28](frontend/src/components/NoticeStream.jsx#L28)). A grid layout puts the button under the text on phones and beside it on wider screens ([51-52](frontend/src/components/NoticeStream.jsx#L51-L52)) | Urgent items stand out until acknowledged, then calm down, so the board never loses them entirely |
| [MilestoneForm.jsx](frontend/src/components/MilestoneForm.jsx) | Milestone name, a **Status select**, a resource link (`type="url"`) and reflection notes with a character counter ([28-90](frontend/src/components/MilestoneForm.jsx#L28-L90)). Blank optional fields are sent as `null` ([19-23](frontend/src/components/MilestoneForm.jsx#L19-L23)). Server errors such as an invalid URL appear under the form ([76](frontend/src/components/MilestoneForm.jsx#L76)) | Self-reporting "Stalled" puts the trainee in the manager's at-risk count right away |
| [SubmissionTimeline.jsx](frontend/src/components/SubmissionTimeline.jsx) | A vertical timeline of `/submissions/mine` with a coloured `StatusPill` ([27](frontend/src/components/SubmissionTimeline.jsx#L27); pill styles at [ui.jsx:4-24](frontend/src/components/ui.jsx#L4-L24)). A small spinner shows during background refreshes ([15](frontend/src/components/SubmissionTimeline.jsx#L15)) | Trainees see their whole history and each report's current review status in one place |

[ManagerView.jsx](frontend/src/views/ManagerView.jsx) is deliberately minimal: four dashboard tiles. It proves the role switch works end to end. Full manager tools for posting notices and reviewing reports would come in the next phase.

---

## Trade-offs

These are decisions to know about before going beyond a demo:

| Choice | Why it's fine here | What production would do |
|---|---|---|
| Token stored in `localStorage` | The brief allowed it, and it survives refreshes | An httpOnly cookie, which page scripts (and so injected scripts) can't read |
| `GET /api/users/switch-options` is public | The login screen needs the account list | Require login, or replace it with a plain email + password form |
| Default `JWT_SECRET` in [config.py](backend/app/config.py#L17) | Fine for local development | A long random secret from the environment (see `.env.example`) |
| No refresh tokens; 8-hour expiry, then back to the login screen | Simple, and the 401 handler covers expiry | Short-lived access tokens plus refresh tokens |
| passlib with `bcrypt==4.0.1` pinned | Matches the brief and works | `pwdlib` (the library FastAPI's docs now recommend), or the maintained `libpass` fork |
| Trainees can change the status of their **own** reports | The brief: "trainee_id matches current_user.id unless manager" | If review should be manager-only, swap `user: CurrentUser` for `user: Manager` on [submissions.py:56](backend/app/routers/submissions.py#L56) |
