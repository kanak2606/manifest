# Manifest

> A self-hosted, local-first personal workspace for notes, tasks, habit tracking, focus/Pomodoro timers, and productivity analytics — built on **Python FastAPI + SQLite (WAL & FTS5)** with a pre-built static web UI and zero Docker or Node.js runtime dependencies.

Tailored for running seamlessly on **Windows** as well as **Samsung tablets / ARM64 Android devices via Termux** with a dedicated real-time **NiKiosk** dashboard (`/display`).

---

## Table of Contents

1. [Overview & Architecture](#overview--architecture)
2. [Core Features](#core-features)
3. [Quick Start (Windows / Desktop)](#quick-start-windows--desktop)
4. [Samsung Tablet / Termux Installation](#samsung-tablet--termux-installation)
5. [NiKiosk Display Configuration](#nikiosk-display-configuration)
6. [Windows Laptop Wi-Fi Access & Auto-Login](#windows-laptop-wi-fi-access--auto-login)
7. [Samsung Battery Optimization & Termux:Boot](#samsung-battery-optimization--termuxboot)
8. [Automated Backups & Packaging](#automated-backups--packaging)
9. [Running Tests & Migrations](#running-tests--migrations)
10. [Configuration & Environment Variables](#configuration--environment-variables)

---

## Overview & Architecture

Manifest (`notetrace_backend`) runs a lightweight, thread-safe FastAPI backend backed by pure Python `sqlite3` (WAL mode + FTS5 full-text search) and serves ahead-of-time compiled static frontend assets (`static/`).

```text
       +-------------------------------------------------------------+
       |            HOST DEVICE (0.0.0.0:8000 / Termux / Win)        |
       |                                                             |
       |  +--------------------+         +------------------------+  |
       |  |  NiKiosk App       |         | Python 3.10+           |  |
       |  |  URL: /display     | <=====> | FastAPI + Uvicorn      |  |
       |  |  (Read-only Kiosk) |   SSE   | SQLite (WAL + FTS5)    |  |
       |  +--------------------+         +-----------^------------+  |
       |                                             |               |
       +---------------------------------------------|---------------+
                                                     | Local Wi-Fi
                                                     | HTTP :8000
                                       +-------------v---------------+
                                       |   LAPTOP / DESKTOP BROWSER  |
                                       |   http://<host-ip>:8000     |
                                       |   (Full Interactive Editor) |
                                       +-----------------------------+
```

### Project Layout

```text
.
├── notetrace_backend/        # FastAPI application, SQLite layer, scheduler, and routers
│   ├── main.py               # App entrypoint, auth/CSRF middleware, static & upload serving
│   ├── config.py             # Paths, server host/port, JWT & rate-limit configuration
│   ├── database.py           # Thread-safe SQLite (WAL + FTS5) helpers & schema setup
│   ├── notes_logic.py        # Note CRUD, checklists, wikilinks, search, and task queries
│   ├── scheduler.py          # Background reminder & maintenance scheduler
│   └── routers/              # API routes: notes, habits, focus, analytics, sync, mcp, etc.
├── static/                   # Compiled frontend assets & PDF.js viewer
├── scripts/                  # DB migrations, tablet sync/SSH scripts, and ZIP packager
├── termux/                   # Termux installer, start/stop scripts, backup, and boot hook
├── tests/                    # Unit & API integration tests
├── run.py                    # Local launcher printing LAN & kiosk URLs
└── requirements.txt          # Python dependencies
```

---

## Core Features

- **Notes & Formatting:** Markdown notes, drag-and-drop checklists, rich drawings, image/file attachments, PDF viewing, and color coding.
- **Tasks & Reminders:** Due dates, repeating task rules (`daily`, `weekly`, `monthly`, `yearly`, `weekdays`), and RRULE recurring reminders.
- **Habit Tracking (`/api/habits`):** Customizable habits (preset choices, numeric/counter tracking, streaks, and daily logging).
- **Focus / Pomodoro Timer (`/api/focus`):** Focus, short break, and long break sessions linked directly to notes or checklist tasks.
- **Productivity Analytics (`/api/analytics`):** Task completion metrics (today, 7-day, monthly, all-time), focus time, and habit insights.
- **Organization & Search:** Color-coded labels/tags, pinned notes, archive, `[[Title]]` wikilinks with backlinks, and SQLite FTS5 multi-field search.
- **History & Recovery:** Automatic version snapshots on edits/conflicts, 30-day soft trash with auto-purge, and full restore.
- **Collaboration & Sharing:** Multi-user auth (bcrypt/JWT), note member invitations (`view` / `edit` roles), and read-only public links (`/n/:token`).
- **Integrations & Sync:** Personal Access Tokens (`note_pat_*`), JSON-RPC MCP endpoint (`/api/mcp` for `list_notes`, `get_note`, `create_note`), webhooks, link previews, full-backup ZIP export/import, and multi-device sync.

---

## Quick Start (Windows / Desktop)

1. **Create and activate a virtual environment:**
   ```powershell
   python -m venv .venv
   .venv\Scripts\Activate.ps1
   ```
2. **Install dependencies:**
   ```powershell
   pip install -r requirements.txt
   ```
3. **Run the server:**
   ```powershell
   python run.py
   ```
   Or double-click `run.bat`. The terminal will print your local URL (`http://localhost:8000`) and your LAN/tablet URLs.

---

## Samsung Tablet / Termux Installation

### Step 1: Install Termux & Termux:Boot
> **Important:** Install Termux from **F-Droid** rather than the Google Play Store:
- [Termux on F-Droid](https://f-droid.org/packages/com.termux/)
- [Termux:Boot on F-Droid](https://f-droid.org/packages/com.termux.boot/)

### Step 2: Transfer & Install
Clone or copy this repository to `$HOME/NoteTrace` in Termux, then run:
```bash
cd ~/NoteTrace
chmod +x termux/*.sh
./termux/install.sh
```
The installer acquires a wake lock, requests storage permissions, installs Python and build tools via `pkg`, creates `.venv`, installs `requirements.txt`, initializes `data/`, and links Termux:Boot startup scripts.

### Step 3: Start / Stop
```bash
./termux/start.sh   # Start server in background
./termux/stop.sh    # Stop server
```

---

## NiKiosk Display Configuration

1. Install **NiKiosk** from Google Play or F-Droid.
2. Set the **Kiosk URL** to:
   ```text
   http://127.0.0.1:8000/display
   ```
3. Enable **Auto-start on boot** and **Keep screen on**.
4. The `/display` dashboard shows a live clock/date, pinned notes, overdue & today's tasks, upcoming reminders, and updates in real time via Server-Sent Events (`/api/display/stream`).

---

## Windows Laptop Wi-Fi Access & Auto-Login

With your tablet and laptop on the same Wi-Fi network, open:
```text
http://<TABLET_IP>:8000
```
*(Find your tablet IP in Termux with `ip -4 addr show wlan0`.)*

### Bookmark / Kiosk Auto-Login
You can pass credentials or an API token via URL query parameters for one-tap bookmarks:
- `http://<TABLET_IP>:8000/?u=admin&p=YOUR_PASSWORD`
- `http://<TABLET_IP>:8000/?token=note_pat_...`
- Append `&redirect=/display` to jump straight to the kiosk view.

The server validates credentials, sets an `HttpOnly` session cookie (`note_token`), and issues an immediate HTTP 303 redirect to strip sensitive query parameters from browser history (with IP rate limiting of 5 failed attempts per 60 seconds).

---

## Samsung Battery Optimization & Termux:Boot

1. **Termux Wake Lock:** `termux/start.sh` calls `termux-wake-lock` automatically.
2. **Android Battery Settings:**
   - **Settings → Apps → Termux → Battery** → set to **Unrestricted**.
   - **Settings → Device Care → Battery → Background usage limits → Never sleeping apps** → add **Termux** and **NiKiosk**.
3. **Termux:Boot:** Open the **Termux:Boot** app once after installation. `termux/install.sh` places `~/.termux/boot/notetrace-boot.sh` to start Manifest automatically after reboot.

---

## Automated Backups & Packaging

### Tablet / Termux Backups
```bash
./termux/backup.sh
```
Creates a live `.tar.gz` snapshot of `data/notetrace.db` and `data/uploads/` in both `data/backups/` and `~/storage/shared/NoteTrace/backups/`, retaining the last 14 backups.

### Clean Release ZIP Packager
```powershell
python scripts/package_manifest.py
```
Packages `notetrace_backend/`, `static/`, `termux/`, `scripts/`, and launcher files into a timestamped `Manifest-Clean-*.zip`.

---

## Running Tests & Migrations

Initialize or verify the SQLite schema and FTS5 tables:
```bash
python scripts/migrate.py
```

Run the test suite:
```bash
python -m unittest discover -s tests -p "test_*.py"
```

---

## Configuration & Environment Variables

Configure via environment variables or a `.env` file in the project root:

| Variable | Default | Description |
|---|---|---|
| `HOST` | `0.0.0.0` | Server bind address |
| `PORT` | `8000` | Server port |
| `DATA_DIR` | `./data` | Base directory for database, uploads, and backups |
| `DB_PATH` | `./data/notetrace.db` | SQLite database path |
| `UPLOADS_PATH` | `./data/uploads` | Stored attachments and images |
| `BACKUPS_PATH` | `./data/backups` | Local backup archives |
| `JWT_SECRET` | Auto / dev fallback | Secret key for JWT sessions |
| `SINGLE_USER_MODE` | `0` | Set to `1` to bypass multi-user auth |
| `ALLOW_REGISTRATION` | `1` | Enable/disable new user registration |
| `TRASH_RETENTION_DAYS` | `30` | Days before trashed notes are purged |
| `API_RATE_LIMIT_PER_MIN` | `60` | Per-minute API rate limit |
