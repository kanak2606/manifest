import sys
sys.path.insert(0, '.')
import sqlite3
import json
import urllib.request
from notetrace_backend.auth import sign_token

def verify_db():
    print("=================== 1. DATABASE RECORDS VERIFICATION ===================")
    conn = sqlite3.connect('data/notetrace.db')
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    print("\n--- HABITS ---")
    c.execute("SELECT id, title, kind, options_json FROM habits")
    habits = c.fetchall()
    habit_map = {}
    for h in habits:
        habit_map[h["id"]] = h["title"]
        print(f"ID {h['id']}: {h['title']} ({h['kind']}) -> {h['options_json']}")

    print("\n--- HABIT_LOGS ---")
    c.execute("SELECT id, habit_id, user_id, log_date, status, selected_options, numeric_value, notes FROM habit_logs")
    logs = c.fetchall()
    print(f"Total habit logs: {len(logs)}")
    for l in logs:
        title = habit_map.get(l["habit_id"], f"Habit #{l['habit_id']}")
        print(f"Log #{l['id']}: Habit '{title}' | Date={l['log_date']} | Status={l['status']} | Options={l['selected_options']} | Num={l['numeric_value']}")

    print("\n--- BODY_METRICS ---")
    c.execute("SELECT id, user_id, metric_type, value, unit, logged_at FROM body_metrics ORDER BY id DESC")
    metrics = c.fetchall()
    print(f"Total body metrics: {len(metrics)}")
    for m in metrics:
        print(f"Metric #{m['id']}: User={m['user_id']} | Type={m['metric_type']} | Value={m['value']} {m['unit']} | LoggedAt={m['logged_at']}")

    print("\n--- FOCUS_SESSIONS ---")
    c.execute("SELECT id, user_id, note_id, item_uuid, session_type, duration_min, actual_sec, status, started_at, completed_at FROM focus_sessions ORDER BY id DESC")
    sessions = c.fetchall()
    print(f"Total focus sessions: {len(sessions)}")
    for s in sessions:
        print(f"Session #{s['id']}: User={s['user_id']} | Note={s['note_id']} | Type={s['session_type']} | Duration={s['duration_min']}m | Actual={s['actual_sec']}s | Status={s['status']}")

def verify_apis():
    print("\n=================== 2. API ENDPOINTS VERIFICATION ===================")
    token = sign_token({'id': 68, 'username': 'admin', 'role': 'admin'})
    headers = {'Authorization': f'Bearer {token}'}

    endpoints = [
        ('/api/display/data', False),
        ('/api/habits', True),
        ('/api/habits/weight-history', True),
        ('/api/focus/active', True),
        ('/api/focus/today-summary', True),
        ('/api/analytics', True),
    ]

    for path, needs_auth in endpoints:
        h = headers if needs_auth else {}
        req = urllib.request.Request(f'http://localhost:8080{path}', headers=h)
        try:
            with urllib.request.urlopen(req) as resp:
                status_code = resp.status
                body = resp.read().decode('utf-8')
                data = json.loads(body)
                print(f"SUCCESS [200 OK]: {path} (keys: {list(data.keys()) if isinstance(data, dict) else len(data)})")
                if path == '/api/display/data':
                    habits_info = data.get('habits', {})
                    print(f"  -> Kiosk Habits: {habits_info.get('completed')}/{habits_info.get('total')} ({habits_info.get('percent')}%)")
                elif path == '/api/habits':
                    summary = data.get('summary', {})
                    print(f"  -> Habits Summary: {summary.get('completed')}/{summary.get('total')} ({summary.get('percent')}%), streak={summary.get('streak')}")
                elif path == '/api/habits/weight-history':
                    print(f"  -> Weight History Entries: {len(data.get('history', []))}")
                    if data.get('history'):
                        print(f"  -> Latest Weight: {data['history'][-1]}")
                elif path == '/api/analytics':
                    print(f"  -> Analytics keys: focus={bool(data.get('focus'))}, habits={bool(data.get('habits'))}, tasks={bool(data.get('tasks'))}")
                    if 'habits' in data:
                        print(f"  -> Analytics Habits summary: {data['habits'].get('summary')}")
                    if 'focus' in data:
                        print(f"  -> Analytics Focus total_focus_sec: {data['focus'].get('total_focus_sec')}, ranked_projects: {len(data['focus'].get('ranked_projects', []))}")
        except Exception as e:
            print(f"FAILED: {path} -> {e}")

if __name__ == '__main__':
    verify_db()
    verify_apis()
