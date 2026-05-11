"""
test_sync_worker.py — verify sync_worker tick logic (no threading)
รัน: venv/bin/python test_sync_worker.py
"""
import os
import sys
import tempfile
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

_tmpdir = tempfile.mkdtemp(prefix="sync_worker_test_")
_tmp_db = os.path.join(_tmpdir, "test.db")
os.environ["OFFLINE_QUEUE_PATH"] = _tmp_db
os.environ.setdefault("EXTERNAL_API_URL", "http://mock.example.com")
os.environ.setdefault("EXTERNAL_API_KEY", "test-key")
os.environ["KNOWN_FACES_DIR"] = os.path.join(_tmpdir, "known_faces")
os.makedirs(os.environ["KNOWN_FACES_DIR"], exist_ok=True)

import offline_queue
offline_queue.DB_PATH = _tmp_db
offline_queue._initialized = False
offline_queue.init_db()

import sync_worker
from requests.exceptions import ConnectionError as ReqConnErr


def assert_eq(actual, expected, label):
    if actual != expected:
        print(f"  ✗ {label}: expected {expected!r}, got {actual!r}")
        return False
    print(f"  ✓ {label}")
    return True


def _mk_post_response(success: bool, reason: str = ""):
    m = MagicMock()
    m.raise_for_status = MagicMock()
    m.json = MagicMock(return_value={"success": success, "reason": reason})
    return m


def _mk_get_response(status_code: int = 200):
    m = MagicMock()
    m.status_code = status_code
    return m


def _clear():
    with offline_queue.get_conn() as c:
        c.execute("DELETE FROM attendance_buf")
        c.execute("DELETE FROM employee_cache")
        c.execute("DELETE FROM sync_state")


def _enqueue_pending(per_id: str, status: str = "IN", camera: str = "cam1"):
    return offline_queue.enqueue_attendance(per_id, status, camera, datetime.now(),
                                            name="x", synced=False)


def test_drain_success():
    print("\n[TEST] drain — all rows synced")
    _clear()
    ids = [_enqueue_pending(f"100{i:04d}11111111"[:13]) for i in range(3)]
    assert all(i is not None for i in ids), "preconditions: 3 rows enqueued"
    with patch("sync_worker.requests.post", return_value=_mk_post_response(True)):
        sync_worker._drain_pending()
    ok = assert_eq(offline_queue.pending_count(), 0, "all 3 rows synced")
    last_sync = offline_queue.get_state("last_sync")
    ok &= assert_eq(last_sync.get("drained"), 3, "last_sync.drained == 3")
    return ok


def test_drain_pg_dup_marked_synced():
    print("\n[TEST] PG dup ('วันนี้บันทึก') → mark_synced (drop from queue)")
    _clear()
    _enqueue_pending("2000000000001")
    with patch("sync_worker.requests.post",
               return_value=_mk_post_response(False, "วันนี้บันทึก IN แล้ว")):
        sync_worker._drain_pending()
    return assert_eq(offline_queue.pending_count(), 0, "row dropped from queue")


def test_drain_transient_failure_bails():
    print("\n[TEST] network failure → record_sync_failure + bail tick")
    _clear()
    _enqueue_pending("3000000000001")
    _enqueue_pending("3000000000002")
    with patch("sync_worker.requests.post",
               side_effect=ReqConnErr("PG down")):
        sync_worker._drain_pending()
    ok = assert_eq(offline_queue.pending_count(), 2, "both rows stay pending")
    # retry_count incremented แค่ row แรก (bail หลัง row แรก fail)
    pending = offline_queue.list_pending(limit=10)
    failed_rows = [r for r in pending if r['retry_count'] > 0]
    ok &= assert_eq(len(failed_rows), 1, "only first row's retry_count bumped")
    return ok


def test_drain_permanent_failure_continues():
    print("\n[TEST] rule reject ('ยังไม่มี IN วันนี้') → keep row, try next")
    _clear()
    # row1 — OUT without IN → permanent reject (will retry later)
    _enqueue_pending("4000000000001", status="OUT")
    # row2 — IN → success
    _enqueue_pending("4000000000002", status="IN")

    def post_router(url, **kwargs):
        payload = kwargs.get("json", {})
        if payload.get("status") == "OUT" and payload.get("per_id") == "4000000000001":
            return _mk_post_response(False, "ยังไม่มี IN วันนี้")
        return _mk_post_response(True)

    with patch("sync_worker.requests.post", side_effect=post_router):
        sync_worker._drain_pending()

    # row2 should be synced, row1 should still be pending with retry_count++
    ok = assert_eq(offline_queue.pending_count(), 1, "1 row left (the OUT-no-IN one)")
    pending = offline_queue.list_pending(limit=10)
    ok &= assert_eq(pending[0]['per_id'], "4000000000001", "remaining row is the OUT one")
    ok &= assert_eq(pending[0]['retry_count'], 1, "retry_count bumped on remaining row")
    return ok


def test_probe_pg_no_pending():
    print("\n[TEST] no pending → probe PG health and write state")
    _clear()
    with patch("sync_worker.requests.get", return_value=_mk_get_response(200)):
        sync_worker._tick()
    state = offline_queue.get_state("last_pg_check")
    return assert_eq(state.get("ok"), True, "last_pg_check.ok=True after probe")


def test_probe_pg_down():
    print("\n[TEST] probe — PG down")
    _clear()
    with patch("sync_worker.requests.get", side_effect=ReqConnErr("down")):
        sync_worker._tick()
    state = offline_queue.get_state("last_pg_check")
    return assert_eq(state.get("ok"), False, "last_pg_check.ok=False")


def test_cache_refresh():
    print("\n[TEST] _refresh_employee_cache walks known_faces dir")
    _clear()
    # สร้าง known_faces/{per_id}/
    kf = sync_worker.KNOWN_FACES_DIR
    for pid in ["7000000000001", "7000000000002", "notadigit"]:
        os.makedirs(os.path.join(kf, pid), exist_ok=True)

    payload = {"per_id": "X", "name": "Test"}
    fake_resp = MagicMock()
    fake_resp.status_code = 200
    fake_resp.raise_for_status = MagicMock()
    fake_resp.json = MagicMock(return_value=payload)
    with patch("api_client.requests.post", return_value=fake_resp):
        sync_worker._refresh_employee_cache()

    cached_ids = offline_queue.all_cached_employee_ids()
    ok = assert_eq(sorted(cached_ids), ["7000000000001", "7000000000002"],
                   "only digit-named dirs cached")
    state = offline_queue.get_state("last_cache_refresh")
    ok &= assert_eq(state.get("refreshed"), 2, "refreshed=2")
    ok &= assert_eq(state.get("skipped"), 1, "skipped=1 (notadigit)")
    return ok


def test_tick_updates_pending_count():
    print("\n[TEST] tick updates pending_count state")
    _clear()
    _enqueue_pending("8000000000001")
    _enqueue_pending("8000000000002")
    # mock POST to fail so we don't accidentally clear
    with patch("sync_worker.requests.post", side_effect=ReqConnErr("down")), \
         patch("sync_worker.requests.get", side_effect=ReqConnErr("down")):
        sync_worker._tick()
    return assert_eq(offline_queue.get_state("pending_count"), 2,
                     "pending_count state == 2")


def main():
    tests = [
        test_drain_success,
        test_drain_pg_dup_marked_synced,
        test_drain_transient_failure_bails,
        test_drain_permanent_failure_continues,
        test_probe_pg_no_pending,
        test_probe_pg_down,
        test_cache_refresh,
        test_tick_updates_pending_count,
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
