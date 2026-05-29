"""
test_offline_endpoints.py — verify /system/offline + /attendance/today fallback
รัน: venv/bin/python test_offline_endpoints.py

ทดสอบโดยเรียก endpoint handler functions ตรงๆ (ไม่ผ่าน HTTP) เพื่อเลี่ยง JWT/dep injection
"""
import os
import sys
import tempfile
import asyncio
from datetime import datetime
from unittest.mock import patch

_tmpdir = tempfile.mkdtemp(prefix="endpoints_test_")
_tmp_db = os.path.join(_tmpdir, "test.db")
os.environ["OFFLINE_QUEUE_PATH"] = _tmp_db
os.environ.setdefault("EXTERNAL_API_URL", "http://mock.example.com")
os.environ.setdefault("EXTERNAL_API_KEY", "test-key")

import offline_queue
offline_queue.DB_PATH = _tmp_db
offline_queue._initialized = False
offline_queue.init_db()


def assert_eq(actual, expected, label):
    if actual != expected:
        print(f"  ✗ {label}: expected {expected!r}, got {actual!r}")
        return False
    print(f"  ✓ {label}")
    return True


def _clear():
    with offline_queue.get_conn() as c:
        c.execute("DELETE FROM attendance_buf")
        c.execute("DELETE FROM sync_state")


def test_attendance_today_pg_ok():
    print("\n[TEST] /attendance/today — PG OK path (rows from PG)")
    import api as api_module
    _clear()

    class _FakeCur:
        def execute(self, *a, **kw): pass
        def fetchall(self):
            return [
                (1, "1111111111111", "Test User", "นาย", "Test", "User",
                 "Engineer", "Dept", "ORG1", "IN", "cam1",
                 datetime(2026, 5, 11, 9, 0, 0)),
            ]
        def __enter__(self): return self
        def __exit__(self, *a): pass

    class _FakeConn:
        def cursor(self): return _FakeCur()
        def __enter__(self): return self
        def __exit__(self, *a): pass

    with patch.object(api_module, "get_connection", return_value=_FakeConn()):
        result = api_module.attendance_today()

    ok = assert_eq(len(result), 1, "1 row returned")
    ok &= assert_eq(result[0]["source"], "pg", "source=pg")
    ok &= assert_eq(result[0]["per_id"], "1111111111111", "per_id matches")
    return ok


def test_attendance_today_pg_down_fallback():
    print("\n[TEST] /attendance/today — PG down → fallback to attendance_buf")
    import api as api_module
    _clear()
    # populate attendance_buf with 2 today rows
    offline_queue.enqueue_attendance("2222222222222", "IN", "camA",
                                     datetime.now(), name="Buf User A",
                                     synced=True)
    offline_queue.enqueue_attendance("3333333333333", "IN", "camB",
                                     datetime.now(), name="Buf User B",
                                     synced=False)

    def _raise(*a, **kw):
        raise Exception("PG connection refused")

    with patch.object(api_module, "get_connection", side_effect=_raise):
        result = api_module.attendance_today()

    ok = assert_eq(len(result), 2, "2 rows from attendance_buf")
    sources = {r["source"] for r in result}
    ok &= assert_eq(sources, {"buf"}, "all rows source=buf")
    # rows should include synced flag
    synced_flags = sorted([r["synced"] for r in result])
    ok &= assert_eq(synced_flags, [False, True], "one synced + one pending")
    # id should be negative to distinguish from PG ids
    ok &= assert_eq(all(r["id"] < 0 for r in result), True, "all ids negative")
    return ok


def test_system_offline_endpoint():
    print("\n[TEST] /system/offline — exposes worker state")
    import stream_server
    _clear()

    # populate some state
    offline_queue.enqueue_attendance("4444444444444", "IN", "cam1",
                                     datetime.now(), synced=False)
    offline_queue.set_state("last_pg_check", {"ok": True, "ts": "2026-05-11T15:00"})
    offline_queue.set_state("last_sync", {"ts": "2026-05-11T15:00", "drained": 3,
                                          "transient_failed": 0,
                                          "permanent_failed": 0, "pending_after": 0})

    # call the handler directly (it's async)
    result = asyncio.get_event_loop().run_until_complete(
        stream_server.system_offline_status()
    )

    ok = assert_eq(result["pending_count"], 1, "pending_count == 1")
    ok &= assert_eq(result["last_pg_check"]["ok"], True, "last_pg_check.ok")
    ok &= assert_eq(result["last_sync"]["drained"], 3, "last_sync.drained")
    ok &= assert_eq("worker_running" in result, True, "worker_running key present")
    return ok


def main():
    tests = [
        test_attendance_today_pg_ok,
        test_attendance_today_pg_down_fallback,
        test_system_offline_endpoint,
    ]
    passed = 0
    for t in tests:
        try:
            if t():
                passed += 1
        except Exception as e:
            import traceback
            print(f"  ✗ {t.__name__} exception:")
            traceback.print_exc()
    print(f"\n{'='*50}")
    print(f"Result: {passed}/{len(tests)} passed")
    sys.exit(0 if passed == len(tests) else 1)


if __name__ == "__main__":
    main()
