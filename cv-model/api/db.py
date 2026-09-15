"""
Persistence.

SQLite for the pilot — zero setup, one file, adequate for a single company's
hiring volume. The schema deliberately mirrors what PostgreSQL would hold, so
moving to Postgres later is a connection-string change plus a migration, not
a redesign.

Everything a ranking produced is stored: the resolved requirements, the model
versions in effect, and the full per-candidate breakdown. That record IS the
audit trail — it is what lets someone reconstruct months later why a candidate
ranked where they did.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path
from typing import Any, Optional

DB_PATH = Path(__file__).parent.parent / "storage" / "app.db"
_lock = threading.Lock()

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    id                TEXT PRIMARY KEY,
    title             TEXT NOT NULL,
    status            TEXT NOT NULL,          -- draft|ready|processing|completed|failed
    created_at        TEXT NOT NULL,
    updated_at        TEXT NOT NULL,
    created_by        TEXT NOT NULL,
    version           INTEGER NOT NULL DEFAULT 1,
    top_n             INTEGER NOT NULL DEFAULT 10,

    jd_text           TEXT,
    jd_filename       TEXT,
    jd_profile_json   TEXT,                   -- extracted JobProfile
    manual_json       TEXT,                   -- manual requirement overrides
    skills_json       TEXT,                   -- required skills list

    progress_done     INTEGER NOT NULL DEFAULT 0,
    progress_total    INTEGER NOT NULL DEFAULT 0,
    progress_current  TEXT,

    results_json      TEXT,                   -- full ranking output
    failures_json     TEXT,
    versions_json     TEXT,                   -- model/engine versions for audit
    error             TEXT
);

CREATE TABLE IF NOT EXISTS audit_log (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    at         TEXT NOT NULL,
    actor      TEXT NOT NULL,
    action     TEXT NOT NULL,
    run_id     TEXT,
    detail     TEXT
);

-- Who may sign in. Both sign-in routes — email code and phone — check this
-- one table, so removing somebody's access is a single change that closes
-- every door at once.
CREATE TABLE IF NOT EXISTS allowed_users (
    email      TEXT PRIMARY KEY,
    phone      TEXT UNIQUE,
    name       TEXT NOT NULL,
    role       TEXT NOT NULL DEFAULT 'hr',   -- hr | admin
    -- Access is switched off, never deleted: past rankings name the person
    -- who ran them, and deleting the row would break that record.
    active     INTEGER NOT NULL DEFAULT 1,
    added_at   TEXT NOT NULL,
    added_by   TEXT,

    -- Empty until the person sets one. A new account signs in with an emailed
    -- code, chooses a password, and uses that from then on.
    password_hash   TEXT,
    password_set_at TEXT,
    -- Wrong-password attempts, and the time a lockout ends. Without these a
    -- password is guessable at whatever rate the network allows.
    failed_logins   INTEGER NOT NULL DEFAULT 0,
    locked_until    TEXT
);

-- Outstanding sign-in codes. The code itself is never stored, only a keyed
-- hash of it — see api/auth.py.
CREATE TABLE IF NOT EXISTS login_codes (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    email       TEXT NOT NULL,
    code_hash   TEXT NOT NULL,
    created_at  TEXT NOT NULL,
    expires_at  TEXT NOT NULL,
    attempts    INTEGER NOT NULL DEFAULT 0,
    used        INTEGER NOT NULL DEFAULT 0,
    -- The password chosen on the sign-in screen, held here until the code is
    -- verified. Writing it to the account straight away would let anybody set
    -- a password on somebody else's address just by typing it in.
    pending_password_hash TEXT
);

CREATE TABLE IF NOT EXISTS sessions (
    token_hash  TEXT PRIMARY KEY,
    email       TEXT NOT NULL,
    created_at  TEXT NOT NULL,
    expires_at  TEXT NOT NULL,
    last_seen   TEXT
);

CREATE INDEX IF NOT EXISTS idx_runs_created ON runs(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_audit_at ON audit_log(at DESC);
CREATE INDEX IF NOT EXISTS idx_codes_email ON login_codes(email, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_sessions_expiry ON sessions(expires_at);
"""


def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    # A ranking run writes progress from a background thread while the browser
    # polls for it. In WAL mode those can overlap; without a busy timeout the
    # reader raises "database is locked" instead of waiting a few milliseconds.
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


# One connection per thread, NOT one shared connection.
#
# This request path is genuinely concurrent: FastAPI serves sync endpoints on a
# worker thread while _execute_run writes progress from a background thread. A
# single sqlite3.Connection shared across threads interleaves their statements
# on the same underlying cursor, so a read issued while another thread is
# mid-write can come back empty — the browser then polls a run that was created
# a moment earlier and is told "Run not found", and the ranking appears to fail
# for no reason. Separate connections cannot interleave; WAL lets them read and
# write at the same time.
_local = threading.local()
_schema_ready = False
# Deliberately NOT _lock: get_db() is called from inside `with _lock` blocks,
# and a plain Lock is not reentrant, so reusing it here would deadlock the
# first write on a thread that has no connection yet.
_init_lock = threading.Lock()


# Columns added after the first version shipped. CREATE TABLE IF NOT EXISTS
# leaves an existing table alone, so a database made before passwords existed
# would keep working right up until the first query mentioning password_hash.
_ADDED_COLUMNS = [
    ("login_codes", "pending_password_hash", "TEXT"),
    ("allowed_users", "password_hash", "TEXT"),
    ("allowed_users", "password_set_at", "TEXT"),
    ("allowed_users", "failed_logins", "INTEGER NOT NULL DEFAULT 0"),
    ("allowed_users", "locked_until", "TEXT"),
]


def _migrate(conn: sqlite3.Connection) -> None:
    for table, column, decl in _ADDED_COLUMNS:
        existing = {r["name"] for r in conn.execute(f"PRAGMA table_info({table})")}
        if column not in existing:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {decl}")
    conn.commit()


def normalise_phone(phone: str) -> str:
    """Reduce a number to E.164-ish digits so stored and supplied forms match.

    People write the same number as 0300 1234567, +92 300 1234567 and
    92-300-1234567. The phone column is UNIQUE and is looked up by exact match,
    so the canonical form belongs here rather than in each caller: a number
    written in through some future script has to land in the same shape the
    sign-in path looks for, or a listed user is told they are not authorised.
    """
    raw = "".join(ch for ch in (phone or "") if ch.isdigit() or ch == "+")
    if raw.startswith("+"):
        return raw
    if raw.startswith("00"):
        return "+" + raw[2:]
    if raw.startswith("0"):          # local form, assume Pakistan
        return "+92" + raw[1:]
    if raw:
        return "+" + raw
    return ""


def get_db() -> sqlite3.Connection:
    global _schema_ready
    conn = getattr(_local, "conn", None)
    if conn is None:
        conn = _connect()
        _local.conn = conn
        if not _schema_ready:
            with _init_lock:
                if not _schema_ready:
                    conn.executescript(SCHEMA)
                    _migrate(conn)
                    conn.commit()
                    _schema_ready = True
    return conn


def _j(value: Any) -> Optional[str]:
    return json.dumps(value, ensure_ascii=False) if value is not None else None


def _u(text: Optional[str], default: Any = None) -> Any:
    if not text:
        return default
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return default


# ---------------------------------------------------------------------------


def upsert_run(run: dict[str, Any]) -> None:
    cols = [
        "id", "title", "status", "created_at", "updated_at", "created_by",
        "version", "top_n", "jd_text", "jd_filename", "jd_profile_json",
        "manual_json", "skills_json", "progress_done", "progress_total",
        "progress_current", "results_json", "failures_json", "versions_json",
        "error",
    ]
    values = [run.get(c) for c in cols]
    placeholders = ",".join("?" * len(cols))
    updates = ",".join(f"{c}=excluded.{c}" for c in cols if c != "id")
    with _lock:
        db = get_db()
        db.execute(
            f"INSERT INTO runs ({','.join(cols)}) VALUES ({placeholders}) "
            f"ON CONFLICT(id) DO UPDATE SET {updates}",
            values,
        )
        db.commit()


def update_run(run_id: str, **fields: Any) -> None:
    if not fields:
        return
    sets = ",".join(f"{k}=?" for k in fields)
    with _lock:
        db = get_db()
        db.execute(f"UPDATE runs SET {sets} WHERE id=?", [*fields.values(), run_id])
        db.commit()


def get_run(run_id: str) -> Optional[dict[str, Any]]:
    db = get_db()
    row = db.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone()
    return _row_to_run(row) if row else None


def list_runs(limit: int = 100) -> list[dict[str, Any]]:
    db = get_db()
    rows = db.execute(
        "SELECT * FROM runs ORDER BY created_at DESC LIMIT ?", (limit,)
    ).fetchall()
    return [_row_to_run(r) for r in rows]


def delete_run(run_id: str) -> None:
    with _lock:
        db = get_db()
        db.execute("DELETE FROM runs WHERE id=?", (run_id,))
        db.commit()


def _row_to_run(row: sqlite3.Row) -> dict[str, Any]:
    d = dict(row)
    d["jd_profile"] = _u(d.pop("jd_profile_json", None))
    d["manual_overrides"] = _u(d.pop("manual_json", None), {})
    d["required_skills"] = _u(d.pop("skills_json", None), [])
    d["results"] = _u(d.pop("results_json", None))
    d["failures"] = _u(d.pop("failures_json", None), [])
    d["versions"] = _u(d.pop("versions_json", None), {})
    return d


# ---------------------------------------------------------------------------


def log_audit(actor: str, action: str, run_id: str | None = None,
              detail: str | None = None) -> None:
    """Append-only. Never updated or deleted — that is the point of it."""
    import datetime as dt

    with _lock:
        db = get_db()
        db.execute(
            "INSERT INTO audit_log (at, actor, action, run_id, detail) VALUES (?,?,?,?,?)",
            (dt.datetime.now().isoformat(timespec="seconds"), actor, action, run_id, detail),
        )
        db.commit()


def list_audit(limit: int = 200) -> list[dict[str, Any]]:
    db = get_db()
    rows = db.execute(
        "SELECT * FROM audit_log ORDER BY id DESC LIMIT ?", (limit,)
    ).fetchall()
    return [dict(r) for r in rows]


def count_audit() -> int:
    """How many entries the log actually holds.

    `list_audit` returns a page, and a page with nothing to compare it against
    is indistinguishable from the whole record. An administrator looking at the
    two hundred most recent lines and believing that is everything is exactly
    the failure this log exists to prevent.
    """
    return int(get_db().execute("SELECT COUNT(*) AS n FROM audit_log").fetchone()["n"])


# ---------------------------------------------------------------------------
# Access control
# ---------------------------------------------------------------------------


def get_user(email: str) -> Optional[dict[str, Any]]:
    row = get_db().execute(
        "SELECT * FROM allowed_users WHERE email=?", (email.strip().lower(),)
    ).fetchone()
    return dict(row) if row else None


def get_user_by_phone(phone: str) -> Optional[dict[str, Any]]:
    """Look a user up by number, in whatever form the caller has it."""
    canonical = normalise_phone(phone)
    if not canonical:
        return None
    row = get_db().execute(
        "SELECT * FROM allowed_users WHERE phone=?", (canonical,)
    ).fetchone()
    return dict(row) if row else None


def list_users() -> list[dict[str, Any]]:
    rows = get_db().execute(
        "SELECT * FROM allowed_users ORDER BY active DESC, name"
    ).fetchall()
    return [dict(r) for r in rows]


def upsert_user(email: str, name: str, role: str = "hr",
                phone: Optional[str] = None, active: bool = True,
                added_by: Optional[str] = None) -> None:
    import datetime as dt

    email = email.strip().lower()
    phone = normalise_phone(phone) or None
    with _lock:
        db = get_db()
        db.execute(
            """INSERT INTO allowed_users (email, phone, name, role, active, added_at, added_by)
               VALUES (?,?,?,?,?,?,?)
               ON CONFLICT(email) DO UPDATE SET
                   phone=excluded.phone,
                   name=excluded.name,
                   role=excluded.role,
                   active=excluded.active""",
            (email, phone or None, name, role, 1 if active else 0,
             dt.datetime.now().isoformat(timespec="seconds"), added_by),
        )
        db.commit()


def set_user_active(email: str, active: bool) -> None:
    with _lock:
        db = get_db()
        db.execute("UPDATE allowed_users SET active=? WHERE email=?",
                   (1 if active else 0, email.strip().lower()))
        db.commit()


# --- sign-in codes ---------------------------------------------------------


def latest_code(email: str) -> Optional[dict[str, Any]]:
    row = get_db().execute(
        "SELECT * FROM login_codes WHERE email=? ORDER BY id DESC LIMIT 1",
        (email.strip().lower(),),
    ).fetchone()
    return dict(row) if row else None


def insert_code(email: str, code_hash: str, created_at: str, expires_at: str,
                pending_password_hash: Optional[str] = None) -> int:
    with _lock:
        db = get_db()
        cur = db.execute(
            "INSERT INTO login_codes (email, code_hash, created_at, expires_at,"
            " pending_password_hash) VALUES (?,?,?,?,?)",
            (email.strip().lower(), code_hash, created_at, expires_at,
             pending_password_hash),
        )
        db.commit()
        return int(cur.lastrowid)


def bump_code_attempts(code_id: int) -> None:
    with _lock:
        db = get_db()
        db.execute("UPDATE login_codes SET attempts = attempts + 1 WHERE id=?", (code_id,))
        db.commit()


def mark_code_used(code_id: int) -> None:
    with _lock:
        db = get_db()
        db.execute("UPDATE login_codes SET used=1 WHERE id=?", (code_id,))
        db.commit()


# --- sessions --------------------------------------------------------------


def create_session(token_hash: str, email: str, created_at: str, expires_at: str) -> None:
    with _lock:
        db = get_db()
        db.execute(
            "INSERT OR REPLACE INTO sessions (token_hash, email, created_at, expires_at, last_seen)"
            " VALUES (?,?,?,?,?)",
            (token_hash, email.strip().lower(), created_at, expires_at, created_at),
        )
        db.commit()


def get_session(token_hash: str) -> Optional[dict[str, Any]]:
    row = get_db().execute(
        "SELECT * FROM sessions WHERE token_hash=?", (token_hash,)
    ).fetchone()
    return dict(row) if row else None


def touch_session(token_hash: str, at: str) -> None:
    with _lock:
        db = get_db()
        db.execute("UPDATE sessions SET last_seen=? WHERE token_hash=?", (at, token_hash))
        db.commit()


def delete_session(token_hash: str) -> None:
    with _lock:
        db = get_db()
        db.execute("DELETE FROM sessions WHERE token_hash=?", (token_hash,))
        db.commit()


def delete_sessions_for(email: str) -> None:
    """Used when access is withdrawn: an existing session must stop working
    immediately, not linger until it happens to expire."""
    with _lock:
        db = get_db()
        db.execute("DELETE FROM sessions WHERE email=?", (email.strip().lower(),))
        db.commit()


def purge_expired(now: str) -> None:
    with _lock:
        db = get_db()
        db.execute("DELETE FROM sessions WHERE expires_at < ?", (now,))
        db.execute("DELETE FROM login_codes WHERE expires_at < ?", (now,))
        db.commit()


# --- passwords -------------------------------------------------------------


def set_password_hash(email: str, password_hash: Optional[str], at: Optional[str]) -> None:
    """Store (or clear) a password. Clearing sends the user back through the
    emailed-code route, which is how an administrator resets somebody."""
    with _lock:
        db = get_db()
        db.execute(
            "UPDATE allowed_users SET password_hash=?, password_set_at=?,"
            " failed_logins=0, locked_until=NULL WHERE email=?",
            (password_hash, at, email.strip().lower()),
        )
        db.commit()


def record_failed_login(email: str, locked_until: Optional[str]) -> int:
    """Count a wrong password, and lock the account if told to. Returns the
    new count."""
    with _lock:
        db = get_db()
        db.execute(
            "UPDATE allowed_users SET failed_logins = failed_logins + 1,"
            " locked_until = COALESCE(?, locked_until) WHERE email=?",
            (locked_until, email.strip().lower()),
        )
        db.commit()
        row = db.execute(
            "SELECT failed_logins FROM allowed_users WHERE email=?",
            (email.strip().lower(),),
        ).fetchone()
        return int(row["failed_logins"]) if row else 0


def clear_failed_logins(email: str) -> None:
    with _lock:
        db = get_db()
        db.execute(
            "UPDATE allowed_users SET failed_logins=0, locked_until=NULL WHERE email=?",
            (email.strip().lower(),),
        )
        db.commit()
