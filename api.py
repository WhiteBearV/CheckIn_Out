"""
api.py — FastAPI Server สำหรับระบบ Face Attendance
=====================================================
รัน: uvicorn api:app --host 0.0.0.0 --port 8000

Endpoints:
  [Attendance]
  POST   /attendance                       — บันทึกเวลา IN/OUT
  GET    /attendance/today                 — การลงเวลาวันนี้ทั้งหมด
  GET    /attendance/today/check           — ตรวจว่า IN/OUT วันนี้แล้วหรือยัง
  GET    /attendance/{per_id}              — ประวัติลงเวลาของพนักงาน
  PUT    /attendance/{log_id}              — แก้ไข record ลงเวลา
  DELETE /attendance/{log_id}              — ลบ record ลงเวลา

หมายเหตุ: ข้อมูลพนักงาน (ชื่อ/หน่วยงาน) ดึงจาก external API ผ่าน api_client
          ตาราง employees ถูกลบออกแล้ว — ดู migrate_v9.sql
"""

import os
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query, Depends, Header
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, date
from db import get_connection

load_dotenv()

app = FastAPI(title="Face Attendance API", version="2.0.0")

_ADMIN_KEY = os.environ.get("ADMIN_API_KEY", "")

def _require_admin(x_admin_key: str = Header(...)):
    if not _ADMIN_KEY or x_admin_key != _ADMIN_KEY:
        raise HTTPException(status_code=403, detail="Forbidden")


# ─── Schemas ────────────────────────────────────────────────────────────────

class AttendanceRequest(BaseModel):
    per_id:      str
    status:      str                       # "IN" หรือ "OUT"
    camera_name: Optional[str] = None
    check_time:  Optional[datetime] = None
    name:        Optional[str] = None      # ชื่อเต็ม เช่น "ร้อยตรี วีรภัทร สวัดดี"
    prename_th:  Optional[str] = None      # คำนำหน้าเต็ม
    per_name:    Optional[str] = None      # ชื่อ
    per_surname: Optional[str] = None      # นามสกุล
    posname_th:  Optional[str] = None      # ตำแหน่ง
    organize_th: Optional[str] = None      # หน่วยงาน
    organize_id: Optional[str] = None      # รหัสหน่วยงาน


class AttendanceUpdateRequest(BaseModel):
    status:      Optional[str] = None      # "IN" หรือ "OUT"
    camera_name: Optional[str] = None
    check_time:  Optional[datetime] = None
    name:        Optional[str] = None
    prename_th:  Optional[str] = None
    per_name:    Optional[str] = None
    per_surname: Optional[str] = None
    posname_th:  Optional[str] = None
    organize_th: Optional[str] = None
    organize_id: Optional[str] = None


# ╔═══════════════════════════════════════════════════════════════════════════╗
# ║  Attendance Endpoints                                                     ║
# ╚═══════════════════════════════════════════════════════════════════════════╝

@app.post("/attendance")
def mark_attendance(req: AttendanceRequest):
    """
    บันทึกเวลา IN หรือ OUT
    - ตรวจซ้ำอัตโนมัติ (ไม่บันทึกถ้า IN/OUT วันนี้แล้ว)
    - OUT จะไม่บันทึกถ้ายังไม่มี IN วันนี้
    """
    if req.status not in ("IN", "OUT"):
        raise HTTPException(status_code=400, detail="status ต้องเป็น 'IN' หรือ 'OUT'")

    with get_connection() as conn:
        with conn.cursor() as cur:

            # ตรวจซ้ำ
            cur.execute("""
                SELECT 1 FROM attendance_logs
                WHERE per_id = %s
                  AND DATE(check_time) = CURRENT_DATE
                  AND status = %s
                LIMIT 1
            """, (req.per_id, req.status))
            if cur.fetchone():
                return {"success": False, "reason": f"วันนี้บันทึก {req.status} แล้ว"}

            # OUT ต้องมี IN ก่อน
            if req.status == "OUT":
                cur.execute("""
                    SELECT 1 FROM attendance_logs
                    WHERE per_id = %s
                      AND DATE(check_time) = CURRENT_DATE
                      AND status = 'IN'
                    LIMIT 1
                """, (req.per_id,))
                if not cur.fetchone():
                    return {"success": False, "reason": "ยังไม่มี IN วันนี้"}

            # บันทึก
            cur.execute("""
                INSERT INTO attendance_logs
                    (per_id, status, camera_name, check_time,
                     name, prename_th, per_name, per_surname,
                     posname_th, organize_th, organize_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                req.per_id, req.status, req.camera_name,
                req.check_time or datetime.now(),
                req.name, req.prename_th, req.per_name, req.per_surname,
                req.posname_th, req.organize_th, req.organize_id,
            ))

        conn.commit()

    return {"success": True, "per_id": req.per_id, "status": req.status}


@app.get("/person/{per_id}")
def get_person(per_id: str):
    """ดึงข้อมูลพนักงาน (รวม per_picpath) จาก external API ผ่าน api_client"""
    from api_client import fetch_person_by_pid
    data = fetch_person_by_pid(per_id)
    if not data:
        raise HTTPException(status_code=404, detail="Person not found")
    return {
        "per_id":      data.get("per_id", per_id),
        "name":        data.get("name", ""),
        "prename_th":  data.get("prename_th", ""),
        "per_name":    data.get("per_name", ""),
        "per_surname": data.get("per_surname", ""),
        "posname_th":  data.get("posname_th", ""),
        "organize_th": data.get("organize_th", ""),
        "per_picpath": data.get("per_picpath", ""),
    }


@app.get("/attendance/today/check")
def check_attendance_today(
    per_id: str = Query(...),
    status: str = Query(...)
):
    """ตรวจว่าวันนี้บันทึก IN/OUT แล้วหรือยัง"""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT 1 FROM attendance_logs
                WHERE per_id = %s
                  AND DATE(check_time) = CURRENT_DATE
                  AND status = %s
                LIMIT 1
            """, (per_id, status))
            marked = cur.fetchone() is not None
    return {"marked": marked, "per_id": per_id, "status": status}


@app.get("/attendance/today")
def attendance_today():
    """รายการลงเวลาวันนี้ทั้งหมด (สำหรับ Dashboard)"""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, per_id, name, prename_th, per_name, per_surname,
                       posname_th, organize_th, organize_id,
                       status, camera_name, check_time
                FROM attendance_logs
                WHERE DATE(check_time) = CURRENT_DATE
                ORDER BY check_time DESC
            """)
            rows = cur.fetchall()

    return [
        {
            "id":          r[0],
            "per_id":      r[1],
            "name":        r[2],
            "prename_th":  r[3],
            "per_name":    r[4],
            "per_surname": r[5],
            "posname_th":  r[6],
            "organize_th": r[7],
            "organize_id": r[8],
            "status":      r[9],
            "camera_name": r[10],
            "check_time":  r[11].isoformat() if r[11] else None,
        }
        for r in rows
    ]


@app.get("/attendance/{per_id}")
def attendance_by_person(
    per_id: str,
    start_date: Optional[date] = Query(None),
    end_date:   Optional[date] = Query(None),
):
    """ประวัติลงเวลาของพนักงาน กรองตามช่วงวันได้"""
    with get_connection() as conn:
        with conn.cursor() as cur:
            query = """
                SELECT id, name, prename_th, per_name, per_surname,
                       posname_th, organize_th, organize_id,
                       status, camera_name, check_time
                FROM attendance_logs
                WHERE per_id = %s
            """
            params = [per_id]

            if start_date:
                query += " AND DATE(check_time) >= %s"
                params.append(start_date)
            if end_date:
                query += " AND DATE(check_time) <= %s"
                params.append(end_date)

            query += " ORDER BY check_time DESC LIMIT 100"
            cur.execute(query, params)
            rows = cur.fetchall()

    return [
        {
            "id":          r[0],
            "name":        r[1],
            "prename_th":  r[2],
            "per_name":    r[3],
            "per_surname": r[4],
            "posname_th":  r[5],
            "organize_th": r[6],
            "organize_id": r[7],
            "status":      r[8],
            "camera_name": r[9],
            "check_time":  r[10].isoformat() if r[10] else None,
        }
        for r in rows
    ]


@app.put("/attendance/{log_id}", dependencies=[Depends(_require_admin)])
def update_attendance(log_id: int, req: AttendanceUpdateRequest):
    """แก้ไข record ลงเวลา — ส่งเฉพาะ field ที่ต้องการเปลี่ยน"""
    if req.status and req.status not in ("IN", "OUT"):
        raise HTTPException(status_code=400, detail="status ต้องเป็น 'IN' หรือ 'OUT'")

    fields = {k: v for k, v in req.model_dump().items() if v is not None}
    if not fields:
        raise HTTPException(status_code=400, detail="ไม่มี field ที่ต้องการแก้ไข")

    set_clause = ", ".join(f"{k} = %s" for k in fields)
    values = list(fields.values()) + [log_id]

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"UPDATE attendance_logs SET {set_clause} WHERE id = %s",
                values
            )
            if cur.rowcount == 0:
                raise HTTPException(status_code=404, detail="Attendance record not found")
        conn.commit()

    return {"success": True, "id": log_id, "updated": fields}


@app.delete("/attendance/{log_id}", dependencies=[Depends(_require_admin)])
def delete_attendance(log_id: int):
    """ลบ record ลงเวลา (ลบถาวร)"""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM attendance_logs WHERE id = %s", (log_id,))
            if cur.rowcount == 0:
                raise HTTPException(status_code=404, detail="Attendance record not found")
        conn.commit()

    return {"success": True, "id": log_id}
