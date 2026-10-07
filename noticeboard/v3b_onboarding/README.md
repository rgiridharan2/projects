# NoticeBoardTracker — v3b (Onboarding & Trainee Portal)

Phase 3b builds on [v3](../v3_auth/README.md), which added JWT login, roles and the React app. It adds:

- **Self sign-up.** People can join a cohort themselves, but only as trainees. Managers come from the seed.
- **Milestones (tasks) with due dates.** Each trainee's task status is worked out from their reports.
- **A split hero landing page.** A looping animation sits beside a tabbed "Sign in / Join cohort" card.
- **A new trainee dashboard.** It has a time-of-day greeting with a pending-task alert, a monthly review grid, and an active task card with cohort peers and a submit button.

`v3_auth/` is unchanged and still runs on its own. v3b has its own database container on port **5435**.

The demo password for every seeded account is **`password123`**. The manager from the brief is **`manager@edtech.com`**.

---

## Run plan

### One-time setup

`.venv` and `node_modules` already exist on your machine.

**Backend** (from `v3b_onboarding/backend`):

```powershell
docker compose up -d                 # Postgres for v3b on localhost:5435
.venv\Scripts\activate               # (fresh clone: python -m venv .venv, then pip install -r requirements.txt)
alembic upgrade head                 # 0001 tables, 0002 passwords, 0003 milestones + sign-up flag
python seed.py                       # 3 cohorts, 20 milestones, 12 trainees, 2 managers, 34 reports
```

**Frontend** (from `v3b_onboarding/frontend`): `npm install`, only needed on a fresh clone.

### Every time: two terminals

| Terminal | Folder | Command | URL |
|---|---|---|---|
| 1 | `v3b_onboarding/backend` (venv active) | `uvicorn app.main:app --reload` | http://localhost:8000/docs |
| 2 | `v3b_onboarding/frontend` | `npm run dev` | **http://localhost:5173** |

**Stop the v3 servers first**, because v3 uses the same two ports (Ctrl+C in their terminals). To run both versions side by side, start v3b on other ports:

```powershell
# terminal 1
uvicorn app.main:app --reload --port 8001
# terminal 2
$env:API_URL="http://127.0.0.1:8001"; npm run dev -- --port 5174
```

The `API_URL` variable tells Vite's proxy where the backend is ([vite.config.js:7](frontend/vite.config.js#L7)).

### Backend checks

| # | Do | Expect |
|---|---|---|
| 1 | `alembic current`, then `alembic check` | `0003 (head)`, then `No new upgrade operations detected.` |
| 2 | `pytest` | `87 passed` |
| 3 | Swagger, logged out: `GET /api/cohorts/public-list` | **200**: Cloud Native Q4 and Full-Stack Foundations. The solo track is hidden |
| 4 | `POST /api/auth/signup` with `{"name":"Sam","email":"sam@example.com","password":"password123","cohort_id":"c1"}` | **201** with a token. `user.role` is `"trainee"` |
| 5 | The same request plus `"role":"manager"` | **422**: sign-up has no role field |
| 6 | Sign up with `"cohort_id":"c2"` (the solo track) | **400** `Cohort 'c2' is not open for sign-up` |
| 7 | `GET /api/users/switch-options` without logging in | **401**: it needs a login now (it was public in v3) |
| 8 | **Authorize** as `jane.doe@example.com`, then `GET /api/milestones/mine` | 8 tasks: 4 `completed`, 1 `under_review`, 3 `pending`. Week 6 is due today |
| 9 | As Jane, `POST /api/submissions` with `{"trainee_id":"u1","milestone_id":"m6"}` | **201**. `milestone_name` is filled in as "Week 6: Observability" |
| 10 | As Jane, the same with `"milestone_id":"m9"` (another cohort's task) | **400** |
| 11 | **Authorize** as `manager@edtech.com`, then `POST /api/milestones` with `{"cohort_id":"c1","title":"Week 9: Demo day","due_date":"2026-11-06"}` | **201**. Jane's `/milestones/mine` now has 9 tasks |

### Frontend checks

| # | Do | Expect |
|---|---|---|
| 1 | Open http://localhost:5173 | Split screen: a purple hero with a looping animation (a notice is acknowledged, then a report is signed off) beside a **Sign in / Join cohort** card |
| 2 | Narrow the window to phone width | The hero hides and the card fills the screen, with no sideways scrolling |
| 3 | **Join cohort**: name, a new email, a password of 8+ characters, cohort **Full-Stack Foundations** → **Create account** | You land on the trainee dashboard, already logged in |
| 4 | Look at the greeting | "Good morning/afternoon/evening, ‹name›" based on your PC's clock, and **"4 tasks are pending now · 2 overdue"** (you joined late) |
| 5 | **Monthly review** | This month's tasks by status. Use ‹ › to step through months |
| 6 | **Active task** | Week 1 with a red **Overdue** date tag, a "Pending" pill, and 5 peer avatars |
| 7 | **Submit report** → fill it in → submit | The dialog closes. The alert drops to 3 pending, the active task moves to Week 2, and the report appears in **My submissions** |
| 8 | **Switch user** (top right) → Morgan Reyes → `password123` | The manager dashboard counts your new trainee in **Active trainees** |
| 9 | Log out → **Sign in** → click the **Jane · trainee** shortcut → Sign in | "**2 tasks are pending now**", and the active task is Week 6 with a "**Due today**" tag |
| 10 | Switch to **Tom Okafor** | His active task is Week 4, shown as **In progress** with a "Submit an update" button (his last report was stalled) |

`python seed.py` resets everything, including removing accounts you signed up.

---

## What changed from v3

| | v3 | v3b |
|---|---|---|
| Getting an account | A manager onboards you (`POST /api/trainees`) | Also **`POST /api/auth/signup`** (public, always a trainee) |
| Cohorts | Managers couldn't create them | `POST /api/cohorts` (manager), with an **`open_for_signup`** flag |
| Sign-up dropdown | | **`GET /api/cohorts/public-list`** (public): open cohorts only |
| Tasks | Free-text `milestone_name` on reports | **`milestones` table** with `due_date`. Reports link to one with `milestone_id` |
| New trainee routes | | `GET /api/milestones/mine` (each task with its status), `GET /api/cohorts/mine` (cohort and peers) |
| New manager routes | | `POST /api/milestones`, `GET /api/milestones` |
| `GET /api/users/switch-options` | Public | **Needs a login.** The landing page now has a real sign-in form, so the account list no longer has to be public |
| Seeded managers | Alex Smith | + **Morgan Reyes, `manager@edtech.com`** |
| Logged-out page | Account picker | Split hero with tabbed Sign in / Join cohort |
| Trainee page | Notices, form, timeline | Greeting, monthly review grid, active task card, notices and timeline. The form moved into a dialog |

The v3 routes still behave the same: v3's 59 tests pass alongside 28 new ones.

---

## Implementation walkthrough

What each part does, how it works, and why. Links go to the exact lines. For login, tokens and role guards, see the [v3 walkthrough](../v3_auth/README.md#implementation-walkthrough).

## Backend

### 1. Milestones and due dates: [models.py](backend/app/models.py), migration [0003](backend/alembic/versions/0003_milestones_and_signup.py)

**What.** A `Milestone` is a task assigned to a whole cohort with a `due_date` ([models.py:80-90](backend/app/models.py#L80-L90)). A report can point at one through `submissions.milestone_id` ([101](backend/app/models.py#L101)).

**How.**
- **Where the due date lives.** The brief asked for due dates "on tasks/submissions". The deadline belongs to the **task**, and a report inherits it through its milestone, so one cohort-wide date isn't copied onto every report.
- **Migration 0003** creates the table with its own ID sequence (`m1`, `m2`, …) ([0003:29-38](backend/alembic/versions/0003_milestones_and_signup.py#L29-L38)). It also adds the foreign key from submissions ([42-45](backend/alembic/versions/0003_milestones_and_signup.py#L42-L45)).
- **Backfilling the new flag.** `cohorts.open_for_signup` is added with `server_default=true` ([24-27](backend/alembic/versions/0003_milestones_and_signup.py#L24-L27)), so the migration also works on a database that already has cohorts. Autogenerate wrote it without a default, which would fail there.
- **Older reports.** `milestone_id` is nullable, so free-form reports and reports written before v3b stay valid.

### 2. Task status: [milestone_repo.py](backend/app/repositories/milestone_repo.py)

**What.** Each trainee sees each task as `pending`, `in_progress`, `under_review` or `completed`. These are the four stat cards in the brief.

**How.** `list_for_trainee()` ([milestone_repo.py:29-58](backend/app/repositories/milestone_repo.py#L29-L58)) works in four steps:
1. Ranks **this trainee's** reports per milestone, newest first ([35-46](backend/app/repositories/milestone_repo.py#L35-L46)).
2. Keeps only the latest report for each task ([47](backend/app/repositories/milestone_repo.py#L47)).
3. LEFT JOINs that onto the cohort's milestones ([51](backend/app/repositories/milestone_repo.py#L51)).
4. Maps the latest report's status through `TASK_STATUS` ([11-15](backend/app/repositories/milestone_repo.py#L11-L15)):

| Latest report | Task status | Card |
|---|---|---|
| none | `pending` | Pending |
| `stalled` (blocked, or sent back by a manager) | `in_progress` | In progress / Continue |
| `needs_review` | `under_review` | Under review |
| `on_track` (signed off) | `completed` | Completed |

**Why.** The status is **worked out, not stored**, so it can't drift out of sync with the reports. A manager's sign-off or a newer report updates it automatically. [test_milestones.py:49](backend/tests/test_milestones.py#L49) walks through every transition.

### 3. Sign-up that can't create managers: [routers/auth.py:31-55](backend/app/routers/auth.py#L31-L55)

**What.** `POST /api/auth/signup` creates a trainee and returns a token, so the new user is logged in straight away.

**How.**
- **No role field.** `SignupRequest` ([schemas.py:48](backend/app/schemas.py#L48)) simply has no `role`, and like every input model it rejects unknown fields. Sending `"role": "manager"` gets a 422 ([test_signup.py:40](backend/tests/test_signup.py#L40)). The route always writes `role="trainee"` ([auth.py:50](backend/app/routers/auth.py#L50)).
- **Cohort checks.** An unknown cohort and a closed cohort get the **same** 400 ([41](backend/app/routers/auth.py#L41)), so the response doesn't reveal private cohorts.
- **Duplicates.** A duplicate email returns 409 ([43](backend/app/routers/auth.py#L43)).
- **Manager accounts** come only from [seed.py:39](backend/seed.py#L39), as the brief allowed. That includes `manager@edtech.com`.

**Why `open_for_signup` exists.** Picking any cohort at sign-up means anyone on the internet could join a cohort and read its notices. Managers decide which cohorts appear in the public list ([cohort_repo.py:25](backend/app/repositories/cohort_repo.py#L25), [routers/cohorts.py:22-25](backend/app/routers/cohorts.py#L22-L25)). Solo tracks are seeded closed ([seed.py:30](backend/seed.py#L30)), because a manager assigns them one-to-one.

### 4. Other new routes

| Route | Where | Notes |
|---|---|---|
| `GET /api/cohorts/public-list` | [cohorts.py:22](backend/app/routers/cohorts.py#L22) | Public. Returns `PublicCohort` ([schemas.py:101](backend/app/schemas.py#L101)): id, name, track type and start date, without the internal flag |
| `GET /api/cohorts/mine` | [cohorts.py:28](backend/app/routers/cohorts.py#L28) | Trainee. Returns their cohort and peers (`user_repo.list_peers`, [user_repo.py:27](backend/app/repositories/user_repo.py#L27)), or `{cohort: null, peers: []}` before they're assigned |
| `POST /api/cohorts` | [cohorts.py:39](backend/app/routers/cohorts.py#L39) | Manager: the brief's "cohort administration" |
| `POST /api/milestones`, `GET /api/milestones` | [milestones.py:12-30](backend/app/routers/milestones.py#L12-L30) | Manager |
| `GET /api/milestones/mine` | [milestones.py:33](backend/app/routers/milestones.py#L33) | Trainee: their tasks with status and last report time (`MyMilestone`, [schemas.py:180](backend/app/schemas.py#L180)) |
| `POST /api/submissions` + `milestone_id` | [submissions.py:21-33](backend/app/routers/submissions.py#L21-L33) | The task must belong to the trainee's cohort ([26](backend/app/routers/submissions.py#L26)), and its title becomes the default report name ([33](backend/app/routers/submissions.py#L33)). The schema needs a task or a title ([schemas.py:219](backend/app/schemas.py#L219)) |
| `GET /api/users/switch-options` | [auth.py:72](backend/app/routers/auth.py#L72) | **Now needs a login.** The navbar switcher still works; the list just isn't public anymore |

### 5. Seed: [seed.py](backend/seed.py)

- **Cohorts and tasks.** Each cohort now has a full weekly curriculum ([27-35](backend/seed.py#L27-L35)). Week N is due `start + N weeks` ([96-104](backend/seed.py#L96-L104)), so some tasks are past and some upcoming. Every seeded report links to its milestone ([133](backend/seed.py#L133)).
- **Example states.** Because dates are relative to today, Jane always has Week 6 due *today* and Week 7 due in a week, which gives the brief's "2 tasks are pending now". Tom's latest report is stalled, so his active task shows as "In progress". Ethan has never submitted, so he has overdue tasks.
- **Managers.** Morgan Reyes (`manager@edtech.com`) is added **last** ([122](backend/seed.py#L122)), so the existing IDs (u1 Jane, u2 Alex, …) stay the same as v1–v3.

### 6. Tests: 87 passing

- [test_signup.py](backend/tests/test_signup.py) checks sign-up, the role guard, closed cohorts, validation, and that a trainee with no cohort sees only global notices.
- [test_milestones.py](backend/tests/test_milestones.py) checks status derivation, that other trainees' reports don't count, the cohort check on `milestone_id`, and peers.
- [test_dashboard.py:65](backend/tests/test_dashboard.py#L65) pins Jane's seeded task list, and [76](backend/tests/test_dashboard.py#L76) logs in as `manager@edtech.com`.
- [test_auth.py:78](backend/tests/test_auth.py#L78) checks the switch-user list now returns 401 without a login.

## Frontend

### 7. Split hero sign-in / sign-up: [views/AuthPage.jsx](frontend/src/views/AuthPage.jsx)

**What.** On wide screens the page is two columns: `HeroPane` on the left ([39-85](frontend/src/views/AuthPage.jsx#L39-L85)) and `AuthCard` on the right ([87-119](frontend/src/views/AuthPage.jsx#L87-L119)). Below the `lg` breakpoint the hero hides (`hidden … lg:flex`, [46](frontend/src/views/AuthPage.jsx#L46)) and a small brand line shows above the card instead.

**How.**
- **Tabs.** The card has real ARIA tabs ([96](frontend/src/views/AuthPage.jsx#L96)), so screen readers announce "Sign in" and "Join cohort" as tabs.
- **Sign in** ([151](frontend/src/views/AuthPage.jsx#L151)) takes an email or user ID and a password.
- **Join cohort** ([211](frontend/src/views/AuthPage.jsx#L211)) fills its dropdown from `/cohorts/public-list`, with "I'll be assigned one later" sent as `null` ([219](frontend/src/views/AuthPage.jsx#L219)). It calls the new `signup()` in AuthContext ([AuthContext.jsx:46](frontend/src/auth/AuthContext.jsx#L46)). Login and sign-up share `startSession()` ([26](frontend/src/auth/AuthContext.jsx#L26)), so a new account gets the same token storage and cache reset as a login.
- **Demo shortcuts.** The "Manager / Jane / Ethan" buttons ([187-206](frontend/src/views/AuthPage.jsx#L187-L206)) are wrapped in `import.meta.env.DEV`. They show under `npm run dev` and are **removed from production builds**; I checked that the built bundle doesn't contain the demo emails or password. Together with the navbar switcher (kept from v3), this covers "easy evaluation without typing full credentials".

### 8. The looping hero animation: [HeroLoop.jsx](frontend/src/components/HeroLoop.jsx), [index.css](frontend/src/index.css)

**What.** A 9-second loop of the product's core flow:
1. an urgent notice slides in;
2. a cursor clicks **Acknowledge** and the button turns green;
3. a progress report appears, its bar fills, and its pill flips from "Needs review" to "On track ✓".

Friendly floating chips ("Due Friday", a cohort avatar stack, a sparkle) bob around it.

**How.**
- **Drawn, not recorded.** The scene is plain HTML and Tailwind. All its parts share one 9 s CSS clock, and the timeline is mapped out in the comment at [index.css:4-12](frontend/src/index.css#L4-L12).
- **Crossfades.** Two-state elements, such as the red and green button, are stacked layers that crossfade ([HeroLoop.jsx:48-54](frontend/src/components/HeroLoop.jsx#L48-L54)).
- **Reduced motion.** The base styles are the *finished* frame. `prefers-reduced-motion` switches the animation off ([index.css:81](frontend/src/index.css#L81)), so people who ask their OS for less motion see a still, complete picture.
- **Optional video.** To use a real video, put an MP4/WebM in `frontend/public/media/` and set `HERO_VIDEO_SRC` ([AuthPage.jsx:12](frontend/src/views/AuthPage.jsx#L12)). The hero then plays it (`autoPlay loop muted playsInline`) instead.

**Why not a Lottie or video file?** No video or Lottie asset was provided, and none can be generated here without design tools. The drawn version adds no download and no library, stays sharp at any size, and uses the app's real colours and icons.

### 9. Trainee dashboard: [views/TraineeView.jsx](frontend/src/views/TraineeView.jsx)

**What.** The greeting header, monthly review and active task card all read **one** query, `useMyMilestones()` ([TraineeView.jsx:11](frontend/src/views/TraineeView.jsx#L11)). Their numbers always agree, and they refresh together every 15 s ([queries.js:36-43](frontend/src/queries.js#L36-L43)). Submitting a report also refreshes it immediately ([queries.js:92](frontend/src/queries.js#L92)).

**How.** The rules are pure functions in [lib/tasks.js](frontend/src/lib/tasks.js), separate from the components:

| Brief item | Rule | Component |
|---|---|---|
| Greeting | "Good morning" before 12:00, "afternoon" until 17:00, then "evening", using the **viewer's** clock ([format.js:61](frontend/src/lib/format.js#L61)) | [GreetingHeader.jsx:20](frontend/src/components/GreetingHeader.jsx#L20) |
| "N tasks are pending now" | Not submitted and due within 7 days, or already overdue ([tasks.js:20](frontend/src/lib/tasks.js#L20)). Overdue ones are counted separately | [GreetingHeader.jsx:29-46](frontend/src/components/GreetingHeader.jsx#L29-L46) |
| Monthly review grid | Tasks **due in the selected month**, counted by status ([tasks.js:8](frontend/src/lib/tasks.js#L8)). The ‹ › buttons step through months ([MonthlyReview.jsx:11](frontend/src/components/MonthlyReview.jsx#L11)) | [MonthlyReview.jsx](frontend/src/components/MonthlyReview.jsx) |
| Active task | The soonest task that's **pending or in progress**, meaning it needs the trainee's action ([tasks.js:25](frontend/src/lib/tasks.js#L25)) | [ActiveTaskCard.jsx](frontend/src/components/ActiveTaskCard.jsx) |
| Due date tag | Red "Overdue", amber "Due today", otherwise neutral. The date is shown in your locale's 2-digit order, e.g. 05/10/2026 ([format.js:56](frontend/src/lib/format.js#L56)) | [ActiveTaskCard.jsx:49](frontend/src/components/ActiveTaskCard.jsx#L49) |
| Cohort peers | Up to 5 overlapping avatars plus "+N", from `/cohorts/mine`. Solo trainees see "just you" | [ActiveTaskCard.jsx:64](frontend/src/components/ActiveTaskCard.jsx#L64) |
| Submission trigger | **Submit report** opens [SubmitReportModal.jsx](frontend/src/components/SubmitReportModal.jsx) with that task preselected ([TraineeView.jsx:22](frontend/src/views/TraineeView.jsx#L22)) | |

**Details worth knowing.**
- **Parsing due dates.** `due_date` comes as `"2026-10-05"`. `new Date("2026-10-05")` means midnight **UTC**, which shows as **4 October** anywhere west of UTC, including the whole of the Americas. `parseDay()` ([format.js:39](frontend/src/lib/format.js#L39)) reads it as a local date instead.
- **Colours.** All four statuses share one colour and icon map ([ui.jsx:30-43](frontend/src/components/ui.jsx#L30-L43)), so a card and a pill of the same status always match. The class names are written out in full because Tailwind only generates classes it can find literally in the source.
- **Shared dialog shell.** [Modal.jsx](frontend/src/components/Modal.jsx) handles Esc, backdrop clicks and dialog labelling. It's used by both the password prompt and the report form.

---

## Choices to review

| Choice | Why | Change it by |
|---|---|---|
| "In progress" means the latest report is **stalled** | The four cards need a status between "not started" and "submitted". A stalled or sent-back task is the one you need to *continue* | Edit `TASK_STATUS` ([milestone_repo.py:11](backend/app/repositories/milestone_repo.py#L11)) |
| "Pending now" means due within **7 days** or overdue | Matches the weekly cadence and the brief's "2 tasks are pending now" for Jane | `pendingNow()` ([tasks.js:20](frontend/src/lib/tasks.js#L20)) |
| The monthly grid buckets tasks by **due month** | Gives "this month's review" a clear meaning; the arrows reach other months | `monthCounts()` ([tasks.js:8](frontend/src/lib/tasks.js#L8)) |
| Late joiners inherit past tasks as **overdue** | Honest: those tasks were due. A manager can decide what to excuse | Filter by join date if you add a `joined_at` column |
| The dashboard's `overdue_submissions` still uses v2's 7-day rule | Kept the manager numbers stable | A follow-up could count past-due milestones with no report instead |
| The sign-up error for a taken email says it's taken (409) | Standard UX, but it lets someone check whether an email has an account | Return a generic success and send an email instead (needs email sending) |
