import calendar
import re
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any

TASK_REPEATS = ['daily', 'weekdays', 'weekly', 'monthly', 'yearly']

def clean_task_repeat(v: Optional[str]) -> Optional[str]:
    return v if v in TASK_REPEATS else None

def _parse_date(s: Optional[str]) -> Optional[datetime]:
    if not s or not re.match(r'^\d{4}-\d{2}-\d{2}$', str(s).strip()):
        return None
    try:
        return datetime.strptime(str(s).strip(), "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except Exception:
        return None

def _fmt_date(d: datetime) -> str:
    return d.strftime("%Y-%m-%d")

def _step_date(d: datetime, repeat: str) -> datetime:
    if repeat == 'daily':
        return d + timedelta(days=1)
    elif repeat == 'weekdays':
        n = d + timedelta(days=1)
        # Monday is 0, Sunday is 6
        if n.weekday() == 5: # Saturday -> Monday
            return n + timedelta(days=2)
        elif n.weekday() == 6: # Sunday -> Monday
            return n + timedelta(days=1)
        return n
    elif repeat == 'weekly':
        return d + timedelta(days=7)
    elif repeat == 'monthly':
        y = d.year
        m = d.month + 1
        if m > 12:
            m = 1
            y += 1
        day = min(d.day, calendar.monthrange(y, m)[1])
        return datetime(y, m, day, tzinfo=timezone.utc)
    elif repeat == 'yearly':
        y = d.year + 1
        m = d.month
        day = min(d.day, calendar.monthrange(y, m)[1])
        return datetime(y, m, day, tzinfo=timezone.utc)
    return d

def next_due_date(due: Optional[str], repeat: Optional[str], today: Optional[str] = None) -> Optional[str]:
    from_d = _parse_date(due)
    if not from_d or not clean_task_repeat(repeat):
        return None
    limit_d = _parse_date(today)
    limit_str = _fmt_date(limit_d) if limit_d else _fmt_date(from_d)
    
    d = _step_date(from_d, repeat)
    guard = 0
    while _fmt_date(d) <= limit_str and guard < 20000:
        d = _step_date(d, repeat)
        guard += 1
    return _fmt_date(d)

def is_task(note: Optional[Dict[str, Any]], item: Optional[Dict[str, Any]], all_checklists: bool = False) -> bool:
    if not note or note.get('kind') != 'checklist' or not item or item.get('checked'):
        return False
    if not str(item.get('text', '')).strip():
        return False
    return all_checklists or bool(item.get('due_date')) or bool(note.get('in_tasks'))

def item_after_patch(item: Dict[str, Any], patch: Dict[str, Any], today: Optional[str] = None) -> Dict[str, Any]:
    next_item = dict(item)
    for k in ['text', 'checked', 'position', 'due_date', 'due_repeat']:
        if k in patch:
            next_item[k] = patch[k]
    
    if not next_item.get('due_date'):
        next_item['due_repeat'] = None
        
    was_checked = bool(item.get('checked'))
    is_now_checked = bool(next_item.get('checked'))
    repeat = clean_task_repeat(next_item.get('due_repeat'))
    
    if is_now_checked and not was_checked and repeat:
        moved = next_due_date(next_item.get('due_date'), repeat, today or next_item.get('due_date'))
        if moved:
            next_item['due_date'] = moved
            next_item['checked'] = False
            
    return next_item
