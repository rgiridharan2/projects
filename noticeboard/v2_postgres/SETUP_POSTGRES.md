# PostgreSQL setup guide (first time)

This guide gets a Postgres database running for v2, shows you how to look inside it, and covers the errors you're most likely to hit.
You already have Docker Desktop, so **Option A** is the quickest route.

---

## The basics in two minutes

| Term | Meaning here |
|------|--------------|
| **Server** | A program that runs in the background and waits for connections on a **port**. The Postgres default is 5432; v2 uses **5433**. |
| **Database** | One server can hold many databases. v2 uses `noticeboard` for the app and `noticeboard_test` for the tests. |
| **Role / user** | The login the app connects as. Here: user `noticeboard`, password `noticeboard`. |
| **Table** | Rows and columns, like a spreadsheet tab with strict types. **You never create tables by hand**: Alembic migrations do it. |
| **psql** | Postgres's command-line client, for typing SQL directly. |

The app finds the database through a **connection URL** ([app/config.py:13](app/config.py#L13)):

```
postgresql+psycopg://noticeboard:noticeboard@localhost:5433/noticeboard
└─ dialect + driver ┘ └─ user ─┘ └─ pass ─┘ └─ host ─┘└port┘└─ database ┘
```

The order of operations is always:

**start the server → `alembic upgrade head` (creates tables) → `python seed.py` (fills them) → run the API**

---

## Option A: Docker (recommended)

Docker runs Postgres in an isolated container, so nothing gets installed on Windows itself.

1. **Start Docker Desktop** from the Start menu and wait until it shows *Engine running*. Check from a terminal:
   ```powershell
   docker version          # should print both "Client" and "Server" sections
   ```

2. **Start the database** from the `v2_postgres` folder:
   ```powershell
   docker compose up -d
   ```
   The first run downloads the `postgres:16-alpine` image (about 100 MB).

3. **Check it's healthy:**
   ```powershell
   docker compose ps       # STATUS should say "Up ... (healthy)"
   ```

4. **Open a SQL prompt inside the container:**
   ```powershell
   docker exec -it noticeboard-v2-db psql -U noticeboard
   ```
   You'll see `noticeboard=#`. Type `\q` to leave.

### What `docker-compose.yml` sets up

| Setting | What it does |
|---------|--------------|
| `image: postgres:16-alpine` | Official Postgres 16, small Linux base |
| `POSTGRES_USER / PASSWORD / DB` | On the **first** start only, creates the `noticeboard` user and database |
| `ports: "5433:5432"` | Your PC's port 5433 maps to Postgres's 5432 inside the container. 5433 avoids clashing with any other Postgres on 5432 |
| `volumes: pgdata` | Data lives in a Docker volume, so it survives container restarts and reboots |
| `healthcheck` | Docker runs `pg_isready` every 5 s; that's where "(healthy)" comes from |

### Everyday commands (run in `v2_postgres`)

| Task | Command |
|------|---------|
| Start | `docker compose up -d` |
| Stop (data kept) | `docker compose stop` |
| View logs | `docker compose logs -f db` |
| SQL prompt | `docker exec -it noticeboard-v2-db psql -U noticeboard` |
| **Delete everything** and start fresh | `docker compose down -v`, then `up -d` and `alembic upgrade head` again |

> **Your old MVP container.** `noticeboard-db` (from the project now in `ignore/`) is a separate container on port 5432, and v2 doesn't use it.
> You can stop it to free memory with `docker stop noticeboard-db`. Its data is kept, and `docker start noticeboard-db` brings it back.

---

## Option B: Install Postgres directly on Windows

Use this option if you can't or don't want to use Docker.

1. Install Postgres 16:
   ```powershell
   winget install PostgreSQL.PostgreSQL.16
   ```
   Alternatively, use the EDB installer from <https://www.postgresql.org/download/windows/>. The installer asks for a password for the `postgres` superuser (write it down) and a port (keep **5432**).
   It also installs **pgAdmin** (a GUI) and **SQL Shell (psql)**.

2. Open **SQL Shell (psql)** from the Start menu. Press Enter to accept the defaults, then type the superuser password. Now create the app's user and database:
   ```sql
   CREATE ROLE noticeboard WITH LOGIN PASSWORD 'noticeboard' CREATEDB;
   CREATE DATABASE noticeboard OWNER noticeboard;
   ```
   `CREATEDB` lets the test suite create `noticeboard_test` by itself.

3. Point v2 at port 5432. Copy `.env.example` to `.env` and change `5433` to `5432` in both lines:
   ```
   DATABASE_URL=postgresql+psycopg://noticeboard:noticeboard@localhost:5432/noticeboard
   TEST_DATABASE_URL=postgresql+psycopg://noticeboard:noticeboard@localhost:5432/noticeboard_test
   ```

4. Use the same psql commands below, connecting with `psql -U noticeboard -d noticeboard`.

---

## Looking inside the database (psql cheat sheet)

Backslash commands are psql shortcuts. SQL statements must end with `;`.

| Command | Shows |
|---------|-------|
| `\l` | All databases |
| `\c noticeboard_test` | Switch to another database |
| `\dt` | Tables |
| `\d users` | A table's columns, indexes, and **foreign keys** |
| `\ds` | Sequences (where IDs like `u14` get their numbers) |
| `\x` | Toggle vertical output for wide rows |
| `\q` | Quit |

Try these after running `alembic upgrade head` and `python seed.py`:

```sql
SELECT * FROM alembic_version;                       -- which migration the DB is at (0001)
SELECT id, name, role, cohort_id FROM users ORDER BY length(id), id;
SELECT c.name, count(u.id) FROM cohorts c LEFT JOIN users u ON u.cohort_id = c.id AND u.role = 'trainee' GROUP BY c.name;

-- See a foreign key reject bad data (cohort c99 doesn't exist):
INSERT INTO users (id, name, email, role, cohort_id) VALUES ('x1', 'Test', 't@x.com', 'trainee', 'c99');
-- ERROR:  insert or update on table "users" violates foreign key constraint "fk_users_cohort_id_cohorts"
```

### Prefer a GUI?

pgAdmin, DBeaver, and the VS Code "PostgreSQL" extension all work. Connect with host `localhost`, port `5433` (or `5432` for Option B), database `noticeboard`, user and password `noticeboard`.

---

## Troubleshooting

| You see | Why | Fix |
|---------|-----|-----|
| `error during connect` / `cannot find the file specified` from `docker` | Docker Desktop isn't running | Start it and wait for *Engine running* |
| `Bind for 0.0.0.0:5433 failed: port is already allocated` | Something else is using 5433 | Change the left number in `ports:` (e.g. `"5434:5432"`) and set the same port in `.env` |
| `seed.py`: *Could not connect … Is Postgres running?* | The container is stopped | `docker compose up -d` |
| `password authentication failed for user "noticeboard"` | The volume was first created with different credentials (`POSTGRES_*` only apply on first start) | `docker compose down -v` then `docker compose up -d` (this deletes the data) |
| `seed.py`: *Tables not found* / `relation "users" does not exist` | Migrations haven't run on this database | `alembic upgrade head` |
| `alembic`: `Can't locate revision` | The DB was migrated by a different project (e.g. the old MVP DB) | Make sure `DATABASE_URL` points at port **5433**, not 5432 |
| uvicorn `WinError 10013` / `10048` | Port 8000 is taken (often the v1 server is still running) | Stop it (Ctrl+C in its terminal) or use `--port 8001` |
