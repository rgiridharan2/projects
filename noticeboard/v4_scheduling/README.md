# NoticeBoardTracker — v4 (Scheduling & Oversight)

Phase 4 builds on [v3b](../v3b_onboarding/README.md) and adds:

1. **Task scheduling.**
   - Each task's `due_date` is now an exact **ISO timestamp**, and each task has a `milestone_order` (its position in the cohort's sequence).
   - Managers get a **task dispatcher** that sends one task to several cohorts, each with its own deadline.
   - Tasks show **colour-coded due badges**: green = due later, amber = due today, red = overdue.
2. **Agenda.** A month header with a clickable **day carousel**, and an **hourly timeline** of the cohort's scheduled sessions for the chosen day.
3. **Manager oversight.**
   - A **cohort matrix** (trainees × tasks) that works out who is overdue from the current time and each task's deadline.
   - **Nudges**: managers can send a reminder about any overdue task, one at a time or all at once.

`v3b_onboarding/` is unchanged. v4 has its own database container on port **5436**. Every seeded account's password is **`password123`**. Managers are `manager@edtech.com` (Morgan) and `alex.smith@example.com` (Alex).

---

## Run plan

### One-time setup

`.venv` and `node_modules` already exist on your machine.

```powershell
# v4_scheduling/backend
docker compose up -d                 # Postgres for v4 on localhost:5436
.venv\Scripts\activate
alembic upgrade head                 # ... 0004 timed deadlines, milestone order, schedule, reminders
python seed.py                       # also creates 200 timetable sessions and one unread nudge
```

**Re-run `python seed.py` on the day you demo.** Deadlines and sessions are placed relative to *today*, in **your computer's timezone**.

### Every time: two terminals

| Terminal | Folder | Command | URL |
|---|---|---|---|
| 1 | `v4_scheduling/backend` (venv active) | `uvicorn app.main:app --reload` | http://localhost:8000/docs |
| 2 | `v4_scheduling/frontend` | `npm run dev` | **http://localhost:5173** |

Stop any other version's servers first, because they share these ports. To run v4 next to them, use `--port 8001` for uvicorn and `$env:API_URL="http://127.0.0.1:8001"; npm run dev -- --port 5174`.

### Backend checks

| # | Do | Expect |
|---|---|---|
| 1 | `alembic current`, then `alembic check` | `0004 (head)`, then `No new upgrade operations detected.` |
| 2 | `pytest` | `122 passed` |
| 3 | **Authorize** as `manager@edtech.com`, then `GET /api/dashboard/stats` | `overdue_submissions: 9`: past-deadline tasks with nothing submitted (Tom 1, Sofia 2, Liam 3, Grace 1, Ethan 2) |
| 4 | `GET /api/cohorts/c1/matrix` | 6 trainees × 8 tasks, `overdue_total: 6`. Liam's Week 3 cell has a `nudged_at` from the seed |
| 5 | `POST /api/reminders` with `{"trainee_id":"u5","milestone_id":"m5"}` (Tom, Week 5) | **201**. Send it again: **409** (already nudged) |
| 6 | `POST /api/reminders` with `{"trainee_id":"u1","milestone_id":"m8"}` (Jane, not due yet) | **400** `Only overdue tasks can be nudged…` |
| 7 | `POST /api/cohorts/c1/nudges` | `{"created": 4, "already_nudged": 2}` |
| 8 | `POST /api/milestones/dispatch` with `{"title":"Demo day","assignments":[{"cohort_id":"c1","due_date":"2026-11-06T17:00:00-05:00"},{"cohort_id":"c3","due_date":"2026-11-13T17:00:00Z"}]}` | **201**: two tasks, `milestone_order` 9 (c1) and 7 (c3) |
| 9 | The same request with `"due_date":"2026-11-06T17:00:00"` (no timezone) | **422**: deadlines must say which timezone they're in |
| 10 | **Authorize** as `jane.doe@example.com`, then `GET /api/schedule/mine?start=<today 00:00Z>&end=<tomorrow 00:00Z>` | That day's sessions for Jane's cohort |

### Frontend checks

| # | Do | Expect |
|---|---|---|
| 1 | Sign in as **Jane** | "**2 tasks are pending now**". The active task (Week 6) has an **amber "Due today · 11:59 PM"** badge |
| 2 | **Agenda** tab | Header `‹ Sep  October 2026  Nov ›`, a scrollable strip of day tabs with today selected, and a timeline from 08:00 to 18:00 |
| 3 | Look at today's timeline | Today's sessions as coloured blocks with times and module names. Finished sessions are faded, the current one has a **Now** ring, and a red line marks the current time. Today's deadline sits above the grid |
| 4 | Click other days and the ‹ › months | Weekdays have sessions and weekends say "Nothing scheduled". A red dot on a day tab marks a deadline |
| 5 | **Your tasks** list (right side of the agenda) | `#1`–`#8` in order, each with a badge: grey **Submitted**, amber **Due today**, green **Due 10/12/2026**. Clicking one jumps to its due day |
| 6 | **Switch user → Morgan Reyes** | Tiles show **Overdue tasks 9**. **Cohort matrix**: Cloud Native Q4 shows "6 overdue". Red **Nudge** buttons sit in Liam's, Sofia's and Tom's late cells, and Liam's Week 3 already says **Nudged** |
| 7 | Click one **Nudge**, then **Nudge all overdue** | The cell flips to "Nudged", then "Sent 4 reminders." and the button greys out |
| 8 | **Dispatch tasks** → title → tick two cohorts → adjust each date and time → **Dispatch** | "Sent … to 2 cohorts". The preview shows "becomes task #9", and the matrix gains a #9 column |
| 9 | **Switch user → Liam Murphy** | **Red reminder banners** (Morgan's and Alex's), "**· 3 overdue**", and the active task Week 3 with a **red Overdue** badge |
| 10 | **Submit now** on a banner → submit | That banner disappears (submitting clears the reminder), and the active task moves on |

`python seed.py` resets everything.

---

## What changed from v3b

| | v3b | v4 |
|---|---|---|
| `milestones.due_date` | `DATE` (`"2026-10-05"`) | **`TIMESTAMPTZ`** (`"2026-10-06T04:59:00Z"`, which is 23:59 on 5 Oct in Chicago) |
| Task order | Sorted by due date | **`milestone_order`**: 1, 2, 3… per cohort, unique within a cohort |
| Creating tasks | One cohort per request | Also **`POST /api/milestones/dispatch`**: one task to many cohorts, all-or-nothing |
| "Overdue" | Dashboard: no report for 7 days | **One rule everywhere**: deadline passed and nothing submitted |
| Agenda | | **`schedule_blocks`** table, `GET /api/schedule/mine`, `POST /api/schedule` |
| Nudges | | **`reminders`** table, `POST /api/reminders`, `POST /api/cohorts/{id}/nudges`, `GET /api/reminders/mine`, dismiss |
| Manager UI | 4 stat tiles | Tiles + **Cohort matrix** + **Dispatch tasks** |
| Trainee UI | One page | Reminder banners, **Overview / Agenda** tabs, and due badges on task cards |

---

## Implementation walkthrough

What each part does, how it works, and why. Links go to the exact lines.

## Backend

### 1. Timed deadlines and task order: [models.py](backend/app/models.py), migration [0004](backend/alembic/versions/0004_scheduling_and_reminders.py)

**What.** `Milestone` ([models.py:80](backend/app/models.py#L80)) now has:
- `due_date` as a timezone-aware timestamp ([93](backend/app/models.py#L93));
- `milestone_order` ([91](backend/app/models.py#L91)), unique per cohort ([85](backend/app/models.py#L85)).

**How.**
- **Converting existing data.** Migration 0004 changes the column type with an explicit `USING` rule that turns each old date into 23:59 UTC that day ([0004:30](backend/alembic/versions/0004_scheduling_and_reminders.py#L30)).
- **Backfilling the order.** It numbers existing tasks per cohort with `row_number()` before making the column required ([38-42](backend/alembic/versions/0004_scheduling_and_reminders.py#L38-L42)). I tested this on real rows, and the downgrade turns the timestamps back into dates ([96](backend/alembic/versions/0004_scheduling_and_reminders.py#L96)).
- **Requiring a timezone.** Incoming deadlines use Pydantic's `AwareDatetime` ([schemas.py:185](backend/app/schemas.py#L185)), so a value without a timezone is rejected with 422.
- **Order on create.** If a manager leaves out `milestone_order`, the task goes after the cohort's highest number. A clash returns 409 ([routers/milestones.py:21](backend/app/routers/milestones.py#L21)).

**Why.**
- **Exact deadlines.** A date alone can't express "Friday 5 pm", and without a timezone "17:00" means different moments to different people. Storing an exact UTC moment and displaying it in each viewer's local time is the standard fix.
- **A separate order field.** `milestone_order` gives every task a stable "#3" label for the matrix columns and lists. It doesn't change when a deadline moves.

### 2. One definition of "overdue": [milestone_repo.py](backend/app/repositories/milestone_repo.py)

**What.** "Overdue" means **the deadline has passed and the trainee has submitted nothing for the task**. It's one SQL condition ([milestone_repo.py:51-55](backend/app/repositories/milestone_repo.py#L51-L55)), used everywhere:
- the trainee's task list (`overdue` on `/milestones/mine`, [schemas.py:218](backend/app/schemas.py#L218));
- the cohort matrix;
- nudge eligibility;
- the dashboard's `overdue_submissions` ([dashboard_repo.py:39-45](backend/app/repositories/dashboard_repo.py#L39-L45)).

**How.**
- **`task_states()`** ([58-77](backend/app/repositories/milestone_repo.py#L58-L77)) joins trainees to their cohort's milestones, then LEFT JOINs each pair's latest report (`latest_reports()`, [30](backend/app/repositories/milestone_repo.py#L30)). It returns a `TaskState` ([20](backend/app/repositories/milestone_repo.py#L20)) for every pair, including the overdue flag.
- **Who uses it.** The matrix, the nudge routes and `/mine` all call it. The dashboard uses the same condition inside its own aggregate query.

**Why.**
- **Numbers that agree.** Before v4 the dashboard had its own rule (no report in 7 days), so the manager tile and a trainee's red badge could disagree. Now they can't: [test_oversight.py](backend/tests/test_oversight.py) asserts the dashboard count equals the matrix total.
- **Stalled work isn't "overdue".** A stalled report counts as **at risk** instead, so the two numbers measure different problems.
- **The dashboard number changed.** `overdue_submissions` is now **9** on the seed data (v2's rule gave 4) and counts *tasks*, not trainees. The new definition is in the Swagger description ([schemas.py:350](backend/app/schemas.py#L350)).

### 3. Dispatcher: [routers/milestones.py:32](backend/app/routers/milestones.py#L32)

**What.** `POST /api/milestones/dispatch` takes `{title, assignments: [{cohort_id, due_date}, …]}` and creates one milestone per cohort.

**How.**
- It checks every cohort before creating anything, so one unknown cohort means nothing is created.
- Each copy is appended to its own cohort's sequence.
- The schema rejects an empty list and a cohort listed twice ([schemas.py:202-212](backend/app/schemas.py#L202-L212)).

**Why.** "Distributing milestones to cohorts" usually means the same task for several cohorts, with deadlines that differ because the cohorts started on different dates. One request keeps it atomic.

### 4. Agenda data: [routers/schedule.py](backend/app/routers/schedule.py), [schedule_repo.py](backend/app/repositories/schedule_repo.py)

**What.** A `ScheduleBlock` ([models.py:96](backend/app/models.py#L96)) is a timed session for a cohort (lecture, lab, office hours), optionally tied to a module (milestone).

**How.**
- **`GET /api/schedule/mine?start=&end=`** ([schedule.py:48](backend/app/routers/schedule.py#L48)) returns blocks that **overlap** the range, so a session running across midnight still shows ([schedule_repo.py:14](backend/app/repositories/schedule_repo.py#L14)).
- **Range limits.** A range can be at most 62 days ([schedule.py:14](backend/app/routers/schedule.py#L14)), and its ends must include a timezone.
- **Creating blocks.** `POST /api/schedule` (manager) checks that a linked milestone belongs to the same cohort.

**Why a separate table?** Milestones last a week, so on an hourly timeline every day would show the same full-day bar. The brief's "08:00–10:00 Landing page design" describes **scheduled time blocks**, which are their own kind of thing.

### 5. Matrix and nudges: [routers/oversight.py](backend/app/routers/oversight.py), [routers/reminders.py](backend/app/routers/reminders.py)

**The matrix.** `GET /api/cohorts/{id}/matrix` ([oversight.py:16](backend/app/routers/oversight.py#L16)) returns one row per trainee, sorted by name. Each row holds one cell per task in sequence order. A cell gives the status, `overdue`, the time of the last report, and `nudged_at` from the trainee's unread reminder, if any ([22](backend/app/routers/oversight.py#L22)). It also returns per-row and cohort-wide overdue totals (`CohortMatrix`, [schemas.py:293](backend/app/schemas.py#L293)).

**Nudging one task.** `POST /api/reminders` ([reminders.py:14](backend/app/routers/reminders.py#L14)) has three rules:
- only **overdue** tasks can be nudged (otherwise 400, [29](backend/app/routers/reminders.py#L29));
- only **once** while the trainee hasn't cleared it (409, [33](backend/app/routers/reminders.py#L33));
- the task must belong to that trainee's cohort (404).

**Nudging a whole cohort.** `POST /api/cohorts/{id}/nudges` ([oversight.py:47](backend/app/routers/oversight.py#L47)) creates a reminder for every overdue task that doesn't have an unread one, skipping those that do ([58](backend/app/routers/oversight.py#L58)). It reports both counts.

**The trainee's side.**
- `GET /api/reminders/mine` lists unread reminders with the task title, deadline and sender's name ([reminders.py:43](backend/app/routers/reminders.py#L43)).
- `POST /api/reminders/{id}/dismiss` hides one (only your own, and calling it twice is harmless).
- **Submitting the task clears its reminders automatically** ([submissions.py:42](backend/app/routers/submissions.py#L42)), so a trainee never sees "you're late" for work they've handed in.

**Why a `reminders` table rather than notices?** Notices go to whole cohorts, and the read-rate statistic counts them. A nudge is personal and should disappear once the task is done. Storing it separately keeps both features simple, and the matrix can show "nudged 2 days ago".

### 6. Seed: [seed.py](backend/seed.py)

- **Deadlines.** Each week's deadline is **23:59 local time** on its due day ([seed.py:132](backend/seed.py#L132)), built with `local_time()` ([110](backend/seed.py#L110)). That function uses the OS's timezone for each date, so daylight-saving changes are handled. "Today" is also the local date ([118](backend/seed.py#L118)).
- **Timetable.** A weekly timetable ([82-94](backend/seed.py#L82-L94)) gives each cohort weekday sessions for the module of that week ([147](backend/seed.py#L147)): 200 blocks in total.
- **One existing nudge.** Alex already nudged Liam about Week 3 two days ago ([213](backend/seed.py#L213)), so both the matrix and Liam's banner have something to show straight away.
- **Why 23:59?** A deadline at the end of the day keeps "due today" amber all day. With 17:00, Jane's demo state and the overdue count would change mid-afternoon.

### 7. Tests: 122 passing

- [test_scheduling.py](backend/tests/test_scheduling.py) covers task order (automatic, explicit and clashing), the timezone requirement, dispatch (several cohorts, all-or-nothing, validation), blocks (range overlap, a block running across the range start, validation) and the 62-day limit.
- [test_oversight.py](backend/tests/test_oversight.py) covers the overdue maths per cell, stalled tasks counting as at risk rather than overdue, the dashboard matching the matrix, every nudge rule, nudge-all counts, dismissing, and submission clearing a reminder.
- **Tests no longer depend on the date.** Deadlines in tests are relative to "now" (`due_in(-3)`), so the suite passes whenever it runs. Earlier tests used fixed dates in October 2026, which would have started failing after that.

## Frontend

### 8. Due badges: [ui.jsx:57-77](frontend/src/components/ui.jsx#L57-L77), [lib/tasks.js:38](frontend/src/lib/tasks.js#L38)

`dueState()` picks a badge for each task:

| State | Rule | Badge |
|---|---|---|
| `overdue` | The server's `overdue` flag (same rule as the matrix) | **Red** "Overdue · 09/14/2026" |
| `today` | Due on today's **local** calendar date, deadline not yet passed | **Amber** "Due today · 11:59 PM" |
| `later` | Due on a later date | **Green** "Due 10/12/2026" |
| `submitted` | Under review or completed | Grey "Submitted" |
| `past` | Deadline passed but work is in progress (stalled), so not "overdue" | Grey "Was due …" |

`DueBadge` appears on the active task card, the agenda's task list and the deadline rows on the timeline.

A related fix: "N tasks are pending now" counts in **calendar days**, through the end of the 7th day ([tasks.js:23-25](frontend/src/lib/tasks.js#L23-L25)). With exact timestamps, "within 7 days" had started to exclude next Monday's 23:59 deadline on a Monday afternoon.

### 9. Agenda: [views/AgendaView.jsx](frontend/src/views/AgendaView.jsx)

**What.** The **Agenda** tab ([TraineeView.jsx:28](frontend/src/views/TraineeView.jsx#L28)) has three parts:
- **Day selector header.** `‹ Sep  October 2026  Nov ›` ([AgendaView.jsx:47-53](frontend/src/views/AgendaView.jsx#L47-L53)) above `DayStrip` ([75](frontend/src/views/AgendaView.jsx#L75)), a horizontal row of date tabs ("MON 5 Oct"). A dot marks days with sessions and a red dot marks deadlines ([116](frontend/src/views/AgendaView.jsx#L116)). The selected tab scrolls itself into view inside the strip ([86](frontend/src/views/AgendaView.jsx#L86)).
- **Hourly timeline.** `DayTimeline` ([126](frontend/src/views/AgendaView.jsx#L126)) shows the day's deadlines on top, then blocks placed by start and end time.
- **Your tasks.** `TaskList` ([209](frontend/src/views/AgendaView.jsx#L209)) shows every task with its `#order`, due badge and status. Clicking one jumps to its due day, and "Submit report →" opens the dialog.

**How the timeline is laid out.** The layout maths is in [lib/timeline.js](frontend/src/lib/timeline.js):
- **Visible hours.** `visibleHours()` ([timeline.js:9](frontend/src/lib/timeline.js#L9)) shows 08:00–18:00, stretched to fit any earlier or later block.
- **Overlaps.** `assignLanes()` ([24](frontend/src/lib/timeline.js#L24)) places overlapping sessions side by side in lanes rather than on top of each other.
- **Live state.** Blocks that have finished are faded, the current one gets a **Now** ring ([AgendaView.jsx:169](frontend/src/views/AgendaView.jsx#L169)), and a red line marks the current time on today's view ([132](frontend/src/views/AgendaView.jsx#L132)).
- **Colours.** Each module has its own colour, so a week's sessions look related.
- **Loading.** The agenda fetches one month of blocks at a time (`useMySchedule`, [AgendaView.jsx:28](frontend/src/views/AgendaView.jsx#L28)).

**A layout bug found during testing.** The 31-day strip made the whole page scroll sideways. CSS grid items won't shrink below their content's width unless told to, so the column gets `min-w-0` ([AgendaView.jsx:41-43](frontend/src/views/AgendaView.jsx#L41-L43)). Now only the strip scrolls.

### 10. Reminders for trainees: [ReminderBanner.jsx](frontend/src/components/ReminderBanner.jsx)

Unread nudges appear as red banners above the tabs ([TraineeView.jsx:27](frontend/src/views/TraineeView.jsx#L27)), saying who sent each one and when:
- **Submit now** opens the report dialog with that task selected ([ReminderBanner.jsx:29](frontend/src/components/ReminderBanner.jsx#L29)).
- **✕** dismisses it ([35](frontend/src/components/ReminderBanner.jsx#L35)).
- Submitting a report refreshes the reminder list, because the server clears that task's reminders ([queries.js:98](frontend/src/queries.js#L98)).

### 11. Manager tools: [ManagerView.jsx](frontend/src/views/ManagerView.jsx)

The page shows the four stat tiles, then two tabs ([ManagerView.jsx:49-50](frontend/src/views/ManagerView.jsx#L49-L50)).

**Cohort matrix** ([CohortMatrix.jsx](frontend/src/components/CohortMatrix.jsx)):
- **Layout.** A cohort picker sits above a table of trainees and tasks. The trainee column stays pinned while you scroll sideways (`sticky left-0`, [94](frontend/src/components/CohortMatrix.jsx#L94), [112](frontend/src/components/CohortMatrix.jsx#L112)).
- **Column headers** show `#order`, the deadline and how many trainees are late ([98-103](frontend/src/components/CohortMatrix.jsx#L98-L103)).
- **Cells** ([144](frontend/src/components/CohortMatrix.jsx#L144)) use the same colours and icons as the trainee's stat cards. Overdue cells are red **Nudge** buttons, or show "Nudged" with a hover tooltip saying how long ago.
- **Nudge all overdue** shows how many tasks it would remind about ([26](frontend/src/components/CohortMatrix.jsx#L26)) and disables itself at zero.
- **Refreshing.** Every nudge refreshes the matrix *and* the dashboard tiles (`useRefreshOversight`, [queries.js:164](frontend/src/queries.js#L164)).

**Dispatch tasks** ([TaskDispatcher.jsx](frontend/src/components/TaskDispatcher.jsx)):
- **The form.** A title, then one row per cohort with a checkbox and its own `datetime-local` deadline. Each deadline defaults to 23:59 a week from today.
- **Order preview.** Each row says "becomes task #N" ([33](frontend/src/components/TaskDispatcher.jsx#L33)), so the manager can see where the task lands in each sequence.
- **Timezones.** The browser reads `datetime-local` as local time, and `.toISOString()` sends it as UTC ([43](frontend/src/components/TaskDispatcher.jsx#L43)). The deadline is the moment the manager meant, wherever trainees are.

---

## Choices to review

| Choice | Why | Change it by |
|---|---|---|
| **Overdue = deadline passed and nothing submitted.** Stalled work counts as at risk instead | Keeps "overdue" and "at risk" as different problems, and makes nudges about missing work | Add `latest.c.status == "stalled"` to `overdue_condition` ([milestone_repo.py:51](backend/app/repositories/milestone_repo.py#L51)) |
| `overdue_submissions` counts **tasks** (9), not trainees | That's what "overdue submissions" literally means, and it matches the matrix total | Count distinct trainees in [dashboard_repo.py:39-45](backend/app/repositories/dashboard_repo.py#L39-L45) |
| Seeded deadlines are **23:59 local** on the due day | "Due today" stays amber all day, and demo numbers don't change mid-afternoon | Change `"23:59"` at [seed.py:132](backend/seed.py#L132) |
| One unread reminder per task; submitting clears it | Stops managers spamming a trainee, and stops trainees seeing reminders for work they've handed in | Allow repeats in [reminders.py:33](backend/app/routers/reminders.py#L33) |
| Reminders are **in-app only** | No email service in this project | Send an email in the nudge routes once one exists |
| Sessions are created via the API or seed; there's **no timetable editor UI** | The brief asked for the trainee view of the timeline; managers dispatch *tasks* | A manager timetable editor could be Phase 5 |
