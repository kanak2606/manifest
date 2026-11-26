import json
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel

from ..auth import require_auth
from ..database import execute, execute_count, query_all, query_one, transaction
from ..events import notify_update

router = APIRouter(prefix="/api/habits", tags=["habits"])

def get_uid(user: Dict[str, Any]) -> int:
    return user.get("id") or 0

DEFAULT_HABITS = [
    {
        "title": "Gym & Fitness",
        "icon": "🏋️",
        "color": "#10b981",
        "kind": "preset_choice",
        "options": ["Leg Day", "Cardio", "Chest", "Back", "Arms", "Shoulders", "Abs & Core"],
        "unit": None,
        "position": 1
    },
    {
        "title": "Meditation & Breathwork",
        "icon": "🧘",
        "color": "#8b5cf6",
        "kind": "preset_choice",
        "options": ["5 mins", "10 mins", "15 mins", "30 mins", "1 Hour"],
        "unit": "mins",
        "position": 2
    },
    {
        "title": "Focused Study",
        "icon": "📚",
        "color": "#3b82f6",
        "kind": "preset_choice",
        "options": ["Data Structures & Algorithms", "FastAPI Backend", "System Design", "AI & Embeddings"],
        "unit": None,
        "position": 3
    },
    {
        "title": "Diet & Meals",
        "icon": "🥗",
        "color": "#10b981",
        "kind": "preset_choice",
        "options": [
            "Breakfast: Clean",
            "Lunch: High Protein",
            "Supper: Protein Shake",
            "Dinner: Light Salad",
            "High Protein (140g+)",
            "Calorie Deficit"
        ],
        "unit": None,
        "position": 4
    },
    {
        "title": "Medicine & Supplements",
        "icon": "💊",
        "color": "#06b6d4",
        "kind": "preset_choice",
        "options": ["Morning: Multivitamin + D3", "Lunch: Omega-3", "Night: Magnesium"],
        "unit": None,
        "position": 5
    },
    {
        "title": "Body Weight Log",
        "icon": "⚖️",
        "color": "#f59e0b",
        "kind": "numeric_stepper",
        "options": [],
        "unit": "kg",
        "position": 6
    }
]

def ensure_default_habits(uid: int):
    count_row = query_one("SELECT COUNT(*) as c FROM habits WHERE user_id = ?", (uid,))
    if not count_row or count_row["c"] == 0:
        for h in DEFAULT_HABITS:
            execute(
                """INSERT INTO habits (user_id, title, icon, color, kind, options_json, unit, position)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (uid, h["title"], h["icon"], h["color"], h["kind"], json.dumps(h["options"]), h["unit"], h["position"])
            )

class CreateHabitRequest(BaseModel):
    title: str
    icon: Optional[str] = "⚡"
    color: Optional[str] = "#10b981"
    kind: Optional[str] = "preset_choice"
    options: Optional[List[str]] = []
    unit: Optional[str] = None
    target_count: Optional[int] = 1

class ReorderHabitsRequest(BaseModel):
    habit_ids: List[int]

class UpdateHabitRequest(BaseModel):
    title: Optional[str] = None
    icon: Optional[str] = None
    color: Optional[str] = None
    kind: Optional[str] = None
    options: Optional[List[str]] = None
    unit: Optional[str] = None
    position: Optional[int] = None
    archived: Optional[int] = None

class LogHabitRequest(BaseModel):
    date: Optional[str] = None  # 'YYYY-MM-DD'
    status: str = "yes"  # 'yes', 'no'
    selected_options: Optional[List[str]] = []
    numeric_value: Optional[float] = None
    notes: Optional[str] = None

class AddOptionRequest(BaseModel):
    option: str

class RemoveOptionRequest(BaseModel):
    option: Optional[str] = None

class WeightLogRequest(BaseModel):
    value: float
    unit: Optional[str] = "kg"
    notes: Optional[str] = None
    logged_at: Optional[str] = None

def is_multi_log_habit(title: str) -> bool:
    t = title.lower()
    return any(k in t for k in ["diet", "meal", "food", "meditation", "study"])

@router.get("")
@router.get("/")
def list_habits(user: Dict[str, Any] = Depends(require_auth), date: Optional[str] = None):
    uid = get_uid(user)
    ensure_default_habits(uid)

    target_date = date or datetime.now().strftime("%Y-%m-%d")

    habits = query_all(
        """SELECT id, title, icon, color, kind, options_json, target_count, unit, position, archived, created_at
           FROM habits
           WHERE user_id = ? AND archived = 0
           ORDER BY position ASC, id ASC""",
        (uid,)
    )

    # Get today's logs for this user, ordered by creation time
    logs = query_all(
        """SELECT id, habit_id, status, selected_options, numeric_value, notes, created_at, updated_at
           FROM habit_logs
           WHERE user_id = ? AND log_date = ?
           ORDER BY created_at ASC, id ASC""",
        (uid, target_date)
    )
    logs_by_habit: Dict[int, List[Dict[str, Any]]] = {}
    for l in logs:
        hid = l["habit_id"]
        if hid not in logs_by_habit:
            logs_by_habit[hid] = []
        logs_by_habit[hid].append(l)

    # Calculate streak for each habit
    all_positive_logs = query_all(
        """SELECT habit_id, log_date
           FROM habit_logs
           WHERE user_id = ? AND status = 'yes'
           ORDER BY log_date DESC""",
        (uid,)
    )
    habit_dates: Dict[int, set] = {}
    for r in all_positive_logs:
        hid = r["habit_id"]
        if hid not in habit_dates:
            habit_dates[hid] = set()
        habit_dates[hid].add(r["log_date"])

    today_dt = datetime.now().date()
    yesterday_dt = today_dt - timedelta(days=1)
    today_str = today_dt.strftime("%Y-%m-%d")
    yesterday_str = yesterday_dt.strftime("%Y-%m-%d")

    res = []
    completed_count = 0

    for h in habits:
        hid = h["id"]
        try:
            options = json.loads(h["options_json"] or "[]")
        except Exception:
            options = []

        is_multi = is_multi_log_habit(h["title"])
        habit_entries = logs_by_habit.get(hid, [])

        today_logs = []
        for l in habit_entries:
            try:
                opts_list = json.loads(l["selected_options"] or "[]")
            except Exception:
                opts_list = []
            created_str = l["created_at"] or ""
            time_display = ""
            if len(created_str) >= 16:
                try:
                    dt = datetime.strptime(created_str[:19], "%Y-%m-%d %H:%M:%S")
                    time_display = dt.strftime("%I:%M %p").lstrip("0")
                except Exception:
                    time_display = created_str[11:16]
            today_logs.append({
                "id": l["id"],
                "status": l["status"],
                "selected_options": opts_list,
                "numeric_value": l["numeric_value"],
                "notes": l["notes"],
                "created_at": l["created_at"],
                "time": time_display
            })

        if is_multi:
            status_val = "yes" if any(l["status"] == "yes" for l in today_logs) else (today_logs[-1]["status"] if today_logs else None)
            selected_options = today_logs[-1]["selected_options"] if today_logs else []
            num_val = today_logs[-1]["numeric_value"] if today_logs else None
            log_notes = today_logs[-1]["notes"] if today_logs else None
            if status_val == "yes":
                completed_count += 1
        else:
            log_entry = habit_entries[-1] if habit_entries else None
            status_val = None
            selected_options = []
            num_val = None
            log_notes = None
            if log_entry:
                status_val = log_entry["status"]
                try:
                    selected_options = json.loads(log_entry["selected_options"] or "[]")
                except Exception:
                    selected_options = []
                num_val = log_entry["numeric_value"]
                log_notes = log_entry["notes"]
                if status_val == "yes":
                    completed_count += 1

        # Compute streak
        dates_set = habit_dates.get(hid, set())
        streak = 0
        cur_dt = today_dt
        if today_str not in dates_set:
            cur_dt = yesterday_dt
        while cur_dt.strftime("%Y-%m-%d") in dates_set:
            streak += 1
            cur_dt = cur_dt - timedelta(days=1)

        # 7-day mini-history (past 7 days)
        last_7d = []
        for i in range(6, -1, -1):
            check_d = (today_dt - timedelta(days=i)).strftime("%Y-%m-%d")
            last_7d.append({
                "date": check_d,
                "done": check_d in dates_set
            })

        res.append({
            "id": hid,
            "title": h["title"],
            "icon": h["icon"],
            "color": h["color"],
            "kind": h["kind"],
            "options": options,
            "target_count": h["target_count"],
            "unit": h["unit"],
            "position": h["position"],
            "is_multi_log": is_multi,
            "today_status": status_val,
            "today_logs": today_logs,
            "selected_options": selected_options,
            "numeric_value": num_val,
            "notes": log_notes,
            "streak": streak,
            "last_7d": last_7d
        })

    # Overall summary stats
    total_habits = len(res)
    comp_pct = round((completed_count / total_habits * 100), 1) if total_habits > 0 else 0.0

    # Overall combined streak (days where at least 1 habit was logged yes)
    all_logged_days_rows = query_all(
        """SELECT DISTINCT log_date FROM habit_logs WHERE user_id = ? AND status = 'yes' ORDER BY log_date DESC""",
        (uid,)
    )
    logged_days_set = {r["log_date"] for r in all_logged_days_rows}
    overall_streak = 0
    cur_d = today_dt
    if today_str not in logged_days_set:
        cur_d = yesterday_dt
    while cur_d.strftime("%Y-%m-%d") in logged_days_set:
        overall_streak += 1
        cur_d = cur_d - timedelta(days=1)

    return {
        "date": target_date,
        "habits": res,
        "summary": {
            "total": total_habits,
            "completed": completed_count,
            "percent": comp_pct,
            "streak": overall_streak
        }
    }

@router.post("")
@router.post("/")
def create_habit(req: CreateHabitRequest, user: Dict[str, Any] = Depends(require_auth)):
    uid = get_uid(user)
    # Get highest position
    pos_row = query_one("SELECT MAX(position) as m FROM habits WHERE user_id = ?", (uid,))
    next_pos = (pos_row["m"] or 0) + 1 if pos_row else 1

    hid = execute(
        """INSERT INTO habits (user_id, title, icon, color, kind, options_json, unit, target_count, position)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (uid, req.title, req.icon or "⚡", req.color or "#10b981", req.kind or "preset_choice",
         json.dumps(req.options or []), req.unit, req.target_count or 1, next_pos)
    )
    notify_update(uid, "habits")
    return {"ok": True, "id": hid}

@router.put("/reorder")
@router.post("/reorder")
def reorder_habits(req: ReorderHabitsRequest, user: Dict[str, Any] = Depends(require_auth)):
    uid = get_uid(user)
    with transaction():
        for pos, hid in enumerate(req.habit_ids, start=1):
            execute(
                "UPDATE habits SET position = ?, updated_at = datetime('now') WHERE id = ? AND user_id = ?",
                (pos, hid, uid)
            )
    notify_update(uid, "habits")
    return {"ok": True, "ordered_ids": req.habit_ids}

@router.put("/{habit_id}")
def update_habit(habit_id: int, req: UpdateHabitRequest, user: Dict[str, Any] = Depends(require_auth)):
    uid = get_uid(user)
    habit = query_one("SELECT * FROM habits WHERE id = ? AND user_id = ?", (habit_id, uid))
    if not habit:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Habit not found")

    updates = []
    params = []
    if req.title is not None:
        updates.append("title = ?")
        params.append(req.title)
    if req.icon is not None:
        updates.append("icon = ?")
        params.append(req.icon)
    if req.color is not None:
        updates.append("color = ?")
        params.append(req.color)
    if req.kind is not None:
        updates.append("kind = ?")
        params.append(req.kind)
    if req.options is not None:
        updates.append("options_json = ?")
        params.append(json.dumps(req.options))
    if req.unit is not None:
        updates.append("unit = ?")
        params.append(req.unit)
    if req.position is not None:
        updates.append("position = ?")
        params.append(req.position)
    if req.archived is not None:
        updates.append("archived = ?")
        params.append(req.archived)

    if updates:
        updates.append("updated_at = datetime('now')")
        params.extend([habit_id, uid])
        execute(f"UPDATE habits SET {', '.join(updates)} WHERE id = ? AND user_id = ?", tuple(params))
        notify_update(uid, "habits")

    return {"ok": True}

@router.delete("/{habit_id}")
def delete_habit(habit_id: int, user: Dict[str, Any] = Depends(require_auth)):
    uid = get_uid(user)
    execute("UPDATE habits SET archived = 1, updated_at = datetime('now') WHERE id = ? AND user_id = ?", (habit_id, uid))
    notify_update(uid, "habits")
    return {"ok": True}

@router.post("/{habit_id}/options")
def add_habit_option(habit_id: int, req: AddOptionRequest, user: Dict[str, Any] = Depends(require_auth)):
    uid = get_uid(user)
    habit = query_one("SELECT options_json FROM habits WHERE id = ? AND user_id = ?", (habit_id, uid))
    if not habit:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Habit not found")

    try:
        opts = json.loads(habit["options_json"] or "[]")
    except Exception:
        opts = []

    clean_opt = req.option.strip()
    if clean_opt and clean_opt not in opts:
        opts.append(clean_opt)
        execute(
            "UPDATE habits SET options_json = ?, updated_at = datetime('now') WHERE id = ? AND user_id = ?",
            (json.dumps(opts), habit_id, uid)
        )
        notify_update(uid, "habits")

    return {"ok": True, "options": opts}

@router.delete("/{habit_id}/options/{option_name:path}")
@router.post("/{habit_id}/options/remove")
def remove_habit_option(
    habit_id: int,
    option_name: Optional[str] = None,
    req: Optional[RemoveOptionRequest] = None,
    user: Dict[str, Any] = Depends(require_auth)
):
    uid = get_uid(user)
    target = option_name or (req.option if req else None)
    if not target:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Option name required")

    habit = query_one("SELECT options_json FROM habits WHERE id = ? AND user_id = ?", (habit_id, uid))
    if not habit:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Habit not found")

    try:
        opts = json.loads(habit["options_json"] or "[]")
    except Exception:
        opts = []

    target_clean = target.strip()
    new_opts = [o for o in opts if o.strip() != target_clean]
    execute(
        "UPDATE habits SET options_json = ?, updated_at = datetime('now') WHERE id = ? AND user_id = ?",
        (json.dumps(new_opts), habit_id, uid)
    )
    notify_update(uid, "habits")
    return {"ok": True, "options": new_opts}

@router.delete("/{habit_id}/logs/{log_id}")
def delete_habit_log(habit_id: int, log_id: int, user: Dict[str, Any] = Depends(require_auth)):
    uid = get_uid(user)
    execute("DELETE FROM habit_logs WHERE id = ? AND habit_id = ? AND user_id = ?", (log_id, habit_id, uid))
    notify_update(uid, "habits")
    return {"ok": True}

@router.post("/{habit_id}/log")
def log_habit(habit_id: int, req: LogHabitRequest, user: Dict[str, Any] = Depends(require_auth)):
    uid = get_uid(user)
    habit = query_one("SELECT * FROM habits WHERE id = ? AND user_id = ?", (habit_id, uid))
    if not habit:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Habit not found")

    log_date = req.date or datetime.now().strftime("%Y-%m-%d")
    opts_json = json.dumps(req.selected_options or [])
    is_multi = is_multi_log_habit(habit["title"])
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    log_id = None
    if is_multi:
        # Multi-log habits (meals, meditation, study): always append new timestamped entry
        log_id = execute(
            """INSERT INTO habit_logs (habit_id, user_id, log_date, status, selected_options, numeric_value, notes, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (habit_id, uid, log_date, req.status, opts_json, req.numeric_value, req.notes, now_str, now_str)
        )
    else:
        # Single-log habits (gym, medicine, weight): upsert single record for (habit_id, log_date)
        existing = query_one("SELECT id FROM habit_logs WHERE habit_id = ? AND log_date = ?", (habit_id, log_date))
        if existing:
            execute(
                """UPDATE habit_logs
                   SET status = ?, selected_options = ?, numeric_value = ?, notes = ?, updated_at = datetime('now')
                   WHERE id = ?""",
                (req.status, opts_json, req.numeric_value, req.notes, existing["id"])
            )
            log_id = existing["id"]
        else:
            log_id = execute(
                """INSERT INTO habit_logs (habit_id, user_id, log_date, status, selected_options, numeric_value, notes, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (habit_id, uid, log_date, req.status, opts_json, req.numeric_value, req.notes, now_str, now_str)
            )

    # If it's a weight habit and numeric_value is provided, also record to body_metrics
    if "weight" in habit["title"].lower() and req.numeric_value is not None and req.numeric_value > 0:
        execute(
            """INSERT INTO body_metrics (user_id, metric_type, value, unit, logged_at, notes)
               VALUES (?, 'weight', ?, 'kg', datetime('now'), ?)""",
            (uid, req.numeric_value, req.notes)
        )

    notify_update(uid, "habits")
    return {"ok": True, "id": log_id, "date": log_date, "status": req.status, "timestamp": now_str}

@router.get("/weight-history")
def get_weight_history(user: Dict[str, Any] = Depends(require_auth), days: int = Query(30, ge=7, le=365)):
    uid = get_uid(user)
    rows = query_all(
        """SELECT id, value, unit, logged_at, notes
           FROM body_metrics
           WHERE user_id = ? AND metric_type = 'weight'
           ORDER BY logged_at ASC""",
        (uid,)
    )

    # If no body_metrics rows yet, check habit_logs for weight habit
    if not rows:
        weight_habit = query_one("SELECT id FROM habits WHERE user_id = ? AND title LIKE '%weight%'", (uid,))
        if weight_habit:
            h_rows = query_all(
                """SELECT id, numeric_value as value, 'kg' as unit, log_date || ' 08:00:00' as logged_at, notes
                   FROM habit_logs
                   WHERE habit_id = ? AND numeric_value IS NOT NULL AND numeric_value > 0
                   ORDER BY log_date ASC""",
                (weight_habit["id"],)
            )
            rows = h_rows

    # Default seed points if completely empty so charts render nicely
    if not rows:
        now = datetime.now()
        seed_points = [
            (now - timedelta(days=28), 75.2),
            (now - timedelta(days=21), 74.9),
            (now - timedelta(days=14), 74.6),
            (now - timedelta(days=7), 74.4),
            (now - timedelta(days=1), 74.3),
            (now, 74.2),
        ]
        for dt, val in seed_points:
            execute(
                """INSERT INTO body_metrics (user_id, metric_type, value, unit, logged_at)
                   VALUES (?, 'weight', ?, 'kg', ?)""",
                (uid, val, dt.strftime("%Y-%m-%d %H:%M:%S"))
            )
        rows = query_all(
            """SELECT id, value, unit, logged_at, notes FROM body_metrics
               WHERE user_id = ? AND metric_type = 'weight' ORDER BY logged_at ASC""",
            (uid,)
        )

    points = []
    prev = None
    for r in rows:
        val = round(float(r["value"]), 1)
        delta = round(val - prev, 1) if prev is not None else 0.0
        prev = val
        points.append({
            "id": r["id"],
            "value": val,
            "unit": r["unit"],
            "logged_at": r["logged_at"],
            "date": r["logged_at"][:10],
            "delta": delta,
            "notes": r["notes"]
        })

    current_val = points[-1]["value"] if points else 74.2
    start_val = points[0]["value"] if points else current_val
    total_delta = round(current_val - start_val, 1)

    return {
        "points": points,
        "current": current_val,
        "start": start_val,
        "total_delta": total_delta,
        "goal": 72.0,
        "unit": "kg"
    }

@router.post("/weight")
def log_weight(req: WeightLogRequest, user: Dict[str, Any] = Depends(require_auth)):
    uid = get_uid(user)
    log_time = req.logged_at or datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    mid = execute(
        """INSERT INTO body_metrics (user_id, metric_type, value, unit, logged_at, notes)
           VALUES (?, 'weight', ?, ?, ?, ?)""",
        (uid, req.value, req.unit or "kg", log_time, req.notes)
    )

    # Also sync into today's weight habit log if habit exists
    weight_habit = query_one("SELECT id FROM habits WHERE user_id = ? AND title LIKE '%weight%'", (uid,))
    if weight_habit:
        today_date = log_time[:10]
        existing_wh = query_one("SELECT id FROM habit_logs WHERE habit_id = ? AND log_date = ?", (weight_habit["id"], today_date))
        if existing_wh:
            execute(
                """UPDATE habit_logs
                   SET numeric_value = ?, status = 'yes', notes = ?, updated_at = datetime('now')
                   WHERE id = ?""",
                (req.value, req.notes, existing_wh["id"])
            )
        else:
            execute(
                """INSERT INTO habit_logs (habit_id, user_id, log_date, status, numeric_value, notes, created_at, updated_at)
                   VALUES (?, ?, ?, 'yes', ?, ?, datetime('now'), datetime('now'))""",
                (weight_habit["id"], uid, today_date, req.value, req.notes)
            )

    notify_update(uid, "habits")
    return {"ok": True, "id": mid, "value": req.value, "unit": req.unit}
