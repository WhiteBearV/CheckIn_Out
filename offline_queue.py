"""
offline_queue.py — SQLite-backed buffer สำหรับ Offline Mode (Phase 2 A+B)
=========================================================================
รับมือ 2 scenarios:
  A. Internet ดับ  → External API (employee identity) เรียกไม่ได้ → ดึงจาก employee_cache
  B. Local PG ดับ → api.py เรียกไม่ได้ / 5xx → buffer ใน attendance_buf, sync_worker จะ replay

Schema:
  attendance_buf  — ทุก mark_attendance event (synced=0 = ยังไม่ถึง PG, queue + UI cache)
  employee_cache  — pre-warmed identity lookup (refresh ทุก 1 ชม. โดย sync_worker)
  sync_state      — KV เก็บสถานะ worker (PG health, last sync timestamp, pending count)

Concurrency:
  SQLite WAL mode → multi-process safe (stream_server + api.py + main.py อ่าน/เขียนพร้อมกันได้)
  ทุก connection ใช้ context manager เพื่อปิดให้แน่นอน

Path:
  default = ./offline_queue.db (relative to cwd)
  override ผ่าน env OFFLINE_QUEUE_PATH
"""

import json
import os
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime
from typing import Any, Optional

# ─── ค่าตั้งต้น ────────────────────────────────────────────────────────────────

DB_PATH = os.environ.get("OFFLINE_QUEUE_PATH", "./offline_queue.db")

# ─── Schema ──────────────────────────────────────────────────────────────────

_SCHEMA = """
CREATE TABLE IF NOT EXISTS attendance_buf (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    per_id       TEXT NOT NULL,
    status       TEXT NOT NULL CHECK (status IN ('IN', 'OUT')),
    camera_name  TEXT,
    check_time   TEXT NOT NULL,
    name         TEXT,
    prename_th   TEXT,
    per_name     TEXT,
    per_surname  TEXT,
    posname_th   TEXT,
    organize_th  TEXT,
    organize_id  TEXT,
    synced       INTEGER NOT NULL DEFAULT 0,
    created_at   TEXT NOT NULL DEFAULT (datetime('now')),
    synced_at    TEXT,
    last_error   TEXT,
    retry_count  INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_buf_pending
    ON attendance_buf(synced, created_at);

CREATE INDEX IF NOT EXISTS idx_buf_perid_date
    ON attendance_buf(per_id, check_time);

CREATE UNIQUE INDEX IF NOT EXISTS idx_buf_dedup
    ON attendance_buf(per_id, status, date(check_time));

CREATE TABLE IF NOT EXISTS employee_cache (
    per_id      TEXT PRIMARY KEY,
    payload     TEXT NOT NULL,
    cached_at   TEXT NOT NULL DEFAULT (datetime('now')),
    expires_at  TEXT
);

CREATE TABLE IF NOT EXISTS sync_state (
    key         TEXT PRIMARY KEY,
    value       TEXT,
    updated_at  TEXT NOT NULL DEFAULT (datetime('now'))
);
"""

# ─── Connection helpers ───────────────────────────────────────────────────────

_init_lock = threading.Lock()
_initialized = False


def _connect(path: str = None) -> sqlite3.Connection:
    """เปิด connection พร้อม WAL + foreign_keys + busy_timeout"""
    conn = sqlite3.connect(path or DB_PATH, timeout=10.0, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


def init_db(path: str = None) -> None:
    """สร้าง tables (idempotent) — เรียกครั้งเดียวตอน boot"""
    global _initialized
    with _init_lock:
        if _initialized and path is None:
            return
        with _connect(path) as conn:
            conn.executescript(_SCHEMA)
        if path is None:
            _initialized = True


@contextmanager
def get_conn(path: str = None):
    """context manager — ensure init แล้วคืน connection"""
    if not _initialized and path is None:
        init_db()
    conn = _connect(path)
    try:
        yield conn
    finally:
        conn.close()


# ─── attendance_buf operations ─────────────────────────────────────────────────

def enqueue_attendance(per_id: str, status: str, camera_name: Optional[str],
                       check_time: datetime, *, name: Optional[str] = None,
                       prename_th: Optional[str] = None,
                       per_name: Optional[str] = None,
                       per_surname: Optional[str] = None,
                       posname_th: Optional[str] = None,
                       organize_th: Optional[str] = None,
                       organize_id: Optional[str] = None,
                       synced: bool = False,
                       conn: Optional[sqlite3.Connection] = None) -> Optional[int]:
    """
    INSERT attendance event เข้า buffer (idempotent ด้วย UNIQUE index per_id/status/date).
    คืน id ของแถวที่เพิ่ม หรือ None ถ้าซ้ำ (dedup index reject).

    เรียกได้ทั้ง online (PG ก็ INSERT, mark synced=True ตอน success)
    และ offline (PG ดับ — synced=False, sync_worker จะ drain ทีหลัง)
    """
    if status not in ("IN", "OUT"):
        raise ValueError(f"status ต้องเป็น 'IN' หรือ 'OUT' ไม่ใช่ {status!r}")
    ct = check_time.isoformat(timespec='seconds') if isinstance(check_time, datetime) \
         else str(check_time)
    synced_int = 1 if synced else 0
    synced_at = datetime.now().isoformat(timespec='seconds') if synced else None

    sql = """
        INSERT OR IGNORE INTO attendance_buf
            (per_id, status, camera_name, check_time,
             name, prename_th, per_name, per_surname,
             posname_th, organize_th, organize_id,
             synced, synced_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """
    params = (per_id, status, camera_name, ct,
              name, prename_th, per_name, per_surname,
              posname_th, organize_th, organize_id,
              synced_int, synced_at)

    if conn is not None:
        cur = conn.execute(sql, params)
        return cur.lastrowid if cur.rowcount else None

    with get_conn() as c:
        cur = c.execute(sql, params)
        return cur.lastrowid if cur.rowcount else None


def mark_synced(buf_id: int, *, conn: Optional[sqlite3.Connection] = None) -> None:
    """sync_worker เรียกหลัง POST /attendance สำเร็จ"""
    sql = ("UPDATE attendance_buf "
           "SET synced=1, synced_at=datetime('now'), last_error=NULL "
           "WHERE id=?")
    if conn is not None:
        conn.execute(sql, (buf_id,))
    else:
        with get_conn() as c:
            c.execute(sql, (buf_id,))


def record_sync_failure(buf_id: int, error: str, *,
                        conn: Optional[sqlite3.Connection] = None) -> None:
    """sync_worker เรียกหลัง POST /attendance ล้มเหลว — bump retry_count + เก็บ error"""
    sql = ("UPDATE attendance_buf "
           "SET retry_count = retry_count + 1, last_error = ? "
           "WHERE id = ?")
    if conn is not None:
        conn.execute(sql, (error[:500], buf_id))
    else:
        with get_conn() as c:
            c.execute(sql, (error[:500], buf_id))


def list_pending(limit: int = 50) -> list[sqlite3.Row]:
    """ดึง events ที่ยังไม่ sync (oldest first) — sync_worker เรียกทุก tick"""
    with get_conn() as c:
        rows = c.execute(
            "SELECT * FROM attendance_buf "
            "WHERE synced = 0 "
            "ORDER BY created_at ASC LIMIT ?",
            (limit,),
        ).fetchall()
        return list(rows)


def list_today(only_synced: bool = False) -> list[sqlite3.Row]:
    """ดึง attendance วันนี้ (สำหรับ UI fallback ตอน PG ดับ)"""
    sql = ("SELECT * FROM attendance_buf "
           "WHERE date(check_time) = date('now', 'localtime') ")
    if only_synced:
        sql += "AND synced = 1 "
    sql += "ORDER BY check_time DESC"
    with get_conn() as c:
        return list(c.execute(sql).fetchall())


def pending_count() -> int:
    with get_conn() as c:
        row = c.execute("SELECT COUNT(*) FROM attendance_buf WHERE synced=0").fetchone()
        return int(row[0])


def purge_old_synced(keep_days: int = 30) -> int:
    """ลบ records ที่ synced=1 และเก่ากว่า N วัน (เรียกเป็นครั้งคราว — เลี่ยง bloat)"""
    with get_conn() as c:
        cur = c.execute(
            "DELETE FROM attendance_buf "
            "WHERE synced = 1 "
            "AND created_at < datetime('now', ?)",
            (f'-{keep_days} days',),
        )
        return cur.rowcount


# ─── employee_cache operations ─────────────────────────────────────────────────

def cache_employee(per_id: str, payload: dict, *,
                   ttl_hours: Optional[int] = None) -> None:
    """upsert — ใช้ตอน fetch_person_by_pid สำเร็จ ใน online mode"""
    expires_at = None
    if ttl_hours is not None:
        from datetime import timedelta
        expires_at = (datetime.now() + timedelta(hours=ttl_hours)).isoformat(timespec='seconds')
    with get_conn() as c:
        c.execute(
            "INSERT INTO employee_cache (per_id, payload, cached_at, expires_at) "
            "VALUES (?, ?, datetime('now'), ?) "
            "ON CONFLICT(per_id) DO UPDATE SET "
            "  payload=excluded.payload, "
            "  cached_at=excluded.cached_at, "
            "  expires_at=excluded.expires_at",
            (per_id, json.dumps(payload, ensure_ascii=False), expires_at),
        )


def get_cached_employee(per_id: str, *,
                        allow_expired: bool = True) -> Optional[dict]:
    """ดึงจาก cache — allow_expired=True (default) เพราะ offline mode ยอมรับข้อมูลเก่าได้
    (ดีกว่าไม่มีข้อมูลเลย)"""
    with get_conn() as c:
        row = c.execute(
            "SELECT payload, expires_at FROM employee_cache WHERE per_id = ?",
            (per_id,),
        ).fetchone()
        if not row:
            return None
        if not allow_expired and row['expires_at']:
            if row['expires_at'] < datetime.now().isoformat(timespec='seconds'):
                return None
        try:
            return json.loads(row['payload'])
        except json.JSONDecodeError:
            return None


def all_cached_employee_ids() -> list[str]:
    with get_conn() as c:
        return [r[0] for r in c.execute("SELECT per_id FROM employee_cache")]


# ─── sync_state KV ─────────────────────────────────────────────────────────────

def set_state(key: str, value: Any) -> None:
    """เก็บ KV state — value แปลงเป็น JSON string อัตโนมัติถ้าเป็น dict/list/bool/number"""
    if not isinstance(value, str):
        value = json.dumps(value, ensure_ascii=False, default=str)
    with get_conn() as c:
        c.execute(
            "INSERT INTO sync_state (key, value, updated_at) "
            "VALUES (?, ?, datetime('now')) "
            "ON CONFLICT(key) DO UPDATE SET "
            "  value=excluded.value, updated_at=excluded.updated_at",
            (key, value),
        )


def get_state(key: str, default: Any = None) -> Any:
    """ดึง KV — พยายาม parse JSON, ถ้า parse ไม่ได้คืน raw string"""
    with get_conn() as c:
        row = c.execute("SELECT value FROM sync_state WHERE key = ?", (key,)).fetchone()
        if row is None:
            return default
        try:
            return json.loads(row['value'])
        except (json.JSONDecodeError, TypeError):
            return row['value']


def get_all_state() -> dict:
    """ดึง KV ทั้งหมด — สำหรับ /system/offline endpoint"""
    out = {}
    with get_conn() as c:
        for row in c.execute("SELECT key, value, updated_at FROM sync_state"):
            try:
                out[row['key']] = json.loads(row['value'])
            except (json.JSONDecodeError, TypeError):
                out[row['key']] = row['value']
    return out
