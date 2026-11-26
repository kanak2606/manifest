import asyncio
import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.responses import HTMLResponse, StreamingResponse
from pydantic import BaseModel

from ..database import execute, query_all, query_one
from ..events import broker, notify_update
from ..notes_logic import hydrate_note

router = APIRouter(tags=["display"])

def get_kiosk_data(user_id: Optional[int] = None) -> Dict[str, Any]:
    now_dt = datetime.now(timezone.utc)
    today_str = now_dt.strftime("%Y-%m-%d")
    
    # If user_id is None, pick the first user or None for single-user
    if user_id is None:
        first_user = query_one("SELECT id FROM users ORDER BY id ASC LIMIT 1")
        target_uid = first_user["id"] if first_user else None
    else:
        target_uid = user_id

    # 1. Pinned Notes
    if target_uid is not None:
        pinned_rows = query_all(
            """SELECT n.*, 1 as effective_pinned
               FROM notes n
               WHERE n.user_id = ? AND n.pinned = 1 AND n.trashed_at IS NULL AND n.archived = 0 AND n.deleted_at IS NULL
               ORDER BY n.updated_at DESC LIMIT 12""",
            (target_uid,)
        )
    else:
        pinned_rows = query_all(
            """SELECT n.*, 1 as effective_pinned
               FROM notes n
               WHERE n.pinned = 1 AND n.trashed_at IS NULL AND n.archived = 0 AND n.deleted_at IS NULL
               ORDER BY n.updated_at DESC LIMIT 12"""
        )
    pinned_notes = [hydrate_note(target_uid, r) for r in pinned_rows]

    # 2. Tasks Due Today and Overdue
    if target_uid is not None:
        tasks_rows = query_all(
            """SELECT ci.*, n.title as note_title, n.color as note_color
               FROM checklist_items ci
               JOIN notes n ON n.id = ci.note_id
               WHERE n.user_id = ? AND n.archived = 0 AND n.trashed_at IS NULL AND n.deleted_at IS NULL
                 AND ci.deleted_at IS NULL AND ci.checked = 0 AND ci.due_date IS NOT NULL
                 AND ci.due_date <= ?
               ORDER BY ci.due_date ASC, ci.position ASC LIMIT 20""",
            (target_uid, today_str)
        )
    else:
        tasks_rows = query_all(
            """SELECT ci.*, n.title as note_title, n.color as note_color
               FROM checklist_items ci
               JOIN notes n ON n.id = ci.note_id
               WHERE n.archived = 0 AND n.trashed_at IS NULL AND n.deleted_at IS NULL
                 AND ci.deleted_at IS NULL AND ci.checked = 0 AND ci.due_date IS NOT NULL
                 AND ci.due_date <= ?
               ORDER BY ci.due_date ASC, ci.position ASC LIMIT 20""",
            (today_str,)
        )

    # 3. Upcoming Reminders
    if target_uid is not None:
        rem_rows = query_all(
            """SELECT n.id, n.title, n.body_md, n.color, n.reminder_at, n.reminder_rrule, n.reminder_tz
               FROM notes n
               WHERE n.user_id = ? AND n.trashed_at IS NULL AND n.deleted_at IS NULL AND n.reminder_at IS NOT NULL
               ORDER BY n.reminder_at ASC LIMIT 10""",
            (target_uid,)
        )
    else:
        rem_rows = query_all(
            """SELECT n.id, n.title, n.body_md, n.color, n.reminder_at, n.reminder_rrule, n.reminder_tz
               FROM notes n
               WHERE n.trashed_at IS NULL AND n.deleted_at IS NULL AND n.reminder_at IS NOT NULL
               ORDER BY n.reminder_at ASC LIMIT 10"""
        )

    # 4. Recent Notes
    if target_uid is not None:
        recent_rows = query_all(
            """SELECT n.*, n.pinned as effective_pinned
               FROM notes n
               WHERE n.user_id = ? AND n.trashed_at IS NULL AND n.archived = 0 AND n.deleted_at IS NULL
               ORDER BY n.updated_at DESC LIMIT 15""",
            (target_uid,)
        )
    else:
        recent_rows = query_all(
            """SELECT n.*, n.pinned as effective_pinned
               FROM notes n
               WHERE n.trashed_at IS NULL AND n.archived = 0 AND n.deleted_at IS NULL
               ORDER BY n.updated_at DESC LIMIT 15"""
        )
    recent_notes = [hydrate_note(target_uid, r) for r in recent_rows]

    # 5. Daily Habits for Tablet Kiosk
    if target_uid is not None:
        habit_rows = query_all(
            """SELECT h.id, h.title, h.icon, h.color, h.kind, h.options_json,
                      COALESCE(hl.status, 'pending') as status, hl.selected_options
               FROM habits h
               LEFT JOIN habit_logs hl ON hl.habit_id = h.id AND hl.log_date = ?
               WHERE h.user_id = ? AND h.archived = 0
               ORDER BY h.position ASC""",
            (today_str, target_uid)
        )
    else:
        habit_rows = query_all(
            """SELECT h.id, h.title, h.icon, h.color, h.kind, h.options_json,
                      COALESCE(hl.status, 'pending') as status, hl.selected_options
               FROM habits h
               LEFT JOIN habit_logs hl ON hl.habit_id = h.id AND hl.log_date = ?
               WHERE h.archived = 0
               ORDER BY h.position ASC""",
            (today_str,)
        )

    habits_completed = sum(1 for r in habit_rows if r["status"] == "yes")
    habits_total = len(habit_rows)
    habits_pct = round((habits_completed / habits_total) * 100) if habits_total > 0 else 0

    return {
        "today": today_str,
        "pinned_notes": pinned_notes,
        "tasks_due": tasks_rows,
        "reminders": rem_rows,
        "recent_notes": recent_notes,
        "habits": {
            "items": habit_rows,
            "completed": habits_completed,
            "total": habits_total,
            "percent": habits_pct
        },
        "updated_at": now_dt.strftime("%H:%M:%S")
    }

@router.get("/api/display/data")
def api_display_data():
    return get_kiosk_data()

class KioskHabitToggle(BaseModel):
    habit_id: int
    status: str = "yes"

@router.post("/api/display/habit-toggle")
def kiosk_habit_toggle(req: KioskHabitToggle):
    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    first_user = query_one("SELECT id FROM users ORDER BY id ASC LIMIT 1")
    target_uid = first_user["id"] if first_user else 1

    execute(
        """INSERT INTO habit_logs (habit_id, user_id, log_date, status)
           VALUES (?, ?, ?, ?)
           ON CONFLICT(habit_id, log_date) DO UPDATE SET
           status = excluded.status,
           updated_at = datetime('now')""",
        (req.habit_id, target_uid, today_str, req.status)
    )
    notify_update(target_uid, "habits")
    return {"ok": True}

@router.get("/api/display/stream")
async def api_display_stream():
    return StreamingResponse(
        broker.subscribe(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )

DISPLAY_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
  <title>NoteTrace • NiKiosk Display</title>
  <link rel="icon" type="image/png" href="/icons/icon-192.png">
  <style>
    :root {
      --bg: #090a0f;
      --surface-1: #12141c;
      --surface-2: #1a1d28;
      --surface-hover: #222634;
      --border: #282d3d;
      --text-1: #f3f4f6;
      --text-2: #9ca3af;
      --text-muted: #6b7280;
      --accent: #8b5cf6;
      --accent-glow: rgba(139, 92, 246, 0.25);
      --success: #10b981;
      --warning: #f59e0b;
      --danger: #ef4444;
      --font: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; user-select: none; -webkit-user-select: none; }
    body {
      background: var(--bg);
      color: var(--text-1);
      font-family: var(--font);
      height: 100vh;
      width: 100vw;
      overflow: hidden;
      display: flex;
      flex-direction: column;
    }
    header {
      background: var(--surface-1);
      border-bottom: 1px solid var(--border);
      padding: 14px 24px;
      display: flex;
      justify-content: space-between;
      align-items: center;
      flex-shrink: 0;
    }
    .brand-group {
      display: flex;
      align-items: center;
      gap: 14px;
    }
    .brand-logo {
      width: 32px;
      height: 32px;
      border-radius: 8px;
    }
    .brand-title {
      font-size: 20px;
      font-weight: 700;
      letter-spacing: -0.5px;
      background: linear-gradient(135deg, #c084fc, #8b5cf6);
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
    }
    .kiosk-badge {
      background: var(--surface-2);
      border: 1px solid var(--border);
      font-size: 11px;
      font-weight: 600;
      padding: 3px 8px;
      border-radius: 6px;
      color: var(--text-2);
      text-transform: uppercase;
      letter-spacing: 0.5px;
    }
    .clock-group {
      display: flex;
      flex-direction: column;
      align-items: flex-end;
    }
    .live-clock {
      font-size: 26px;
      font-weight: 800;
      font-variant-numeric: tabular-nums;
      letter-spacing: 0.5px;
      color: var(--text-1);
    }
    .live-date {
      font-size: 13px;
      color: var(--text-2);
      font-weight: 500;
    }
    .status-pill {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      font-size: 12px;
      font-weight: 600;
      padding: 4px 10px;
      border-radius: 999px;
      background: rgba(16, 185, 129, 0.12);
      color: var(--success);
      border: 1px solid rgba(16, 185, 129, 0.25);
    }
    .pulse-dot {
      width: 8px;
      height: 8px;
      border-radius: 50%;
      background: var(--success);
      box-shadow: 0 0 8px var(--success);
      animation: pulse 2s infinite;
    }
    @keyframes pulse {
      0% { opacity: 1; transform: scale(1); }
      50% { opacity: 0.4; transform: scale(0.85); }
      100% { opacity: 1; transform: scale(1); }
    }
    main {
      flex: 1;
      overflow-y: auto;
      padding: 20px 24px;
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
      gap: 20px;
    }
    .habit-card {
      cursor: pointer;
      border-left: 4px solid var(--border);
      transition: all 0.2s ease;
    }
    .habit-card.done {
      border-left: 4px solid var(--success);
      background: rgba(16, 185, 129, 0.08);
    }
    .kiosk-check-btn {
      font-size: 11px;
      font-weight: 700;
      padding: 4px 10px;
      border-radius: 6px;
      background: var(--surface-1);
      border: 1px solid var(--border);
      color: var(--text-2);
      transition: all 0.15s ease;
    }
    .kiosk-check-btn.checked {
      background: var(--success);
      color: #000;
      border-color: var(--success);
    }
    .dashboard-panel {
      background: var(--surface-1);
      border: 1px solid var(--border);
      border-radius: 16px;
      padding: 18px 20px;
      display: flex;
      flex-direction: column;
      gap: 14px;
      box-shadow: 0 4px 20px rgba(0,0,0,0.3);
    }
    .panel-head {
      display: flex;
      justify-content: space-between;
      align-items: center;
      border-bottom: 1px solid var(--border);
      padding-bottom: 10px;
    }
    .panel-title {
      font-size: 15px;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.5px;
      color: var(--text-2);
      display: flex;
      align-items: center;
      gap: 8px;
    }
    .panel-count {
      background: var(--surface-2);
      color: var(--accent);
      padding: 2px 8px;
      border-radius: 12px;
      font-size: 12px;
      font-weight: 700;
    }
    .card-list {
      display: flex;
      flex-direction: column;
      gap: 10px;
      overflow-y: auto;
      max-height: 480px;
    }
    .kiosk-card {
      background: var(--surface-2);
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 14px 16px;
      display: flex;
      flex-direction: column;
      gap: 8px;
      transition: transform 0.2s ease, border-color 0.2s ease;
    }
    .kiosk-card.pinned {
      border-left: 4px solid var(--accent);
    }
    .card-header {
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      gap: 10px;
    }
    .card-title {
      font-size: 15px;
      font-weight: 700;
      color: var(--text-1);
      line-height: 1.3;
    }
    .card-body {
      font-size: 13px;
      color: var(--text-2);
      line-height: 1.5;
      white-space: pre-wrap;
      word-break: break-word;
    }
    .task-item {
      display: flex;
      align-items: center;
      gap: 10px;
      padding: 10px 12px;
      background: var(--surface-2);
      border: 1px solid var(--border);
      border-radius: 10px;
    }
    .task-check {
      width: 18px;
      height: 18px;
      border: 2px solid var(--border);
      border-radius: 5px;
      display: flex;
      align-items: center;
      justify-content: center;
      flex-shrink: 0;
    }
    .task-text {
      font-size: 14px;
      font-weight: 500;
      color: var(--text-1);
      flex: 1;
    }
    .task-due {
      font-size: 11px;
      font-weight: 600;
      padding: 2px 6px;
      border-radius: 4px;
      background: rgba(245, 158, 11, 0.15);
      color: var(--warning);
    }
    .empty-msg {
      text-align: center;
      color: var(--text-muted);
      font-size: 13px;
      padding: 24px 0;
    }
    .tag-chip {
      font-size: 11px;
      font-weight: 600;
      padding: 2px 7px;
      border-radius: 6px;
      background: var(--surface-1);
      color: var(--text-2);
      border: 1px solid var(--border);
    }
  </style>
</head>
<body>
  <header>
    <div class="brand-group">
      <img src="/icons/icon-192.png" alt="Logo" class="brand-logo" onerror="this.style.display='none'">
      <div>
        <div style="display:flex; align-items:center; gap:8px;">
          <span class="brand-title">NoteTrace</span>
          <span class="kiosk-badge">Tablet Kiosk</span>
        </div>
      </div>
    </div>
    
    <div style="display:flex; align-items:center; gap:20px;">
      <div class="status-pill" id="live-pill">
        <span class="pulse-dot"></span>
        <span id="live-status">LIVE SYNC</span>
      </div>
      <div class="clock-group">
        <div class="live-clock" id="live-clock">--:--:--</div>
        <div class="live-date" id="live-date">Loading...</div>
      </div>
    </div>
  </header>

  <main>
    <!-- Left Column: Pinned & Important Notes -->
    <div class="dashboard-panel">
      <div class="panel-head">
        <div class="panel-title">
          <span>📌 Pinned Notes</span>
        </div>
        <span class="panel-count" id="pinned-count">0</span>
      </div>
      <div class="card-list" id="pinned-list">
        <div class="empty-msg">No pinned notes</div>
      </div>
    </div>

    <!-- Column 2: Tasks Due & Reminders -->
    <div style="display: flex; flex-direction: column; gap: 20px;">
      <!-- Tasks Due -->
      <div class="dashboard-panel" style="flex: 1;">
        <div class="panel-head">
          <div class="panel-title">
            <span>✅ Tasks Due Today</span>
          </div>
          <span class="panel-count" id="tasks-count">0</span>
        </div>
        <div class="card-list" id="tasks-list">
          <div class="empty-msg">No tasks due today</div>
        </div>
      </div>

      <!-- Upcoming Reminders -->
      <div class="dashboard-panel" style="flex: 1;">
        <div class="panel-head">
          <div class="panel-title">
            <span>⏰ Reminders</span>
          </div>
          <span class="panel-count" id="reminders-count">0</span>
        </div>
        <div class="card-list" id="reminders-list">
          <div class="empty-msg">No upcoming reminders</div>
        </div>
      </div>
    </div>

    <!-- Column 3: Daily Habits & Quick Tap (Tablet Kiosk) -->
    <div class="dashboard-panel">
      <div class="panel-head">
        <div class="panel-title">
          <span>⚡ Daily Habits</span>
        </div>
        <span class="panel-count" id="habits-count">0/0</span>
      </div>
      <div class="card-list" id="habits-list">
        <div class="empty-msg">No habits defined</div>
      </div>
    </div>
  </main>

  <script>
    function updateClock() {
      const now = new Date();
      const clockEl = document.getElementById('live-clock');
      const dateEl = document.getElementById('live-date');
      clockEl.textContent = now.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
      dateEl.textContent = now.toLocaleDateString([], { weekday: 'long', month: 'short', day: 'numeric', year: 'numeric' });
    }
    setInterval(updateClock, 1000);
    updateClock();

    function escapeHtml(str) {
      if (!str) return '';
      return String(str).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
    }

    async function loadData() {
      try {
        const res = await fetch('/api/display/data');
        if (!res.ok) return;
        const d = await res.json();
        renderDashboard(d);
      } catch (err) {
        console.warn('Display fetch error:', err);
      }
    }

    function renderDashboard(data) {
      // 1. Pinned Notes
      const pinnedList = document.getElementById('pinned-list');
      const pinnedCount = document.getElementById('pinned-count');
      const pinned = data.pinned_notes || [];
      pinnedCount.textContent = pinned.length;

      if (!pinned.length) {
        pinnedList.innerHTML = '<div class="empty-msg">No pinned notes</div>';
      } else {
        pinnedList.innerHTML = pinned.map(n => {
          let itemsHtml = '';
          if (n.kind === 'checklist' && n.items) {
            itemsHtml = '<div style="margin-top:6px; display:flex; flex-direction:column; gap:4px;">' +
              n.items.slice(0, 5).map(it => 
                `<div style="font-size:12px; display:flex; align-items:center; gap:6px; color:${it.checked ? 'var(--text-muted)' : 'var(--text-1)'}">` +
                `<span>${it.checked ? '☑' : '☐'}</span>` +
                `<span style="${it.checked ? 'text-decoration:line-through;' : ''}">${escapeHtml(it.text)}</span>` +
                `</div>`
              ).join('') +
              (n.items.length > 5 ? `<div style="font-size:11px; color:var(--text-muted)">+ ${n.items.length - 5} more items</div>` : '') +
              '</div>';
          }
          return `
            <div class="kiosk-card pinned">
              <div class="card-header">
                <div class="card-title">${escapeHtml(n.title || 'Untitled')}</div>
              </div>
              ${n.body_md ? `<div class="card-body">${escapeHtml(n.body_md)}</div>` : ''}
              ${itemsHtml}
            </div>
          `;
        }).join('');
      }

      // 2. Tasks Due
      const tasksList = document.getElementById('tasks-list');
      const tasksCount = document.getElementById('tasks-count');
      const tasks = data.tasks_due || [];
      tasksCount.textContent = tasks.length;

      if (!tasks.length) {
        tasksList.innerHTML = '<div class="empty-msg">No tasks due today 🎉</div>';
      } else {
        tasksList.innerHTML = tasks.map(t => `
          <div class="task-item">
            <div class="task-check"></div>
            <div class="task-text">${escapeHtml(t.text)}</div>
            <div class="task-due">${escapeHtml(t.due_date || 'Today')}</div>
          </div>
        `).join('');
      }

      // 3. Reminders
      const remList = document.getElementById('reminders-list');
      const remCount = document.getElementById('reminders-count');
      const rems = data.reminders || [];
      remCount.textContent = rems.length;

      if (!rems.length) {
        remList.innerHTML = '<div class="empty-msg">No upcoming reminders</div>';
      } else {
        remList.innerHTML = rems.map(r => `
          <div class="task-item">
            <div style="font-size:16px;">⏰</div>
            <div class="task-text">${escapeHtml(r.title || 'Reminder')}</div>
            <div class="tag-chip">${escapeHtml(r.reminder_at || '')}</div>
          </div>
        `).join('');
      }

      // 4. Daily Habits (Interactive 1-Tap on Tablet)
      const habitsList = document.getElementById('habits-list');
      const habitsCount = document.getElementById('habits-count');
      const hData = data.habits || { items: [], completed: 0, total: 0, percent: 0 };
      if (habitsCount) habitsCount.textContent = `${hData.completed}/${hData.total} (${hData.percent}%)`;

      if (habitsList) {
        if (!hData.items || !hData.items.length) {
          habitsList.innerHTML = '<div class="empty-msg">No habits defined</div>';
        } else {
          habitsList.innerHTML = hData.items.map(h => {
            const isDone = h.status === 'yes';
            return `
              <div class="kiosk-card habit-card ${isDone ? 'done' : ''}" onclick="toggleKioskHabit(${h.id}, '${isDone ? 'no' : 'yes'}')">
                <div class="card-header" style="align-items:center;">
                  <div style="display:flex; align-items:center; gap:8px;">
                    <span style="font-size:18px;">${h.icon || '⚡'}</span>
                    <span class="card-title" style="font-size:14px;">${escapeHtml(h.title)}</span>
                  </div>
                  <span class="kiosk-check-btn ${isDone ? 'checked' : ''}">${isDone ? '✓ Done' : 'Tap Done'}</span>
                </div>
              </div>
            `;
          }).join('');
        }
      }
    }

    async function toggleKioskHabit(id, nextStatus) {
      try {
        await fetch('/api/display/habit-toggle', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ habit_id: id, status: nextStatus })
        });
        loadData();
      } catch (err) {
        console.warn('Failed to toggle habit on kiosk:', err);
      }
    }

    // Connect to SSE for real-time live updates
    function connectStream() {
      const livePill = document.getElementById('live-pill');
      const liveStatus = document.getElementById('live-status');
      
      const es = new EventSource('/api/display/stream');
      
      es.onopen = () => {
        livePill.style.color = 'var(--success)';
        liveStatus.textContent = 'LIVE SYNC';
      };

      es.onmessage = (e) => {
        // Any change notification triggers data refresh
        loadData();
      };

      es.onerror = () => {
        livePill.style.color = 'var(--warning)';
        liveStatus.textContent = 'RECONNECTING...';
        es.close();
        setTimeout(connectStream, 3000);
      };
    }

    loadData();
    connectStream();
    // Safety polling fallback every 30 seconds
    setInterval(loadData, 30000);
  </script>
</body>
</html>
"""

@router.get("/display", response_class=HTMLResponse)
def get_display_page():
    return HTMLResponse(content=DISPLAY_HTML)
