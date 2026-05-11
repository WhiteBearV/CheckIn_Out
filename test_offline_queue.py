"""
test_offline_queue.py — smoke test offline_queue.py
ใช้ tmp DB ต่อ test เพื่อไม่กระทบ ./offline_queue.db จริง
รัน: venv/bin/python test_offline_queue.py
"""
import os
import sys
import tempfile
from datetime import datetime, timedelta

# isolate from production DB
_tmpdir = tempfile.mkdtemp(prefix="offline_q_test_")
_tmp_db = os.path.join(_tmpdir, "test.db")
os.environ["OFFLINE_QUEUE_PATH"] = _tmp_db

import offline_queue as q

# force re-init pointing at tmp
q.DB_PATH = _tmp_db
q._initialized = False
q.init_db()


def assert_eq(actual, expected, label):
    if actual != expected:
        print(f"  ✗ {label}: expected {expected!r}, got {actual!r}")
        return False
    print(f"  ✓ {label}")
    return True


def test_enqueue_and_dedup():
    print("\n[TEST] enqueue + dedup")
    now = datetime.now()
    id1 = q.enqueue_attendance("1111111111111", "IN", "cam1", now,
                               name="Test User", per_name="Test")
    ok = assert_eq(id1 is not None, True, "first INSERT returns id")

    # ซ้ำ — ควรถูก reject ด้วย UNIQUE(per_id, status, date(check_time))
    id2 = q.enqueue_attendance("1111111111111", "IN", "cam1", now + timedelta(minutes=5))
    ok &= assert_eq(id2, None, "duplicate (per_id, IN, today) → None")

    # OUT ของคนเดียวกันวันนี้ — ต้องผ่าน
    id3 = q.enqueue_attendance("1111111111111", "OUT", "cam1", now + timedelta(hours=1))
    ok &= assert_eq(id3 is not None, True, "different status (OUT) → new row")

    # คนละคน — ต้องผ่าน
    id4 = q.enqueue_attendance("2222222222222", "IN", "cam2", now)
    ok &= assert_eq(id4 is not None, True, "different per_id → new row")

    return ok


def test_list_pending_and_mark_synced():
    print("\n[TEST] list_pending + mark_synced")
    pending = q.list_pending(limit=10)
    ok = assert_eq(len(pending) >= 3, True, f"≥3 pending rows (got {len(pending)})")

    # mark แถวแรก synced
    first_id = pending[0]['id']
    q.mark_synced(first_id)
    pending2 = q.list_pending(limit=10)
    ok &= assert_eq(len(pending2), len(pending) - 1, "pending count -1 after mark_synced")

    # ลอง count pending ตรงๆ
    pc = q.pending_count()
    ok &= assert_eq(pc, len(pending2), "pending_count() ตรงกับ list_pending")
    return ok


def test_record_sync_failure():
    print("\n[TEST] record_sync_failure")
    pending = q.list_pending(limit=1)
    if not pending:
        print("  ✗ no pending to test")
        return False
    target = pending[0]['id']
    q.record_sync_failure(target, "connection refused")
    q.record_sync_failure(target, "connection refused")

    with q.get_conn() as c:
        row = c.execute("SELECT retry_count, last_error FROM attendance_buf WHERE id=?",
                        (target,)).fetchone()
        ok = assert_eq(row['retry_count'], 2, "retry_count == 2")
        ok &= assert_eq(row['last_error'], "connection refused", "last_error stored")
    return ok


def test_employee_cache():
    print("\n[TEST] employee_cache")
    payload = {"per_id": "9999999999999", "name": "วีรภัทร สวัดดี",
               "per_name": "วีรภัทร", "per_surname": "สวัดดี"}
    q.cache_employee("9999999999999", payload, ttl_hours=1)
    got = q.get_cached_employee("9999999999999")
    ok = assert_eq(got, payload, "cache_employee → get_cached_employee round-trip")

    # update
    payload2 = {**payload, "name": "วีรภัทร สวัดดี (updated)"}
    q.cache_employee("9999999999999", payload2, ttl_hours=1)
    got2 = q.get_cached_employee("9999999999999")
    ok &= assert_eq(got2['name'], "วีรภัทร สวัดดี (updated)", "upsert overwrites")

    # missing
    missing = q.get_cached_employee("0000000000000")
    ok &= assert_eq(missing, None, "miss → None")

    # all ids
    ids = q.all_cached_employee_ids()
    ok &= assert_eq("9999999999999" in ids, True, "all_cached_employee_ids contains key")
    return ok


def test_sync_state():
    print("\n[TEST] sync_state KV")
    q.set_state("last_pg_check", {"ok": True, "ts": "2026-05-11T15:00:00"})
    got = q.get_state("last_pg_check")
    ok = assert_eq(got, {"ok": True, "ts": "2026-05-11T15:00:00"}, "dict round-trip")

    q.set_state("pending_depth", 42)
    ok &= assert_eq(q.get_state("pending_depth"), 42, "int round-trip")

    q.set_state("last_error", "PG connection lost")
    ok &= assert_eq(q.get_state("last_error"), "PG connection lost", "str round-trip")

    ok &= assert_eq(q.get_state("nonexistent", "default"), "default", "missing key → default")

    all_state = q.get_all_state()
    ok &= assert_eq("last_pg_check" in all_state and "pending_depth" in all_state,
                    True, "get_all_state contains all keys")
    return ok


def test_list_today():
    print("\n[TEST] list_today")
    today_rows = q.list_today()
    ok = assert_eq(len(today_rows) >= 1, True, f"≥1 row today (got {len(today_rows)})")

    synced_only = q.list_today(only_synced=True)
    ok &= assert_eq(len(synced_only) >= 1, True, "synced_only returns ≥1 synced row")
    ok &= assert_eq(all(r['synced'] == 1 for r in synced_only), True,
                    "synced_only rows all have synced=1")
    return ok


def test_purge():
    print("\n[TEST] purge_old_synced (forced)")
    # set synced row's created_at เก่าๆ
    with q.get_conn() as c:
        c.execute("UPDATE attendance_buf SET created_at = datetime('now','-100 days') "
                  "WHERE synced=1 LIMIT 1")
    deleted = q.purge_old_synced(keep_days=30)
    ok = assert_eq(deleted >= 1, True, f"purge ≥1 old synced row (got {deleted})")
    return ok


def main():
    tests = [
        test_enqueue_and_dedup,
        test_list_pending_and_mark_synced,
        test_record_sync_failure,
        test_employee_cache,
        test_sync_state,
        test_list_today,
        test_purge,
    ]
    passed = 0
    for t in tests:
        if t():
            passed += 1
    print(f"\n{'='*50}")
    print(f"Result: {passed}/{len(tests)} passed")
    print(f"tmp DB at: {_tmp_db}")
    sys.exit(0 if passed == len(tests) else 1)


if __name__ == "__main__":
    main()
