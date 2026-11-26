import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional

from .database import execute, query_all
from .notes_logic import purge_expired_trash
from .utils.reminders import due_occurrence
from .events import notify_update

logger = logging.getLogger("notetrace.scheduler")

_scheduler_task: Optional[asyncio.Task] = None

async def scheduler_tick():
    now_dt = datetime.now(timezone.utc)
    today_str = now_dt.strftime("%Y-%m-%d")

    # 1. Check due reminders
    notes_with_reminders = query_all(
        "SELECT id, user_id, title, reminder_at, reminder_rrule, reminder_tz FROM notes WHERE trashed_at IS NULL AND deleted_at IS NULL AND reminder_at IS NOT NULL"
    )
    for n in notes_with_reminders:
        occ = due_occurrence(n, now_dt)
        if occ:
            occ_str = occ.strftime("%Y-%m-%d %H:%M:%S")
            # Check if already notified
            exists = query_one(
                "SELECT 1 FROM notification_log WHERE user_id = ? AND kind = 'reminder' AND ref_id = ? AND fired_date = ?",
                (n.get("user_id"), n["id"], occ_str)
            )
            if not exists:
                execute(
                    "INSERT INTO notification_log (user_id, kind, ref_id, fired_date) VALUES (?, 'reminder', ?, ?)",
                    (n.get("user_id"), n["id"], occ_str)
                )
                logger.info(f"[scheduler] Reminder fired for note {n['id']}: {n['title']}")
                notify_update("reminder_fired", {"note_id": n["id"], "title": n["title"]})

    # 2. Daily cleanup tasks (trash purging)
    try:
        purge_expired_trash()
    except Exception as e:
        logger.warn(f"[scheduler] Trash purge error: {e}")

async def scheduler_loop():
    logger.info("[scheduler] Background scheduler started")
    while True:
        try:
            await scheduler_tick()
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"[scheduler] Error in tick: {e}")
        await asyncio.sleep(60)

def start_scheduler():
    global _scheduler_task
    if _scheduler_task is None or _scheduler_task.done():
        _scheduler_task = asyncio.create_task(scheduler_loop())

def stop_scheduler():
    global _scheduler_task
    if _scheduler_task and not _scheduler_task.done():
        _scheduler_task.cancel()
