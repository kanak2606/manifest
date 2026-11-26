# Manifest

Self-hosted, local-first workspace for **notes, tasks, habits, focus timers, and analytics** — powered by **FastAPI + SQLite (WAL & FTS5)** with a pre-built static UI and zero Docker or Node.js runtime dependencies.

Runs on **Windows** and **Android/Termux** (with a real-time `/display` kiosk mode for **NiKiosk**).

---

## Technical Architecture

```mermaid
flowchart LR
    subgraph Clients["Clients"]
        B["Desktop / Laptop Browser<br/>Full Editor UI"]
        K["Tablet NiKiosk (/display)<br/>Read-Only Dashboard"]
        M["MCP / API Clients<br/>Bearer PAT (note_pat_*)"]
    end

    subgraph Edge["FastAPI Middleware (main.py)"]
        AUTH["Auth & Session<br/>JWT Cookie / Bearer PAT"]
        CSRF["CSRF & Rate Limiter<br/>5 req/60s Auto-Login"]
        STATIC["Static UI & Uploads<br/>static/ + /uploads/*"]
    end

    subgraph Routers["API Routers (notetrace_backend/routers/)"]
        R_NOTES["Notes & Checklists<br/>notes.py · labels.py · public_notes.py"]
        R_PROD["Productivity<br/>habits.py · focus.py · analytics.py"]
        R_RT["Real-Time & Sync<br/>display.py (SSE) · sync.py · notify.py"]
        R_EXT["Integrations & Ops<br/>mcp.py · webhooks.py · full_backup.py · ai.py"]
    end

    subgraph Core["Core Engine"]
        LOGIC["notes_logic.py<br/>CRUD · Wikilinks · Search"]
        SCHED["scheduler.py<br/>Reminders & Trash Purge"]
        EVT["events.py<br/>SSE Event Bus"]
    end

    subgraph Storage["Persistence Layer"]
        DB[("SQLite (WAL + FTS5)<br/>data/notetrace.db")]
        FS[("Attachments & Backups<br/>data/uploads/ · data/backups/")]
    end

    B -->|HTTP :8000| AUTH
    K -->|SSE /api/display/stream| AUTH
    M -->|JSON-RPC /api/mcp| AUTH

    AUTH --> CSRF --> STATIC
    CSRF --> R_NOTES & R_PROD & R_RT & R_EXT

    R_NOTES --> LOGIC
    R_PROD --> LOGIC
    R_RT --> EVT
    R_EXT --> LOGIC

    LOGIC --> DB
    SCHED --> DB
    R_PROD --> DB
    R_EXT --> FS
    STATIC --> FS
```

---

## Features

- **Notes & Checklists:** Markdown, drag-and-drop checklists, drawings, file/image uploads, PDF.js viewer, `[[Title]]` wikilinks, backlinks, and FTS5 full-text search.
- **Tasks & Reminders:** Due dates, recurring rules (`daily`, `weekly`, `monthly`, `yearly`, `weekdays`), and RRULE reminders.
- **Habits & Focus (`/api/habits`, `/api/focus`):** Custom habit tracking, streaks, and Pomodoro/focus sessions linked to notes or tasks.
- **Analytics (`/api/analytics`):** Task completion, focus time, and habit metrics.
- **Kiosk Mode (`/display`):** Live clock, pinned notes, due tasks, and instant SSE updates (`/api/display/stream`).
- **Auth, Sync & Integrations:** Multi-user bcrypt/JWT auth, shared note roles (`view`/`edit`), Personal Access Tokens (`note_pat_*`), `/api/mcp` JSON-RPC endpoint, webhooks, and ZIP backups.

---

## Quick Start

### Windows / Desktop
```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python run.py
```
Access at `http://localhost:8000` (or the LAN IP printed in the console).

### Samsung Tablet (Termux + NiKiosk)
Install **Termux** and **Termux:Boot** from F-Droid, copy the project to `~/NoteTrace`, and run:
```bash
cd ~/NoteTrace && chmod +x termux/*.sh
./termux/install.sh
./termux/start.sh      # Stop anytime with ./termux/stop.sh
```
Point **NiKiosk** to `http://127.0.0.1:8000/display` and set Termux battery optimization to **Unrestricted**.

---

## Auto-Login Bookmarks

```text
http://<HOST_IP>:8000/?u=admin&p=YOUR_PASSWORD&redirect=/display
http://<HOST_IP>:8000/?token=note_pat_...&redirect=/display
```
Sets an `HttpOnly` session cookie and issues an immediate HTTP 303 redirect to strip credentials from browser history.

---

## Tests, Migrations & Packaging

```bash
python scripts/migrate.py                              # Initialize/verify SQLite + FTS5 schema
python -m unittest discover -s tests -p "test_*.py"    # Run test suite
python scripts/package_manifest.py                     # Build clean release ZIP
./termux/backup.sh                                     # Live SQLite + uploads snapshot (Termux)
```

---

## Environment Variables

| Variable | Default | Purpose |
|---|---|---|
| `HOST` / `PORT` | `0.0.0.0` / `8000` | Bind address and port |
| `DATA_DIR` | `./data` | Base dir for DB, uploads, and backups |
| `DB_PATH` | `./data/notetrace.db` | SQLite database path |
| `JWT_SECRET` | Auto / dev fallback | JWT signing secret |
| `SINGLE_USER_MODE` | `0` | `1` bypasses multi-user auth |
| `ALLOW_REGISTRATION` | `1` | Enable/disable user sign-ups |
| `TRASH_RETENTION_DAYS` | `30` | Days before trashed notes purge |
| `API_RATE_LIMIT_PER_MIN` | `60` | Per-minute API rate limit |
