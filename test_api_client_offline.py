"""
test_api_client_offline.py — verify api_client.py wiring กับ offline_queue
รัน: venv/bin/python test_api_client_offline.py

Mock requests.post เพื่อจำลอง 4 scenarios:
  - online success
  - online dup ("วันนี้บันทึก IN แล้ว")
  - online OUT without IN
  - offline (network error → queued)
  - N-cam race (2 cams offline ใส่ IN พร้อมกัน → 1 ชนะ 1 แพ้)
และ fetch_person_by_pid: online → cache, offline → stale cache fallback
"""
import os
import sys
import tempfile
from datetime import datetime
from unittest.mock import patch, MagicMock

# isolate DB
_tmpdir = tempfile.mkdtemp(prefix="api_client_offline_test_")
_tmp_db = os.path.join(_tmpdir, "test.db")
os.environ["OFFLINE_QUEUE_PATH"] = _tmp_db

# .env loaded by api_client → ensure required keys exist
os.environ.setdefault("EXTERNAL_API_URL", "http://mock.example.com")
os.environ.setdefault("EXTERNAL_API_KEY", "test-key")

import offline_queue
offline_queue.DB_PATH = _tmp_db
offline_queue._initialized = False
offline_queue.init_db()

# import after env setup
import api_client
from requests.exceptions import ConnectionError as ReqConnectionError


# ─── helpers ─────────────────────────────────────────────────────────────────

def assert_eq(actual, expected, label):
    if actual != expected:
        print(f"  ✗ {label}: expected {expected!r}, got {actual!r}")
        return False
    print(f"  ✓ {label}")
    return True


def _post_mock(success: bool, reason: str = ""):
    """build mock response object for requests.post"""
    m = MagicMock()
    m.raise_for_status = MagicMock()
    m.json = MagicMock(return_value={"success": success, "reason": reason})
    return m


def _clear_buf():
    with offline_queue.get_conn() as c:
        c.execute("DELETE FROM attendance_buf")
        c.execute("DELETE FROM employee_cache")


# ─── tests ───────────────────────────────────────────────────────────────────

def test_online_success():
    print("\n[TEST] online success")
    _clear_buf()
    with patch("api_client.requests.post", return_value=_post_mock(True)):
        ok, reason = api_client.mark_attendance(
            "1234567890123", "IN", "cam1", datetime.now(), name="Test")
    ok1 = assert_eq((ok, reason), (True, ""), "returns (True, '')")
    # buf row must be synced=1
    with offline_queue.get_conn() as c:
        row = c.execute(
            "SELECT synced FROM attendance_buf WHERE per_id=? AND status='IN'",
            ("1234567890123",)).fetchone()
    ok2 = assert_eq(row is not None and row['synced'] == 1, True, "buf row synced=1")
    return ok1 and ok2


def test_online_dup_pg_rejects():
    print("\n[TEST] PG rejects (dup) → delete buf row")
    _clear_buf()
    # pretend PG has the IN already → it returns success=False, reason=...
    with patch("api_client.requests.post",
               return_value=_post_mock(False, "วันนี้บันทึก IN แล้ว")):
        ok, reason = api_client.mark_attendance(
            "2222222222222", "IN", "cam1", datetime.now(), name="Test")
    ok1 = assert_eq((ok, "IN แล้ว" in reason), (False, True),
                    "(False, '...IN แล้ว')")
    # buf row should be deleted (PG is authority)
    cnt = offline_queue.pending_count()
    ok2 = assert_eq(cnt, 0, "buf row deleted after PG dup-reject")
    return ok1 and ok2


def test_online_out_without_in():
    print("\n[TEST] OUT without IN → PG rejects, buf cleaned")
    _clear_buf()
    with patch("api_client.requests.post",
               return_value=_post_mock(False, "ยังไม่มี IN วันนี้")):
        ok, reason = api_client.mark_attendance(
            "3333333333333", "OUT", "cam1", datetime.now(), name="Test")
    ok1 = assert_eq((ok, "ยังไม่มี IN" in reason), (False, True),
                    "(False, 'ยังไม่มี IN...')")
    ok2 = assert_eq(offline_queue.pending_count(), 0, "buf cleaned")
    return ok1 and ok2


def test_offline_network_error():
    print("\n[TEST] offline (network error) → queued offline")
    _clear_buf()
    with patch("api_client.requests.post",
               side_effect=ReqConnectionError("connection refused")):
        ok, reason = api_client.mark_attendance(
            "4444444444444", "IN", "cam1", datetime.now(), name="Test")
    ok1 = assert_eq((ok, reason), (True, "queued offline"), "(True, 'queued offline')")
    # buf row should remain synced=0
    with offline_queue.get_conn() as c:
        row = c.execute(
            "SELECT synced FROM attendance_buf WHERE per_id=?",
            ("4444444444444",)).fetchone()
    ok2 = assert_eq(row is not None and row['synced'] == 0, True,
                    "buf row remains synced=0")
    return ok1 and ok2


def test_offline_n_cam_race():
    print("\n[TEST] N-cam race offline — local arbiter")
    _clear_buf()
    # 2 cameras call mark_attendance for same per_id+IN+today while PG is down
    with patch("api_client.requests.post",
               side_effect=ReqConnectionError("PG down")):
        ok_a, r_a = api_client.mark_attendance(
            "5555555555555", "IN", "camA", datetime.now(), name="Test")
        ok_b, r_b = api_client.mark_attendance(
            "5555555555555", "IN", "camB", datetime.now(), name="Test")
    # camA wins (first to enqueue), camB loses
    ok1 = assert_eq((ok_a, r_a), (True, "queued offline"), "camA wins → queued")
    ok2 = assert_eq((ok_b, "IN แล้ว" in r_b), (False, True),
                    "camB loses → (False, '...IN แล้ว')")
    # only 1 row in buf
    rows = offline_queue.list_pending(limit=10)
    pending_for_5 = [r for r in rows if r['per_id'] == "5555555555555"]
    ok3 = assert_eq(len(pending_for_5), 1, "only 1 buf row for per_id=5555")
    ok4 = assert_eq(pending_for_5[0]['camera_name'], "camA",
                    "camA's row is the one in buf")
    return ok1 and ok2 and ok3 and ok4


def test_fetch_caches_on_success():
    print("\n[TEST] fetch_person_by_pid caches on success")
    _clear_buf()
    api_client.MOCK_MODE = False  # ensure not mock
    sample = {"per_id": "6666666666666", "name": "วีรภัทร สวัดดี", "per_name": "วีรภัทร"}
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json = MagicMock(return_value=sample)
    with patch("api_client.requests.post", return_value=mock_resp):
        result = api_client.fetch_person_by_pid("6666666666666")
    ok1 = assert_eq(result, sample, "returns external API payload")
    cached = offline_queue.get_cached_employee("6666666666666")
    ok2 = assert_eq(cached, sample, "cached in employee_cache")
    return ok1 and ok2


def test_fetch_falls_back_to_cache():
    print("\n[TEST] fetch_person_by_pid falls back to cache on network error")
    # use the one cached above
    api_client.MOCK_MODE = False
    with patch("api_client.requests.post", side_effect=ReqConnectionError("API down")):
        result = api_client.fetch_person_by_pid("6666666666666")
    return assert_eq(result is not None and result.get("name") == "วีรภัทร สวัดดี",
                     True, "uses stale cache when API down")


def test_fetch_404_no_cache_fallback():
    print("\n[TEST] fetch_person_by_pid 404 → None (NO cache fallback)")
    _clear_buf()
    api_client.MOCK_MODE = False
    mock_resp = MagicMock()
    mock_resp.status_code = 404
    mock_resp.raise_for_status = MagicMock()
    with patch("api_client.requests.post", return_value=mock_resp):
        result = api_client.fetch_person_by_pid("9999999999999")
    return assert_eq(result, None, "genuine 404 → None")


def main():
    tests = [
        test_online_success,
        test_online_dup_pg_rejects,
        test_online_out_without_in,
        test_offline_network_error,
        test_offline_n_cam_race,
        test_fetch_caches_on_success,
        test_fetch_falls_back_to_cache,
        test_fetch_404_no_cache_fallback,
    ]
    passed = 0
    for t in tests:
        try:
            if t():
                passed += 1
        except Exception as e:
            print(f"  ✗ exception: {e}")
    print(f"\n{'='*50}")
    print(f"Result: {passed}/{len(tests)} passed")
    print(f"tmp DB at: {_tmp_db}")
    sys.exit(0 if passed == len(tests) else 1)


if __name__ == "__main__":
    main()
