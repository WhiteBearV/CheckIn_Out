"""
api_client.py — HTTP client + mock สำหรับ Face Attendance
==========================================================
ไฟล์นี้ทำหน้าที่ 2 อย่าง:
  1. fetch_person_by_pid()  — ดึงข้อมูลพนักงานจาก external API (หรือ mock)
  2. mark_attendance()      — บันทึก IN/OUT ไปที่ local FastAPI (api.py)

ตั้งค่า:
  MOCK_MODE = True   → ใช้ข้อมูลจำลอง (ทดสอบโดยไม่ต้อง external API)
  MOCK_MODE = False  → เรียก external API จริง (กำหนด EXTERNAL_API_URL + EXTERNAL_API_KEY)
"""

import os
import requests
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

# ── Local API (api.py) ──────────────────────────────────────────────────────
LOCAL_API_URL = "http://localhost:8000"
TIMEOUT       = 5  # วินาที

# ── External API (อ่านจาก .env — ห้ามใส่ key ตรงนี้) ───────────────────────
MOCK_MODE        = os.environ.get("MOCK_MODE", "false").lower() not in ("false", "0", "no")
EXTERNAL_API_URL = os.environ.get("EXTERNAL_API_URL", "")
EXTERNAL_API_KEY = os.environ.get("EXTERNAL_API_KEY", "")

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

    ลำดับการดึง:
      1. MOCK_MODE=True → ใช้ _MOCK_PERSONS
      2. External API → _real_fetch()
      3. Fallback: local attendance DB → _local_fetch()
         (ใช้เมื่อ API ไม่มีข้อมูล หรือ timeout — ดึงจาก check-in ล่าสุดใน DB)

    Returns:
        dict  ที่มี per_id, name, per_name, per_surname, prenameth_abbr,
              organize_th, posname_th, ...
        None  ถ้าไม่พบทั้งใน API และ DB
    """
    if MOCK_MODE:
        return _mock_fetch(per_id)
    result = _real_fetch(per_id)
    if not result:
        result = _local_fetch(per_id)
    return result


def _mock_fetch(per_id: str) -> dict | None:
    result = _MOCK_PERSONS.get(per_id)
    if result:
        return result
    # fallback to local DB for IDs not in mock dict
    local = _local_fetch(per_id)
    if local:
        return local
    print(f"[MOCK] ไม่พบ per_id={per_id} ใน mock database หรือ local DB")
    return None


def _real_fetch(per_id: str) -> dict | None:
    try:
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
        body = resp.json()

        # หา dict ที่มี per_name หรือ per_id จาก wrapper ที่ API อาจห่อมา
        # เช่น {"data": {...}}, {"result": {...}}, {"employee": {...}}
        person = None
        if isinstance(body, dict):
            if body.get("per_name") or body.get("per_id"):
                person = body   # ส่ง flat ตรงๆ
            else:
                for key in ("data", "result", "employee", "person", "info"):
                    candidate = body.get(key)
                    if isinstance(candidate, dict) and (candidate.get("per_name") or candidate.get("per_id")):
                        person = candidate
                        break

        if not person:
            print(f"[API CLIENT] ไม่พบข้อมูล per_name ใน response: {str(body)[:200]}")
            return None

        print(f"[API CLIENT] ดึงข้อมูลสำเร็จ per_id={per_id} per_name={person.get('per_name')}")
        return person

    except Exception as e:
        print(f"[API CLIENT] fetch_person_by_pid({per_id}): {e}")
        return None


def _local_fetch(per_id: str) -> dict | None:
    """Fallback: ดึงจาก local attendance DB (ข้อมูลจาก check-in ล่าสุดที่มีชื่อ)"""
    try:
        from db import get_connection
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT per_id, name, prename_th, per_name, per_surname,
                           posname_th, organize_th, organize_id
                    FROM attendance_logs
                    WHERE per_id = %s
                      AND per_name IS NOT NULL AND per_name != ''
                    ORDER BY check_time DESC
                    LIMIT 1
                """, (per_id,))
                row = cur.fetchone()
        if not row:
            print(f"[API CLIENT] local_fetch: ไม่พบ per_id={per_id} ใน attendance DB")
            return None
        print(f"[API CLIENT] local_fetch: ใช้ข้อมูลจาก DB สำหรับ per_id={per_id}")
        return {
            "per_id":         row[0],
            "name":           row[1] or "",
            "prename_th":     row[2] or "",
            "per_name":       row[3] or "",
            "per_surname":    row[4] or "",
            "posname_th":     row[5] or "",
            "organize_th":    row[6] or "",
            "organize_id":    row[7] or "",
            "prenameth_abbr": row[2] or "",  # ใช้ prename_th แทน abbr เมื่อมาจาก DB
        }
    except Exception as e:
        print(f"[API CLIENT] local_fetch({per_id}): {e}")
        return None


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
                    organize_id: str = None) -> bool:
    """
    บันทึก IN หรือ OUT ผ่าน local API (api.py)

    Returns: True ถ้าสำเร็จ, False ถ้าซ้ำหรือ error
    """
    try:
        payload = {
            "per_id":      per_id,
            "status":      status,
            "camera_name": camera_name,
            "check_time":  check_time.isoformat() if check_time else None,
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
            print(f"[API CLIENT] บันทึก {status} สำเร็จ ({per_id})")
            return True
        else:
            print(f"[API CLIENT] ไม่บันทึก ({per_id}, {status}): {result.get('reason')}")
            return False

    except Exception as e:
        print(f"[API CLIENT] mark_attendance({per_id}, {status}): {e}")
        return False
