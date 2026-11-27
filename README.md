# Manifest — Local-First Second Brain, PKM & MCP Productivity Engine

A **self-hosted, local-first, privacy-first** Personal Knowledge Management (**PKM**) and productivity workspace built on **FastAPI** and zero-config **SQLite (WAL + FTS5)** with a built-in **Model Context Protocol (MCP) server** for AI agents — no Docker or Node.js runtime required.

Runs on **Windows**, **Linux**, and **Android / Termux** with a real-time `/display` **kiosk dashboard** for **NiKiosk**.

<p align="center">
  <img src="docs/manifest-launch.gif" alt="Manifest Product Launch Demo — Notes, Habits, Focus Timer, Analytics & Kiosk" width="100%" />
</p>

---

## Technical Architecture

```mermaid
flowchart LR
    subgraph Clients["Clients & AI Agents"]
        B["Desktop / Laptop Browser<br/>Full PKM & Editor UI"]
        K["Tablet NiKiosk (/display)<br/>Real-Time Kiosk Dashboard"]
        M["AI Agents & MCP Clients<br/>JSON-RPC /api/mcp (PAT)"]
    end

    subgraph Edge["FastAPI Middleware (main.py)"]
        AUTH["Auth & Session<br/>JWT Cookie / Bearer PAT"]
        CSRF["CSRF & Rate Limiter<br/>5 req/60s Auto-Login"]
        STATIC["Static UI & Uploads<br/>static/ + /uploads/*"]
    end

    subgraph Routers["API Routers (notetrace_backend/routers/)"]
        R_NOTES["Second Brain & PKM<br/>notes.py · labels.py · public_notes.py"]
        R_PROD["Productivity & Habits<br/>habits.py · focus.py · analytics.py"]
        R_RT["Real-Time & Sync<br/>display.py (SSE) · sync.py · notify.py"]
        R_EXT["AI, MCP & Backups<br/>mcp.py · ai.py · webhooks.py · full_backup.py"]
    end

    subgraph Core["Core Engine"]
        LOGIC["notes_logic.py<br/>CRUD · Wikilinks · FTS5 Search"]
        SCHED["scheduler.py<br/>Reminders & Trash Purge"]
        EVT["events.py<br/>SSE Event Bus"]
    end

    subgraph Storage["Local-First Persistence"]
        DB[("SQLite (WAL + FTS5)<br/>data/notetrace.db")]
        FS[("Attachments & Backups<br/>data/uploads/ · data/backups/")]
    end

    B -->|HTTP :8000| AUTH
    K -->|SSE /api/display/stream| AUTH
    M -->|MCP JSON-RPC| AUTH

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

## Key Capabilities

- **Second Brain & PKM:** Markdown notes, `[[Title]]` wikilinks, backlinks, drag-and-drop checklists, drawings, PDF.js viewer, and instant **SQLite FTS5** full-text search.
- **Native MCP Server (`/api/mcp`):** JSON-RPC endpoint (`list_notes`, `get_note`, `create_note`) secured by Personal Access Tokens (`note_pat_*`) for connecting **AI coding assistants and agentic workflows**.
- **Tasks, Habits & Focus:** Recurring tasks (RRULE), custom **habit tracker** with streaks (`/api/habits`), **Pomodoro / focus timer** (`/api/focus`), and **productivity analytics** (`/api/analytics`).
- **Offline-First & Kiosk Ready (`/display`):** Single-file SQLite persistence, live Server-Sent Events (`/api/display/stream`), webhooks, multi-device sync, and ZIP backups.

---

## Quick Start

### Windows / Desktop
```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python run.py
```
Open `http://localhost:8000` (or the LAN IP printed in the terminal).

### Android / Termux + NiKiosk
Install **Termux** and **Termux:Boot** from F-Droid, copy to `~/NoteTrace`, and run:
```bash
cd ~/NoteTrace && chmod +x termux/*.sh
./termux/install.sh
./termux/start.sh      # Stop anytime with ./termux/stop.sh
```
Set **NiKiosk** URL to `http://127.0.0.1:8000/display` and Termux battery to **Unrestricted**.

---

## Auto-Login Bookmarks

```text
http://<HOST_IP>:8000/?u=admin&p=YOUR_PASSWORD&redirect=/display
http://<HOST_IP>:8000/?token=note_pat_...&redirect=/display
```
Sets an `HttpOnly` cookie and issues an HTTP 303 redirect to strip credentials from browser history.

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
