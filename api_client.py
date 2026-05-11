"""
api_client.py — HTTP client + mock สำหรับ Face Attendance
==========================================================
ไฟล์นี้ทำหน้าที่ 2 อย่าง:
  1. fetch_person_by_pid()  — ดึงข้อมูลพนักงานจาก external API (หรือ mock)
                              พร้อม fallback ไปอ่าน employee_cache ใน offline mode
  2. mark_attendance()      — บันทึก IN/OUT ไปที่ local FastAPI (api.py)
                              พร้อมเขียน attendance_buf เป็น local arbiter + queue

ตั้งค่า:
  MOCK_MODE = True   → ใช้ข้อมูลจำลอง (ทดสอบโดยไม่ต้อง external API)
  MOCK_MODE = False  → เรียก external API จริง (กำหนด EXTERNAL_API_URL + EXTERNAL_API_KEY)
"""

import os
import requests
from datetime import datetime
from dotenv import load_dotenv

import offline_queue  # SQLite-backed buffer + cache (Phase 2)

load_dotenv()

# ── Local API (api.py) ──────────────────────────────────────────────────────
LOCAL_API_URL = os.environ.get("LOCAL_API_URL", "http://localhost:8000")
TIMEOUT       = 5  # วินาที

# ── External API (อ่านจาก .env — ห้ามใส่ key ตรงนี้) ───────────────────────
MOCK_MODE        = False
EXTERNAL_API_URL = os.environ["EXTERNAL_API_URL"]
EXTERNAL_API_KEY = os.environ["EXTERNAL_API_KEY"]

# ─────────────────────────────────────────────────────────────────────────────

# ── Mock database (format เหมือน external API เป๊ะ) ────────────────────────
# เพิ่ม per_id ของทุกคนที่มีโฟลเดอร์ใน known_faces/ ตรงนี้
_MOCK_PERSONS: dict[str, dict] = {
    "6666666666666": {
        "per_id":         "6666666666666",
        "name":           "ร้อยตรี วีรภัทร สวัดดี",
        "prename_th":     "ร้อยตรี",
        "per_name":       "วีรภัทร",
        "per_surname":    "สวัดดี",
        "posname_th":     "เจ้าหน้าที่งานในพระองค์ ระดับ 99",
        "prenameth_abbr": "ร.ต.",
        "organize_th":    "ฝ่ายวิจัยและพัฒนานวัตกรรมด้าน Software",
        "organize_id":    "1234567",
        "org_path_name":  "/หน่วยราชการตัวอย่าง/ศูนย์เทคโนโลยีดิจิทัลตัวอย่าง/",
        "birthDate":      "2000-11-07",
        "per_picpath":    "",
    },
    "7777777777777": {
        "per_id":         "7777777777777",
        "name":           "พันโท พชร คะจรจัด",
        "prename_th":     "พันโท",
        "per_name":       "พชร",
        "per_surname":    "คะจรจัด",
        "posname_th":     "เจ้าหน้าที่งานในพระองค์ ระดับ 0.99",
        "prenameth_abbr": "พ.ท.",
        "organize_th":    "ฝ่ายวิจัยและพัฒนานวัตกรรมด้าน Software",
        "organize_id":    "7654321",
        "org_path_name":  "/หน่วยราชการตัวอย่างพิเศษ/ศูนย์เทคโนโลยีดิจิทัลตัวอย่าง/",
        "birthDate":      "1995-05-20",
        "per_picpath":    "",
    },
    "8888888888888": {
        "per_id":         "8888888888888",
        "name":           "เนติ อนันธการณ์ฑ์ฒ์ฬ์ฆ์ฏ์ฌ์ฐ์",
        "prename_th":     "",
        "per_name":       "เนติ",
        "per_surname":    "อนันธการณ์ฑ์ฒ์ฬ์ฆ์ฏ์ฌ์ฐ์",
        "posname_th":     "รอง(เท้า) ระดับ 32",
        "prenameth_abbr": "",
        "organize_th":    "ฝ่ายทำความสะอาดและวิจัยขยะเปียก",
        "organize_id":    "6767679",
        "org_path_name":  "/หน่วยราชการทำความสะอาด/ศูนย์เทคโนโลยีดิจิทัลตัวอย่าง/",
        "birthDate":      "1246-02-29",
        "per_picpath":    "",
    },
    # เพิ่มคนอื่นๆ ตามโฟลเดอร์ใน known_faces/ ได้เลย เช่น:
    # "1234567890123": { "per_id": "1234567890123", "per_name": "สมชาย", ... },
}


# ─── ดึงข้อมูลพนักงานจาก per_id ─────────────────────────────────────────────

def fetch_person_by_pid(per_id: str) -> dict | None:
    """
    ดึงข้อมูลพนักงานจาก per_id (เลข 13 หลัก = ชื่อโฟลเดอร์ใน known_faces/)

    Flow:
      1. ลอง external API ก่อน — สำเร็จ → upsert employee_cache + return
      2. 404 (genuine not found) → return None (ไม่ fall back เพราะอาจมี stale cache)
      3. network/timeout/5xx → fall back ไป employee_cache (allow stale)

    Returns:
        dict  ที่มี per_id, name, per_name, per_surname, prenameth_abbr,
              organize_th, posname_th, ... ครบตามที่ external API ส่งมา
        None  ถ้าไม่พบ และ cache ก็ไม่มี
    """
    if MOCK_MODE:
        return _mock_fetch(per_id)

    try:
        result = _real_fetch(per_id)
    except requests.RequestException as e:
        # network failure — try cache fallback
        cached = offline_queue.get_cached_employee(per_id, allow_expired=True)
        if cached:
            print(f"[API CLIENT] fetch_person_by_pid({per_id}): external API down "
                  f"({e}) — ใช้ employee_cache (stale OK)")
            return cached
        print(f"[API CLIENT] fetch_person_by_pid({per_id}): external API down + ไม่มี cache")
        return None

    if result is not None:
        # success — refresh cache (no TTL — sync_worker handles periodic refresh)
        try:
            offline_queue.cache_employee(per_id, result)
        except Exception as cache_err:
            print(f"[API CLIENT] cache_employee({per_id}) failed: {cache_err}")
    return result


def _mock_fetch(per_id: str) -> dict | None:
    result = _MOCK_PERSONS.get(per_id)
    if not result:
        print(f"[MOCK] ไม่พบ per_id={per_id} ใน mock database")
    return result


def _real_fetch(per_id: str) -> dict | None:
    """
    Raises:
        requests.RequestException — network/timeout/5xx → caller จะ fall back ไป cache
    Returns:
        dict — found
        None — 404 (genuinely not in external system)
    """
    resp = requests.post(
        f"{EXTERNAL_API_URL}/api/check-emp",
        headers={
            "x-api-key": EXTERNAL_API_KEY,
            "Content-Type": "application/json",
        },
        json={"per_cardno": per_id},
        timeout=TIMEOUT,
    )
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    return resp.json()


# ─── Mask per_id — แสดง/บันทึกชื่อไฟล์แค่ 4 ตัวท้าย ─────────────────────────

def mask_pid(per_id) -> str:
    """เซ็นเซอร์เลข per_id 13 หลัก → '*********6666' (โชว์แค่ 4 ตัวท้าย)

    ใช้ทุกที่ที่ per_id จะโผล่สู่ภายนอก — UI, ชื่อไฟล์ (live_snap, PicSAVE),
    state ที่ส่งให้ frontend — เพื่อไม่ให้เลขบัตร ปชช. 13 หลักรั่วออกไป
    """
    if not per_id:
        return ""
    s = str(per_id)
    if len(s) <= 4:
        return s
    return "*" * (len(s) - 4) + s[-4:]


# ─── สร้างชื่อแสดงผล ─────────────────────────────────────────────────────────

def get_display_name(person_dict: dict | None) -> str:
    """
    สร้างชื่อแสดงผลจาก dict ที่ได้จาก fetch_person_by_pid()
    ใช้ prenameth_abbr + per_name + per_surname (กระชับกว่า prename_th เต็ม)
    เช่น "ร.ต. วีรภัทร สวัดดี"
    """
    if not person_dict:
        return "Unknown"
    parts = [
        person_dict.get("prenameth_abbr", ""),
        person_dict.get("per_name", ""),
        person_dict.get("per_surname", ""),
    ]
    return " ".join(p for p in parts if p)


# ─── บันทึกเวลา (local API) ──────────────────────────────────────────────────

def mark_attendance(per_id: str, status: str,
                    camera_name: str = None,
                    check_time: datetime = None,
                    name: str = None,
                    prename_th: str = None,
                    per_name: str = None,
                    per_surname: str = None,
                    posname_th: str = None,
                    organize_th: str = None,
                    organize_id: str = None) -> tuple[bool, str]:
    """
    บันทึก IN หรือ OUT — ผ่าน 2 ชั้น:
      1. INSERT ลง attendance_buf (local SQLite) เป็น arbiter — UNIQUE index
         (per_id, status, date(check_time)) ทำหน้าที่ตัดสิน N-cam race แทน PG
      2. POST /attendance (api.py → PG)
         - success      → mark_synced(buf_id) + return (True, "")
         - DB rule fail → delete buf row + return (False, reason)
         - network fail → leave buf row synced=0, sync_worker จะ replay
                          → return (True, "queued offline")

    Returns (ok, reason):
      (True,  "")                       — บันทึกถึง PG แล้ว
      (True,  "queued offline")         — บันทึกใน local buf, รอ sync_worker (offline mode)
      (False, "วันนี้บันทึก IN แล้ว")   — ซ้ำ (อีก cam ใส่ก่อน หรือ PG มีอยู่แล้ว)
      (False, "ยังไม่มี IN วันนี้")      — OUT โดยไม่มี IN (DB rule)
      (False, "ERROR: ...")             — error อื่นที่ไม่คาดคิด
    """
    ct = check_time or datetime.now()

    # ── 1. ใส่ใน local buf ก่อน (atomic dedup arbiter) ──
    try:
        buf_id = offline_queue.enqueue_attendance(
            per_id, status, camera_name, ct,
            name=name, prename_th=prename_th,
            per_name=per_name, per_surname=per_surname,
            posname_th=posname_th, organize_th=organize_th,
            organize_id=organize_id, synced=False,
        )
    except Exception as e:
        # SQLite ล่ม — ไม่ควรเกิด แต่ถ้าเกิด fall back ไป online-only path
        print(f"[API CLIENT] enqueue_attendance failed: {e} — fallback online-only")
        buf_id = None

    if buf_id is None and _local_buf_available():
        # dedup index reject — อีก cam ใส่ event แบบเดียวกัน (per_id, status, today) แล้ว
        # ↔ มี side ของ "PG ตอบ ซ้ำแล้ว" — return ในรูปแบบเดียวกัน
        reason = f"วันนี้บันทึก {status} แล้ว"
        print(f"[API CLIENT] ไม่บันทึก ({per_id}, {status}): {reason} (local dedup)")
        return False, reason

    # ── 2. POST ไป api.py → PG ──
    try:
        payload = {
            "per_id":      per_id,
            "status":      status,
            "camera_name": camera_name,
            "check_time":  ct.isoformat(),
            "name":        name,
            "prename_th":  prename_th,
            "per_name":    per_name,
            "per_surname": per_surname,
            "posname_th":  posname_th,
            "organize_th": organize_th,
            "organize_id": organize_id,
        }
        resp = requests.post(
            f"{LOCAL_API_URL}/attendance",
            json=payload,
            timeout=TIMEOUT,
        )
        resp.raise_for_status()
        result = resp.json()

        if result.get("success"):
            # PG accepted → mark buf row synced
            if buf_id is not None:
                try:
                    offline_queue.mark_synced(buf_id)
                except Exception as e:
                    print(f"[API CLIENT] mark_synced({buf_id}) failed: {e}")
            print(f"[API CLIENT] บันทึก {status} สำเร็จ ({per_id})")
            return True, ""

        # PG rejected (DB rule: ซ้ำ / OUT ก่อน IN)
        reason = result.get("reason") or ""
        if buf_id is not None:
            # ลบ row นี้ออก buf — PG เป็น authority, row นี้ใช้ไม่ได้
            try:
                with offline_queue.get_conn() as c:
                    c.execute("DELETE FROM attendance_buf WHERE id=?", (buf_id,))
            except Exception as e:
                print(f"[API CLIENT] cleanup buf_id={buf_id} failed: {e}")
        print(f"[API CLIENT] ไม่บันทึก ({per_id}, {status}): {reason}")
        return False, reason

    except requests.RequestException as e:
        # network/timeout/5xx — left buf row synced=0, sync_worker drain ทีหลัง
        if buf_id is not None:
            print(f"[API CLIENT] {status} ({per_id}) queued offline "
                  f"(buf_id={buf_id}, reason={e})")
            return True, "queued offline"
        # buf ก็ใส่ไม่ได้ — error ทั้งคู่
        print(f"[API CLIENT] mark_attendance({per_id}, {status}): {e}")
        return False, f"ERROR: {e}"
    except Exception as e:
        print(f"[API CLIENT] mark_attendance({per_id}, {status}): {e}")
        return False, f"ERROR: {e}"


def _local_buf_available() -> bool:
    """ช่วย check ว่า offline_queue พร้อมใช้งานไหม — ถ้าไม่ได้ก็ฝืน online-only ต่อ"""
    try:
        offline_queue.pending_count()
        return True
    except Exception:
        return False
