import sqlite3
import os
import threading
from contextlib import contextmanager
from typing import Any, Dict, List, Optional
from .config import DB_PATH

_local = threading.local()
_db_lock = threading.RLock()

def get_connection(db_file: Optional[str] = None) -> sqlite3.Connection:
    target = db_file or DB_PATH
    if not hasattr(_local, "connections"):
        _local.connections = {}
    
    if target not in _local.connections:
        conn = sqlite3.connect(target, timeout=30.0, check_same_thread=False, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode = WAL;")
        conn.execute("PRAGMA foreign_keys = ON;")
        conn.execute("PRAGMA busy_timeout = 30000;")
        _local.connections[target] = conn
    
    return _local.connections[target]

def clear_all_tables():
    """Wipes all rows from all tables for test isolation."""
    tables = [
        "habit_logs", "body_metrics", "habits", "focus_sessions",
        "note_members", "note_labels", "note_attachments", "checklist_items",
        "note_versions", "notes_fts", "notes", "labels", "user_settings",
        "api_tokens", "webhooks", "notification_log", "ai_chat_history",
        "app_config", "password_resets", "invite_tokens", "users"
    ]
    with transaction() as conn:
        for t in tables:
            try:
                conn.execute(f"DELETE FROM {t};")
            except Exception:
                pass

@contextmanager
def get_db():
    conn = get_connection()
    try:
        yield conn
    finally:
        pass

@contextmanager
def transaction():
    with _db_lock:
        conn = get_connection()
        depth = getattr(_local, "trans_depth", 0)
        _local.trans_depth = depth + 1
        if depth == 0:
            conn.execute("BEGIN IMMEDIATE;")
        else:
            conn.execute(f"SAVEPOINT sp_{depth};")
        try:
            yield conn
            if depth == 0:
                conn.commit()
            else:
                conn.execute(f"RELEASE SAVEPOINT sp_{depth};")
        except Exception:
            if depth == 0:
                try:
                    conn.rollback()
                except Exception:
                    pass
            else:
                try:
                    conn.execute(f"ROLLBACK TO SAVEPOINT sp_{depth};")
                except Exception:
                    pass
            raise
        finally:
            _local.trans_depth = depth

def query_one(sql: str, params: Any = ()) -> Optional[Dict[str, Any]]:
    with _db_lock:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(sql, params)
        row = cur.fetchone()
        return dict(row) if row is not None else None

def query_all(sql: str, params: Any = ()) -> List[Dict[str, Any]]:
    with _db_lock:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(sql, params)
        return [dict(r) for r in cur.fetchall()]

def execute(sql: str, params: Any = ()) -> int:
    with _db_lock:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(sql, params)
        if getattr(_local, "trans_depth", 0) == 0:
            conn.commit()
        return cur.lastrowid

def execute_count(sql: str, params: Any = ()) -> int:
    with _db_lock:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(sql, params)
        if getattr(_local, "trans_depth", 0) == 0:
            conn.commit()
        return cur.rowcount

def column_exists(conn: sqlite3.Connection, table: str, col: str) -> bool:
    cur = conn.cursor()
    cur.execute(f"PRAGMA table_info({table})")
    return any(row["name"] == col for row in cur.fetchall())

def init_db(db_file: Optional[str] = None):
    """Initializes tables, indices, triggers, and idempotent column additions."""
    conn = get_connection(db_file)
    with _db_lock:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            username      TEXT UNIQUE NOT NULL,
            password_hash TEXT,
            full_name     TEXT,
            nickname      TEXT,
            birthday      TEXT,
            gender        TEXT,
            avatar_url    TEXT,
            role          TEXT NOT NULL DEFAULT 'user',
            email         TEXT,
            created_at    TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS user_settings (
            user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            key        TEXT NOT NULL,
            value      TEXT,
            updated_at TEXT DEFAULT (datetime('now')),
            deleted_at TEXT DEFAULT NULL,
            synced_at  TEXT,
            PRIMARY KEY (user_id, key)
        );

        CREATE TABLE IF NOT EXISTS app_config (
            key   TEXT PRIMARY KEY,
            value TEXT
        );

        CREATE TABLE IF NOT EXISTS password_reset_tokens (
            token      TEXT PRIMARY KEY,
            user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            expires_at TEXT NOT NULL,
            used       INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS invite_tokens (
            token      TEXT PRIMARY KEY,
            email      TEXT,
            role       TEXT NOT NULL DEFAULT 'user',
            created_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
            expires_at TEXT NOT NULL,
            used       INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS api_tokens (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id      INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            name         TEXT NOT NULL,
            token_hash   TEXT NOT NULL UNIQUE,
            scopes       TEXT NOT NULL DEFAULT '[]',
            expires_at   TEXT,
            last_used_at TEXT,
            created_at   TEXT NOT NULL DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_api_tokens_user ON api_tokens(user_id);
        CREATE INDEX IF NOT EXISTS idx_api_tokens_hash ON api_tokens(token_hash);

        CREATE TABLE IF NOT EXISTS webhooks (
            id                   INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id              INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            url                  TEXT NOT NULL,
            secret_encrypted     TEXT NOT NULL,
            events               TEXT NOT NULL DEFAULT '[]',
            enabled              INTEGER NOT NULL DEFAULT 1,
            last_delivery_at     TEXT,
            last_delivery_status TEXT,
            last_delivery_error  TEXT,
            created_at           TEXT NOT NULL DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_webhooks_user ON webhooks(user_id);

        CREATE TABLE IF NOT EXISTS ai_chat_history (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id    INTEGER REFERENCES users(id) ON DELETE CASCADE,
            role       TEXT NOT NULL,
            content    TEXT NOT NULL,
            client_key TEXT DEFAULT NULL,
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now')),
            synced_at  TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_ai_chat_history_user ON ai_chat_history(user_id, created_at);

        CREATE TABLE IF NOT EXISTS oauth_state (
            state       TEXT PRIMARY KEY,
            user_id     INTEGER,
            provider    TEXT NOT NULL,
            data        TEXT NOT NULL DEFAULT '{}',
            expires_at  TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS oidc_providers (
            id                            INTEGER PRIMARY KEY AUTOINCREMENT,
            issuer_url                    TEXT NOT NULL,
            client_id                     TEXT NOT NULL,
            client_secret                 TEXT,
            redirect_uris                 TEXT NOT NULL DEFAULT '[]',
            scope                         TEXT NOT NULL DEFAULT 'openid profile email',
            token_endpoint_auth_method    TEXT NOT NULL DEFAULT 'client_secret_post',
            response_types                TEXT NOT NULL DEFAULT '["code"]',
            id_token_signed_response_alg  TEXT NOT NULL DEFAULT 'RS256',
            userinfo_signed_response_alg  TEXT NOT NULL DEFAULT 'none',
            request_timeout_ms            INTEGER NOT NULL DEFAULT 30000,
            auto_register                 INTEGER NOT NULL DEFAULT 0,
            auto_link_verified_email      INTEGER NOT NULL DEFAULT 1,
            auto_register_new_users       INTEGER NOT NULL DEFAULT 0,
            admin_group_claim             TEXT,
            admin_group_value             TEXT,
            display_name                  TEXT,
            logo_url                      TEXT,
            is_active                     INTEGER NOT NULL DEFAULT 1,
            created_at                    TEXT DEFAULT (datetime('now')),
            updated_at                    TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS user_oidc_links (
            id                INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id           INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            oidc_provider_id  INTEGER NOT NULL REFERENCES oidc_providers(id) ON DELETE CASCADE,
            oidc_sub          TEXT NOT NULL,
            email_verified    INTEGER DEFAULT 0,
            last_login_at     TEXT,
            created_at        TEXT DEFAULT (datetime('now')),
            UNIQUE (oidc_provider_id, oidc_sub)
        );
        CREATE INDEX IF NOT EXISTS idx_user_oidc_links_user ON user_oidc_links(user_id);

        CREATE TABLE IF NOT EXISTS notes (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id        INTEGER REFERENCES users(id) ON DELETE CASCADE,
            title          TEXT NOT NULL DEFAULT '',
            body_md        TEXT NOT NULL DEFAULT '',
            kind           TEXT NOT NULL DEFAULT 'text',
            color          TEXT,
            pinned         INTEGER NOT NULL DEFAULT 0,
            archived       INTEGER NOT NULL DEFAULT 0,
            trashed_at     TEXT,
            reminder_at    TEXT,
            reminder_rrule TEXT,
            reminder_tz    TEXT,
            in_tasks       INTEGER NOT NULL DEFAULT 0,
            share_token    TEXT,
            client_key     TEXT DEFAULT NULL,
            synced_at      TEXT,
            created_at     TEXT DEFAULT (datetime('now')),
            updated_at     TEXT DEFAULT (datetime('now')),
            deleted_at     TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_notes_user    ON notes(user_id);
        CREATE INDEX IF NOT EXISTS idx_notes_updated ON notes(updated_at);
        CREATE INDEX IF NOT EXISTS idx_notes_deleted ON notes(deleted_at);
        CREATE UNIQUE INDEX IF NOT EXISTS idx_notes_share_token ON notes(share_token) WHERE share_token IS NOT NULL;

        CREATE TABLE IF NOT EXISTS checklist_items (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            uuid       TEXT NOT NULL UNIQUE,
            user_id    INTEGER REFERENCES users(id) ON DELETE CASCADE,
            note_id    INTEGER NOT NULL REFERENCES notes(id) ON DELETE CASCADE,
            text       TEXT NOT NULL DEFAULT '',
            checked    INTEGER NOT NULL DEFAULT 0,
            position   REAL NOT NULL DEFAULT 0,
            due_date   TEXT,
            due_repeat TEXT,
            checked_at TEXT,
            client_key TEXT DEFAULT NULL,
            synced_at  TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now')),
            deleted_at TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_items_note    ON checklist_items(note_id);
        CREATE INDEX IF NOT EXISTS idx_items_user    ON checklist_items(user_id);
        CREATE INDEX IF NOT EXISTS idx_items_updated ON checklist_items(updated_at);

        CREATE TABLE IF NOT EXISTS labels (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id    INTEGER REFERENCES users(id) ON DELETE CASCADE,
            name       TEXT NOT NULL,
            color      TEXT,
            icon       TEXT,
            position   INTEGER NOT NULL DEFAULT 0,
            client_key TEXT DEFAULT NULL,
            synced_at  TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now')),
            deleted_at TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_labels_user    ON labels(user_id);
        CREATE INDEX IF NOT EXISTS idx_labels_updated ON labels(updated_at);

        CREATE TABLE IF NOT EXISTS note_labels (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id    INTEGER REFERENCES users(id) ON DELETE CASCADE,
            note_id    INTEGER NOT NULL REFERENCES notes(id) ON DELETE CASCADE,
            label_id   INTEGER NOT NULL REFERENCES labels(id) ON DELETE CASCADE,
            client_key TEXT DEFAULT NULL,
            synced_at  TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now')),
            deleted_at TEXT,
            UNIQUE (note_id, label_id)
        );
        CREATE INDEX IF NOT EXISTS idx_note_labels_label   ON note_labels(label_id);
        CREATE INDEX IF NOT EXISTS idx_note_labels_updated ON note_labels(updated_at);

        CREATE TABLE IF NOT EXISTS note_versions (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            note_id    INTEGER NOT NULL REFERENCES notes(id) ON DELETE CASCADE,
            title      TEXT NOT NULL DEFAULT '',
            body_md    TEXT NOT NULL DEFAULT '',
            kind       TEXT NOT NULL DEFAULT 'text',
            items_json TEXT,
            reason     TEXT NOT NULL DEFAULT 'edit',
            created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_note_versions_note ON note_versions(note_id, created_at);

        CREATE TABLE IF NOT EXISTS note_members (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            note_id    INTEGER NOT NULL REFERENCES notes(id) ON DELETE CASCADE,
            user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            role       TEXT NOT NULL DEFAULT 'edit',
            pinned     INTEGER NOT NULL DEFAULT 0,
            archived   INTEGER NOT NULL DEFAULT 0,
            in_tasks   INTEGER NOT NULL DEFAULT 0,
            added_by   INTEGER REFERENCES users(id) ON DELETE SET NULL,
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (strftime('%Y-%m-%d %H:%M:%f', 'now')),
            deleted_at TEXT,
            UNIQUE (note_id, user_id)
        );
        CREATE INDEX IF NOT EXISTS idx_note_members_user ON note_members(user_id, deleted_at);

        CREATE TABLE IF NOT EXISTS note_attachments (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            uuid           TEXT NOT NULL UNIQUE,
            user_id        INTEGER REFERENCES users(id) ON DELETE CASCADE,
            note_id        INTEGER NOT NULL REFERENCES notes(id) ON DELETE CASCADE,
            url            TEXT NOT NULL DEFAULT '',
            mime           TEXT,
            width          INTEGER,
            height         INTEGER,
            position       REAL NOT NULL DEFAULT 0,
            duration_ms    INTEGER,
            waveform       TEXT,
            segments       TEXT,
            extracted_text TEXT,
            summary        TEXT,
            name           TEXT,
            size_bytes     INTEGER,
            preview_url    TEXT,
            drawing        TEXT,
            client_key     TEXT DEFAULT NULL,
            synced_at      TEXT,
            created_at     TEXT DEFAULT (datetime('now')),
            updated_at     TEXT DEFAULT (datetime('now')),
            deleted_at     TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_attachments_note ON note_attachments(note_id);

        CREATE TABLE IF NOT EXISTS notification_log (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id     INTEGER REFERENCES users(id) ON DELETE CASCADE,
            kind        TEXT NOT NULL,
            ref_id      INTEGER,
            fired_date  TEXT NOT NULL,
            fired_at    TEXT DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_notif_log_user ON notification_log(user_id);
        CREATE UNIQUE INDEX IF NOT EXISTS idx_notif_log_dedup ON notification_log(user_id, kind, ref_id, fired_date);

        CREATE TABLE IF NOT EXISTS link_previews (
            url         TEXT PRIMARY KEY,
            ok          INTEGER NOT NULL DEFAULT 0,
            title       TEXT,
            description TEXT,
            site        TEXT,
            image_url   TEXT,
            icon_url    TEXT,
            fetched_at  TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS focus_sessions (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id       INTEGER REFERENCES users(id) ON DELETE CASCADE,
            note_id       INTEGER REFERENCES notes(id) ON DELETE SET NULL,
            item_uuid     TEXT,
            session_type  TEXT NOT NULL DEFAULT 'focus',
            duration_min  INTEGER NOT NULL DEFAULT 25,
            actual_sec    INTEGER NOT NULL DEFAULT 0,
            status        TEXT NOT NULL DEFAULT 'completed',
            started_at    TEXT NOT NULL DEFAULT (datetime('now')),
            target_end_at TEXT,
            remaining_sec INTEGER,
            completed_at  TEXT,
            notes         TEXT,
            created_at    TEXT NOT NULL DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_focus_sessions_user   ON focus_sessions(user_id);
        CREATE INDEX IF NOT EXISTS idx_focus_sessions_note   ON focus_sessions(note_id);
        CREATE INDEX IF NOT EXISTS idx_focus_sessions_status ON focus_sessions(status);
        CREATE INDEX IF NOT EXISTS idx_focus_sessions_start  ON focus_sessions(started_at);

        CREATE TABLE IF NOT EXISTS habits (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id      INTEGER REFERENCES users(id) ON DELETE CASCADE,
            title        TEXT NOT NULL,
            icon         TEXT DEFAULT '⚡',
            color        TEXT DEFAULT '#10b981',
            kind         TEXT NOT NULL DEFAULT 'preset_choice',
            options_json TEXT NOT NULL DEFAULT '[]',
            target_count INTEGER NOT NULL DEFAULT 1,
            unit         TEXT DEFAULT NULL,
            position     INTEGER NOT NULL DEFAULT 0,
            archived     INTEGER NOT NULL DEFAULT 0,
            created_at   TEXT DEFAULT (datetime('now')),
            updated_at   TEXT DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_habits_user ON habits(user_id, archived, position);

        CREATE TABLE IF NOT EXISTS habit_logs (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            habit_id         INTEGER NOT NULL REFERENCES habits(id) ON DELETE CASCADE,
            user_id          INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            log_date         TEXT NOT NULL,
            status           TEXT NOT NULL DEFAULT 'yes',
            selected_options TEXT NOT NULL DEFAULT '[]',
            numeric_value    REAL DEFAULT NULL,
            notes            TEXT DEFAULT NULL,
            created_at       TEXT DEFAULT (datetime('now')),
            updated_at       TEXT DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_habit_logs_user_date ON habit_logs(user_id, log_date);
        CREATE INDEX IF NOT EXISTS idx_habit_logs_habit ON habit_logs(habit_id);

        CREATE TABLE IF NOT EXISTS body_metrics (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            metric_type TEXT NOT NULL DEFAULT 'weight',
            value       REAL NOT NULL,
            unit        TEXT NOT NULL DEFAULT 'kg',
            logged_at   TEXT NOT NULL DEFAULT (datetime('now')),
            notes       TEXT DEFAULT NULL,
            created_at  TEXT DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_body_metrics_user ON body_metrics(user_id, metric_type, logged_at);
        """)

        # FTS5 Virtual Table
        conn.executescript("""
        CREATE VIRTUAL TABLE IF NOT EXISTS notes_fts USING fts5(
            title, body, items, tokenize = 'unicode61 remove_diacritics 2'
        );
        """)

        # FTS Rebuild triggers covering title, body, checklist items, and attachment extracted_text
        refresh_trigger_body = """
            DELETE FROM notes_fts WHERE rowid = {note_id_expr};
            INSERT INTO notes_fts (rowid, title, body, items)
            SELECT n.id, n.title, n.body_md,
                   COALESCE((SELECT group_concat(ci.text, ' ') FROM checklist_items ci
                             WHERE ci.note_id = n.id AND ci.deleted_at IS NULL), '') || ' ' ||
                   COALESCE((SELECT group_concat(na.extracted_text, ' ') FROM note_attachments na
                             WHERE na.note_id = n.id AND na.deleted_at IS NULL AND na.extracted_text IS NOT NULL), '')
            FROM notes n WHERE n.id = {note_id_expr} AND n.deleted_at IS NULL;
        """

        conn.executescript(f"""
        DROP TRIGGER IF EXISTS trg_notes_fts_ins;
        DROP TRIGGER IF EXISTS trg_notes_fts_upd;
        DROP TRIGGER IF EXISTS trg_notes_fts_del;
        DROP TRIGGER IF EXISTS trg_items_fts_ins;
        DROP TRIGGER IF EXISTS trg_items_fts_upd;
        DROP TRIGGER IF EXISTS trg_items_fts_del;
        DROP TRIGGER IF EXISTS trg_attachments_fts_ins;
        DROP TRIGGER IF EXISTS trg_attachments_fts_upd;

        CREATE TRIGGER trg_notes_fts_ins AFTER INSERT ON notes BEGIN
            {refresh_trigger_body.format(note_id_expr='NEW.id')}
        END;

        CREATE TRIGGER trg_notes_fts_upd AFTER UPDATE OF title, body_md, deleted_at ON notes BEGIN
            {refresh_trigger_body.format(note_id_expr='NEW.id')}
        END;

        CREATE TRIGGER trg_notes_fts_del AFTER DELETE ON notes BEGIN
            DELETE FROM notes_fts WHERE rowid = OLD.id;
        END;

        CREATE TRIGGER trg_items_fts_ins AFTER INSERT ON checklist_items BEGIN
            {refresh_trigger_body.format(note_id_expr='NEW.note_id')}
        END;

        CREATE TRIGGER trg_items_fts_upd AFTER UPDATE OF text, note_id, deleted_at ON checklist_items BEGIN
            {refresh_trigger_body.format(note_id_expr='NEW.note_id')}
        END;

        CREATE TRIGGER trg_items_fts_del AFTER DELETE ON checklist_items BEGIN
            {refresh_trigger_body.format(note_id_expr='OLD.note_id')}
        END;

        CREATE TRIGGER trg_attachments_fts_ins AFTER INSERT ON note_attachments WHEN NEW.extracted_text IS NOT NULL BEGIN
            {refresh_trigger_body.format(note_id_expr='NEW.note_id')}
        END;

        CREATE TRIGGER trg_attachments_fts_upd AFTER UPDATE OF extracted_text, deleted_at ON note_attachments BEGIN
            {refresh_trigger_body.format(note_id_expr='NEW.note_id')}
        END;
        """)

        # Triggers for synced_at timestamps
        stamp_expr = "strftime('%Y-%m-%d %H:%M:%f', 'now')"
        for table in ['notes', 'labels', 'checklist_items', 'note_labels', 'note_attachments', 'ai_chat_history']:
            conn.executescript(f"""
            CREATE INDEX IF NOT EXISTS idx_{table}_synced ON {table}(synced_at);
            CREATE INDEX IF NOT EXISTS idx_{table}_client_key ON {table}(user_id, client_key);

            CREATE TRIGGER IF NOT EXISTS trg_{table}_synced_ins AFTER INSERT ON {table}
            BEGIN UPDATE {table} SET synced_at = {stamp_expr} WHERE id = NEW.id; END;

            CREATE TRIGGER IF NOT EXISTS trg_{table}_synced_upd AFTER UPDATE ON {table}
            BEGIN UPDATE {table} SET synced_at = {stamp_expr} WHERE id = NEW.id; END;
            """)

        conn.executescript(f"""
        CREATE TRIGGER IF NOT EXISTS trg_user_settings_synced_ins AFTER INSERT ON user_settings
        BEGIN UPDATE user_settings SET synced_at = {stamp_expr} WHERE user_id IS NEW.user_id AND key = NEW.key; END;

        CREATE TRIGGER IF NOT EXISTS trg_user_settings_synced_upd AFTER UPDATE ON user_settings
        BEGIN UPDATE user_settings SET synced_at = {stamp_expr} WHERE user_id IS NEW.user_id AND key = NEW.key; END;
        """)

        # Default seeds
        conn.execute("INSERT OR IGNORE INTO app_config (key, value) VALUES ('enable_email_password_login', '1');")

        # Migrate habit_logs if old UNIQUE constraint exists
        cur = conn.cursor()
        cur.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='habit_logs'")
        hl_row = cur.fetchone()
        if hl_row and hl_row[0] and "UNIQUE" in hl_row[0].upper():
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS habit_logs_temp (
                    id               INTEGER PRIMARY KEY AUTOINCREMENT,
                    habit_id         INTEGER NOT NULL REFERENCES habits(id) ON DELETE CASCADE,
                    user_id          INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    log_date         TEXT NOT NULL,
                    status           TEXT NOT NULL DEFAULT 'yes',
                    selected_options TEXT NOT NULL DEFAULT '[]',
                    numeric_value    REAL DEFAULT NULL,
                    notes            TEXT DEFAULT NULL,
                    created_at       TEXT DEFAULT (datetime('now')),
                    updated_at       TEXT DEFAULT (datetime('now'))
                );
                INSERT INTO habit_logs_temp (id, habit_id, user_id, log_date, status, selected_options, numeric_value, notes, created_at, updated_at)
                    SELECT id, habit_id, user_id, log_date, status, selected_options, numeric_value, notes, created_at, updated_at FROM habit_logs;
                DROP TABLE habit_logs;
                ALTER TABLE habit_logs_temp RENAME TO habit_logs;
                CREATE INDEX IF NOT EXISTS idx_habit_logs_user_date ON habit_logs(user_id, log_date);
                CREATE INDEX IF NOT EXISTS idx_habit_logs_habit ON habit_logs(habit_id);
            """)

        conn.commit()

def rebuild_fts_index(conn: Optional[sqlite3.Connection] = None):
    c = conn or get_connection()
    with _db_lock:
        c.executescript("""
        DELETE FROM notes_fts;
        INSERT INTO notes_fts (rowid, title, body, items)
        SELECT n.id, n.title, n.body_md,
               COALESCE((SELECT group_concat(ci.text, ' ') FROM checklist_items ci
                         WHERE ci.note_id = n.id AND ci.deleted_at IS NULL), '') || ' ' ||
               COALESCE((SELECT group_concat(na.extracted_text, ' ') FROM note_attachments na
                         WHERE na.note_id = n.id AND na.deleted_at IS NULL AND na.extracted_text IS NOT NULL), '')
        FROM notes n WHERE n.deleted_at IS NULL;
        """)
        c.commit()
