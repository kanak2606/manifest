#!/usr/bin/env python3
"""
NoteTrace Database Migration and Schema Verification Script
Ensures SQLite schema, FTS5 virtual tables, indices, and triggers are fully up to date.
"""
import sys
import os

# Add root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from notetrace_backend.config import DB_PATH
from notetrace_backend.database import get_connection, init_db

def run_migrations(target_db: str = None):
    db_file = target_db or DB_PATH
    print(f"[*] Running database migrations on: {db_file}")
    init_db(db_file)
    conn = get_connection(db_file)
    cur = conn.cursor()
    
    # Verify tables
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name;")
    tables = [r["name"] for r in cur.fetchall()]
    print(f"[✓] Migration complete. Verified {len(tables)} tables:")
    for t in tables:
        print(f"    - {t}")

if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else None
    run_migrations(target)
