import calendar
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any
from zoneinfo import ZoneInfo

REPEATS = ['daily', 'weekly', 'monthly', 'yearly']
LATE_WINDOW_MS = 2 * 60 * 60 * 1000

def parse_utc(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    st = str(s).strip()
    if 'T' in st:
        iso = st
    else:
        iso = st.replace(' ', 'T')
    
    if not (iso.endswith('Z') or '+' in iso[-6:] or '-' in iso[-6:]):
        iso += 'Z'
    
    try:
        # replace Z with +00:00 for fromisoformat
        if iso.endswith('Z'):
            iso = iso[:-1] + '+00:00'
        return datetime.fromisoformat(iso).astimezone(timezone.utc)
    except Exception:
        return None

def to_utc_string(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

def next_occurrence(reminder_at: Optional[str], repeat: Optional[str], tz_name: Optional[str] = None, from_dt: Optional[datetime] = None) -> Optional[datetime]:
    anchor = parse_utc(reminder_at)
    if not anchor:
        return None
    if repeat not in REPEATS:
        return anchor
    
    now = from_dt or datetime.now(timezone.utc)
    if anchor > now:
        return anchor
    
    try:
        zone = ZoneInfo(tz_name) if tz_name else timezone.utc
    except Exception:
        zone = timezone.utc
        
    anchor_local = anchor.astimezone(zone)
    now_local = now.astimezone(zone)
    
    h = anchor_local.hour
    m = anchor_local.minute
    s = anchor_local.second

    if repeat == 'daily':
        # Today at target time
        cand = now_local.replace(hour=h, minute=m, second=s, microsecond=0)
        while cand.astimezone(timezone.utc) <= now:
            cand += timedelta(days=1)
        return cand.astimezone(timezone.utc)
        
    elif repeat == 'weekly':
        target_dow = anchor_local.weekday()
        current_dow = now_local.weekday()
        delta_days = (target_dow - current_dow) % 7
        cand = (now_local + timedelta(days=delta_days)).replace(hour=h, minute=m, second=s, microsecond=0)
        if cand.astimezone(timezone.utc) <= now:
            cand += timedelta(days=7)
        return cand.astimezone(timezone.utc)
        
    elif repeat == 'monthly':
        y = now_local.year
        mo = now_local.month
        target_day = anchor_local.day
        max_d = calendar.monthrange(y, mo)[1]
        cand = datetime(y, mo, min(target_day, max_d), h, m, s, tzinfo=zone)
        if cand.astimezone(timezone.utc) <= now:
            mo += 1
            if mo > 12:
                mo = 1
                y += 1
            max_d = calendar.monthrange(y, mo)[1]
            cand = datetime(y, mo, min(target_day, max_d), h, m, s, tzinfo=zone)
        return cand.astimezone(timezone.utc)
        
    elif repeat == 'yearly':
        y = now_local.year
        mo = anchor_local.month
        target_day = anchor_local.day
        max_d = calendar.monthrange(y, mo)[1]
        cand = datetime(y, mo, min(target_day, max_d), h, m, s, tzinfo=zone)
        if cand.astimezone(timezone.utc) <= now:
            y += 1
            max_d = calendar.monthrange(y, mo)[1]
            cand = datetime(y, mo, min(target_day, max_d), h, m, s, tzinfo=zone)
        return cand.astimezone(timezone.utc)

    return anchor

def due_occurrence(note: Dict[str, Any], now: Optional[datetime] = None, window_ms: int = LATE_WINDOW_MS) -> Optional[datetime]:
    now_dt = now or datetime.now(timezone.utc)
    from_dt = now_dt - timedelta(milliseconds=window_ms)
    occ = next_occurrence(note.get("reminder_at"), note.get("reminder_rrule"), note.get("reminder_tz"), from_dt)
    if not occ:
        return None
    age_ms = (now_dt - occ).total_seconds() * 1000
    if 0 <= age_ms <= window_ms:
        return occ
    return None
