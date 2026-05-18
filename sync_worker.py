"""
sync_worker.py — daemon thread ที่ drain offline_queue + refresh employee_cache
================================================================================
ทุก SYNC_INTERVAL วินาที (default 30s):
  1. ดึง pending rows จาก attendance_buf (synced=0)
  2. POST ไป api.py /attendance ทีละแถว
       - success → mark_synced
       - PG dup ("วันนี้บันทึก ... แล้ว") → mark_synced (PG มีแล้ว)
       - rule reject (OUT ก่อน IN) → record_sync_failure + leave pending
       - network/5xx → record_sync_failure + bail tick (PG อาจดับยาว)
  3. update sync_state: last_pg_check, last_sync, pending_count

ทุก CACHE_REFRESH_INTERVAL (default 3600s = 1h):
  - สแกน known_faces/{per_id}/ → fetch_person_by_pid → upsert employee_cache

เริ่มจาก stream_server.py — start() ใน startup, stop() ใน shutdown
"""

import os
import threading
import time
import traceback
from datetime import datetime
from pathlib import Path
from typing import Optional

import requests

import offline_queue
import notify as _notify

# ─── ค่าตั้งต้น ────────────────────────────────────────────────────────────────

SYNC_INTERVAL          = float(os.environ.get("SYNC_WORKER_INTERVAL", "30"))
CACHE_REFRESH_INTERVAL = float(os.environ.get("EMPLOYEE_CACHE_REFRESH", "3600"))
BATCH_SIZE             = int(os.environ.get("SYNC_BATCH_SIZE", "50"))
LOCAL_API_URL          = os.environ.get("LOCAL_API_URL", "http://localhost:8000")
KNOWN_FACES_DIR        = Path(os.environ.get("KNOWN_FACES_DIR", "./known_faces"))
HEALTH_TIMEOUT         = 3
POST_TIMEOUT           = 5

# ─── module state ─────────────────────────────────────────────────────────────

_thread: Optional[threading.Thread] = None
_stop_event = threading.Event()
_last_cache_refresh_ts = 0.0
_last_pg_ok: Optional[bool] = None  # ติดตามสถานะ PG เพื่อส่ง notify เมื่อเปลี่ยน


# ─── lifecycle ────────────────────────────────────────────────────────────────

def start() -> bool:
    """Spawn daemon thread (no-op if running). คืน True ถ้า start จริง"""
    global _thread, _last_cache_refresh_ts
    if _thread is not None and _thread.is_alive():
        return False
    _stop_event.clear()
    _last_cache_refresh_ts = 0.0  # ให้ refresh ครั้งแรก trigger เลย
    _thread = threading.Thread(target=_loop, daemon=True, name="sync_worker")
    _thread.start()
    print(f"[SYNC WORKER] เริ่มทำงาน "
          f"(interval={SYNC_INTERVAL}s, cache_refresh={CACHE_REFRESH_INTERVAL}s, "
          f"batch={BATCH_SIZE})")
    return True


def stop(timeout: float = 5.0) -> None:
    """ส่ง stop signal + รอ thread จบ (best-effort, daemon thread ไม่ block exit)"""
    _stop_event.set()
    t = _thread
    if t is not None and t.is_alive():
        t.join(timeout=timeout)


def is_running() -> bool:
    return _thread is not None and _thread.is_alive()


# ─── main loop ────────────────────────────────────────────────────────────────

def _loop() -> None:
    try:
        offline_queue.init_db()
    except Exception as e:
        print(f"[SYNC WORKER] init_db failed: {e}")
        return
    # tick first พอจริงๆ — ไม่รอ SYNC_INTERVAL ก่อน
    while True:
        try:
            _tick()
        except Exception as e:
            print(f"[SYNC WORKER] tick error: {e}\n{traceback.format_exc()}")
            try:
                offline_queue.set_state("last_error",
                                        f"{datetime.now().isoformat(timespec='seconds')} {e}")
            except Exception:
                pass
        if _stop_event.wait(SYNC_INTERVAL):
            print("[SYNC WORKER] หยุดทำงานตามคำสั่ง")
            return


def _notify_pg_state(pg_ok: bool) -> None:
    """ส่ง notify เมื่อสถานะ PG เปลี่ยน (down→up หรือ up→down) เท่านั้น"""
    global _last_pg_ok
    if _last_pg_ok is None:
        _last_pg_ok = pg_ok
        return
    if not pg_ok and _last_pg_ok:
        _notify.pg_down()
    elif pg_ok and not _last_pg_ok:
        _notify.pg_recovered()
    _last_pg_ok = pg_ok


def _tick() -> None:
    """หนึ่งรอบการทำงาน — drain pending + (เป็นครั้งคราว) refresh cache"""
    now = time.time()
    pending_total = offline_queue.pending_count()
    offline_queue.set_state("pending_count", pending_total)

    if pending_total > 0:
        _drain_pending()
    else:
        # ไม่มีงาน — แค่ probe PG health เพื่อให้ UI badge สด
        pg_ok = _probe_pg()
        offline_queue.set_state("last_pg_check", {
            "ok": pg_ok,
            "ts": datetime.now().isoformat(timespec='seconds'),
        })
        _notify_pg_state(pg_ok)

    # employee cache refresh
    global _last_cache_refresh_ts
    if now - _last_cache_refresh_ts > CACHE_REFRESH_INTERVAL:
        _refresh_employee_cache()
        _last_cache_refresh_ts = now


# ─── drain ────────────────────────────────────────────────────────────────────

def _drain_pending() -> None:
    pending = offline_queue.list_pending(limit=BATCH_SIZE)
    drained = 0
    transient_failed = 0
    permanent_failed = 0
    for row in pending:
        outcome = _push_row(row)
        if outcome == "synced":
            drained += 1
        elif outcome == "transient":
            transient_failed += 1
            # PG ยังไม่ขึ้น → ไม่ต้องเสียเวลาลอง row ต่อ ๆ ไป
            break
        else:  # "permanent"
            permanent_failed += 1
            # rule reject (เช่น OUT ก่อน IN) — ลอง row ต่อไปได้

    offline_queue.set_state("last_sync", {
        "ts": datetime.now().isoformat(timespec='seconds'),
        "drained": drained,
        "transient_failed": transient_failed,
        "permanent_failed": permanent_failed,
        "pending_after": offline_queue.pending_count(),
    })
    pg_ok = drained > 0 or (transient_failed == 0 and permanent_failed > 0)
    offline_queue.set_state("last_pg_check", {
        "ok": pg_ok,
        "ts": datetime.now().isoformat(timespec='seconds'),
    })
    _notify_pg_state(pg_ok)
    if drained or transient_failed or permanent_failed:
        print(f"[SYNC WORKER] drained={drained} transient={transient_failed} "
              f"permanent={permanent_failed} (pending_after={offline_queue.pending_count()})")


def _push_row(row) -> str:
    """
    ส่ง 1 row ไป PG. คืน:
        "synced"    — บันทึกแล้ว / PG มีอยู่แล้ว → marked synced
        "transient" — network/5xx — PG อาจดับ
        "permanent" — rule reject — leave for retry แต่ row ต่อ ๆ ไปยังลองได้
    """
    payload = {
        "per_id":      row['per_id'],
        "status":      row['status'],
        "camera_name": row['camera_name'],
        "check_time":  row['check_time'],
        "name":        row['name'],
        "prename_th":  row['prename_th'],
        "per_name":    row['per_name'],
        "per_surname": row['per_surname'],
        "posname_th":  row['posname_th'],
        "organize_th": row['organize_th'],
        "organize_id": row['organize_id'],
    }
    try:
        resp = requests.post(f"{LOCAL_API_URL}/attendance",
                             json=payload, timeout=POST_TIMEOUT)
        resp.raise_for_status()
        result = resp.json()
    except requests.RequestException as e:
        offline_queue.record_sync_failure(row['id'], str(e)[:200])
        return "transient"
    except Exception as e:
        offline_queue.record_sync_failure(row['id'], f"unexpected: {e}"[:200])
        return "permanent"

    if result.get("success"):
        offline_queue.mark_synced(row['id'])
        print(f"[SYNC WORKER] synced buf_id={row['id']} "
              f"({row['per_id']}, {row['status']})")
        return "synced"

    reason = result.get("reason") or ""
    if "วันนี้บันทึก" in reason:
        # PG มีอยู่แล้ว → ถือว่า sync แล้ว (drop จาก queue)
        offline_queue.mark_synced(row['id'])
        print(f"[SYNC WORKER] buf_id={row['id']} already in PG ({reason}) "
              f"— marked synced")
        return "synced"

    # OUT ก่อน IN หรือ rule อื่นๆ — เก็บไว้ลองใหม่ (IN อาจ replay มาทีหลัง)
    offline_queue.record_sync_failure(row['id'], reason[:200])
    print(f"[SYNC WORKER] buf_id={row['id']} rejected: {reason} "
          f"(retry={(row['retry_count'] or 0) + 1})")
    return "permanent"


# ─── PG probe ─────────────────────────────────────────────────────────────────

def _probe_pg() -> bool:
    """ping api.py /health — 200 + ok=true = PG พร้อม"""
    try:
        resp = requests.get(f"{LOCAL_API_URL}/health", timeout=HEALTH_TIMEOUT)
        return resp.status_code == 200 and resp.json().get("ok") is True
    except Exception:
        return False


# ─── employee_cache refresh ───────────────────────────────────────────────────

def _refresh_employee_cache() -> None:
    """walk known_faces/ → fetch_person_by_pid → upsert employee_cache"""
    if not KNOWN_FACES_DIR.exists():
        offline_queue.set_state("last_cache_refresh", {
            "ts": datetime.now().isoformat(timespec='seconds'),
            "error": f"known_faces dir not found: {KNOWN_FACES_DIR}",
        })
        return

    # circular-safe import (api_client imports offline_queue)
    from api_client import _real_fetch

    refreshed = 0
    failed = 0
    skipped = 0
    for sub in KNOWN_FACES_DIR.iterdir():
        if _stop_event.is_set():
            return
        if not sub.is_dir():
            continue
        per_id = sub.name
        if not per_id.isdigit():
            skipped += 1
            continue
        try:
            result = _real_fetch(per_id)
        except requests.RequestException:
            failed += 1
            continue
        except Exception:
            failed += 1
            continue
        if result is not None:
            try:
                offline_queue.cache_employee(per_id, result)
                refreshed += 1
            except Exception:
                failed += 1

    offline_queue.set_state("last_cache_refresh", {
        "ts": datetime.now().isoformat(timespec='seconds'),
        "refreshed": refreshed,
        "failed": failed,
        "skipped": skipped,
    })
    print(f"[SYNC WORKER] cache refresh: {refreshed} ok, {failed} failed, "
          f"{skipped} skipped")
