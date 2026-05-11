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
from fastapi import FastAPI, HTTPException, Query, Depends, Header, Request
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, date
from db import get_connection

load_dotenv()

import auth as _auth   # ต้อง import หลัง load_dotenv (auth อ่าน JWT_SECRET ตอน import time)
import audit as _audit
import offline_queue as _oq   # offline fallback (Phase 2)

app = FastAPI(title="Face Attendance API", version="2.1.0")

_ADMIN_KEY = os.environ.get("ADMIN_API_KEY", "")


def _require_admin(
    authorization: Optional[str] = Header(None),
    x_admin_key:   Optional[str] = Header(None),
) -> dict:
    """Admin guard — รับได้ทั้ง 2 ทาง:
      1. Authorization: Bearer <JWT>  (role=admin)        — แนะนำ
      2. X-Admin-Key: <ADMIN_API_KEY>                     — legacy fallback
    """
    if authorization:
        user = _auth.get_current_user(authorization)
        if user.get("role") != "admin":
            raise HTTPException(status_code=403, detail="admin เท่านั้น")
        return user

    if _ADMIN_KEY and x_admin_key == _ADMIN_KEY:
        return {"id": 0, "username": "legacy_admin_key", "role": "admin"}

    raise HTTPException(
        status_code=401,
        detail="ต้องส่ง Authorization: Bearer <token> หรือ X-Admin-Key",
    )


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

            # บันทึก — ตัด microsecond ทิ้ง (เก็บแค่วินาที)
            ts = (req.check_time or datetime.now()).replace(microsecond=0)
            cur.execute("""
                INSERT INTO attendance_logs
                    (per_id, status, camera_name, check_time,
                     name, prename_th, per_name, per_surname,
                     posname_th, organize_th, organize_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                req.per_id, req.status, req.camera_name, ts,
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
    """รายการลงเวลาวันนี้ทั้งหมด (สำหรับ Dashboard)

    Fallback: ถ้า PG ดับ → อ่านจาก offline_queue.attendance_buf แทน
    (offline mode B — Phase 2) เพื่อให้ Dashboard ยัง render วันนี้ได้
    """
    try:
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
                "source":      "pg",
            }
            for r in rows
        ]
    except Exception as e:
        # PG ดับ → fallback ไป attendance_buf
        print(f"[API] /attendance/today PG error: {e} — falling back to attendance_buf")
        try:
            buf_rows = _oq.list_today()
        except Exception as buf_err:
            print(f"[API] attendance_buf fallback also failed: {buf_err}")
            raise HTTPException(status_code=503,
                                detail=f"PG down และ buffer อ่านไม่ได้: {buf_err}")
        return [
            {
                "id":          -int(r['id']),  # negative to signal buf origin
                "per_id":      r['per_id'],
                "name":        r['name'],
                "prename_th":  r['prename_th'],
                "per_name":    r['per_name'],
                "per_surname": r['per_surname'],
                "posname_th":  r['posname_th'],
                "organize_th": r['organize_th'],
                "organize_id": r['organize_id'],
                "status":      r['status'],
                "camera_name": r['camera_name'],
                "check_time":  r['check_time'],
                "source":      "buf",
                "synced":      bool(r['synced']),
            }
            for r in buf_rows
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


@app.put("/attendance/{log_id}")
def update_attendance(log_id: int, req: AttendanceUpdateRequest, request: Request,
                      user: dict = Depends(_require_admin)):
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

    _audit.log("attendance.update", user=user, target=f"log_id={log_id}",
               request=request, fields=list(fields.keys()))
    return {"success": True, "id": log_id, "updated": fields}


@app.delete("/attendance/{log_id}")
def delete_attendance(log_id: int, request: Request,
                      user: dict = Depends(_require_admin)):
    """ลบ record ลงเวลา (ลบถาวร)"""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM attendance_logs WHERE id = %s", (log_id,))
            if cur.rowcount == 0:
                raise HTTPException(status_code=404, detail="Attendance record not found")
        conn.commit()

    _audit.log("attendance.delete", user=user, target=f"log_id={log_id}",
               request=request)
    return {"success": True, "id": log_id}


# ╔═══════════════════════════════════════════════════════════════════════════╗
# ║  History & Report Endpoints                                                ║
# ╚═══════════════════════════════════════════════════════════════════════════╝

def _history_where(start: Optional[date], end: Optional[date],
                   organize_id: Optional[str], per_id: Optional[str],
                   camera_name: Optional[str]) -> tuple[str, list]:
    """สร้าง WHERE clause + params สำหรับ filter (ใช้ร่วมกันหลาย endpoint)"""
    clauses, params = [], []
    if start:
        clauses.append("DATE(check_time) >= %s"); params.append(start)
    if end:
        clauses.append("DATE(check_time) <= %s"); params.append(end)
    if organize_id:
        clauses.append("organize_id = %s"); params.append(organize_id)
    if per_id:
        clauses.append("per_id = %s"); params.append(per_id)
    if camera_name:
        clauses.append("camera_name = %s"); params.append(camera_name)
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    return where, params


def _fetch_history_rows(start: Optional[date], end: Optional[date],
                       organize_id: Optional[str], per_id: Optional[str],
                       camera_name: Optional[str]) -> list[dict]:
    where, params = _history_where(start, end, organize_id, per_id, camera_name)
    sql = f"""
        SELECT id, per_id, name, prename_th, per_name, per_surname,
               posname_th, organize_th, organize_id,
               status, camera_name, check_time
        FROM attendance_logs
        {where}
        ORDER BY check_time DESC
        LIMIT 5000
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
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


@app.get("/history")
def history(
    from_:        Optional[date] = Query(None, alias="from"),
    to:           Optional[date] = Query(None),
    organize_id:  Optional[str]  = Query(None),
    per_id:       Optional[str]  = Query(None),
    camera_name:  Optional[str]  = Query(None),
):
    """ประวัติลงเวลา filter ตามช่วงวัน/แผนก/บุคคล/กล้อง — group by date"""
    rows = _fetch_history_rows(from_, to, organize_id, per_id, camera_name)
    grouped: dict[str, list] = {}
    for r in rows:
        ct = r.get("check_time") or ""
        d = ct[:10] if ct else "unknown"
        grouped.setdefault(d, []).append(r)
    days = [{"date": d, "logs": grouped[d]} for d in sorted(grouped, reverse=True)]
    return {"total": len(rows), "days": days}


@app.get("/history/filters")
def history_filters():
    """รายการ filter (แผนก/บุคคล/กล้อง) สำหรับ dropdown — distinct จาก attendance_logs"""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT DISTINCT organize_id, organize_th
                FROM attendance_logs
                WHERE organize_id IS NOT NULL AND organize_id <> ''
                ORDER BY organize_th
            """)
            depts = [{"id": r[0], "name": r[1]} for r in cur.fetchall()]
            cur.execute("""
                SELECT DISTINCT per_id, name
                FROM attendance_logs
                WHERE per_id IS NOT NULL AND per_id <> ''
                ORDER BY name
                LIMIT 1000
            """)
            persons = [{"per_id": r[0], "name": r[1]} for r in cur.fetchall()]
            cur.execute("""
                SELECT DISTINCT camera_name
                FROM attendance_logs
                WHERE camera_name IS NOT NULL AND camera_name <> ''
                ORDER BY camera_name
            """)
            cameras = [r[0] for r in cur.fetchall()]
    return {"departments": depts, "persons": persons, "cameras": cameras}


@app.get("/report/summary")
def report_summary(
    from_:        Optional[date] = Query(None, alias="from"),
    to:           Optional[date] = Query(None),
    organize_id:  Optional[str]  = Query(None),
    per_id:       Optional[str]  = Query(None),
    camera_name:  Optional[str]  = Query(None),
):
    """สรุปสถิติ: ลงครบ (IN+OUT), เข้าอย่างเดียว, ออกอย่างเดียว — group by per_id+date"""
    where, params = _history_where(from_, to, organize_id, per_id, camera_name)
    sql = f"""
        SELECT per_id, name, organize_th,
               DATE(check_time) AS d,
               BOOL_OR(status='IN')  AS has_in,
               BOOL_OR(status='OUT') AS has_out,
               COUNT(*) AS n_logs
        FROM attendance_logs
        {where}
        GROUP BY per_id, name, organize_th, DATE(check_time)
        ORDER BY d DESC, name
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()

    complete = in_only = out_only = 0
    by_dept: dict[str, dict] = {}
    by_day:  dict[str, dict] = {}
    items = []
    for per_id_, name, dept, d, has_in, has_out, n in rows:
        if has_in and has_out:    cat, complete  = "complete", complete + 1
        elif has_in:              cat, in_only   = "in_only",  in_only  + 1
        else:                     cat, out_only  = "out_only", out_only + 1
        items.append({
            "per_id": per_id_, "name": name, "organize_th": dept,
            "date":   d.isoformat() if d else None,
            "has_in": bool(has_in), "has_out": bool(has_out),
            "n_logs": n, "category": cat,
        })
        d_key = d.isoformat() if d else "unknown"
        by_day.setdefault(d_key, {"complete":0,"in_only":0,"out_only":0})
        by_day[d_key][cat] += 1
        dept_key = dept or "—"
        by_dept.setdefault(dept_key, {"complete":0,"in_only":0,"out_only":0})
        by_dept[dept_key][cat] += 1

    return {
        "totals": {
            "complete": complete, "in_only": in_only, "out_only": out_only,
            "total_person_days": len(rows),
        },
        "by_day":  [{"date": k, **v} for k, v in sorted(by_day.items(), reverse=True)],
        "by_dept": [{"organize_th": k, **v} for k, v in sorted(by_dept.items())],
        "items":   items,
    }


@app.get("/report/export")
def report_export(
    format:       str            = Query("csv", pattern="^(csv|xlsx|pdf)$"),
    from_:        Optional[date] = Query(None, alias="from"),
    to:           Optional[date] = Query(None),
    organize_id:  Optional[str]  = Query(None),
    per_id:       Optional[str]  = Query(None),
    camera_name:  Optional[str]  = Query(None),
):
    """Export ประวัติลงเวลาเป็น CSV / XLSX / PDF (filter เดียวกับ /history)"""
    from fastapi.responses import StreamingResponse
    import io

    rows = _fetch_history_rows(from_, to, organize_id, per_id, camera_name)
    fname = f"attendance_{(from_ or '').__str__()}_{(to or '').__str__()}".strip("_")
    headers = ["check_time", "date", "time", "per_id", "name",
               "organize_th", "posname_th", "status", "camera_name"]

    def _row_values(r: dict) -> list:
        ct = r.get("check_time") or ""
        d  = ct[:10] if ct else ""
        t  = ct[11:19] if len(ct) >= 19 else ""
        return [ct, d, t, r.get("per_id",""), r.get("name",""),
                r.get("organize_th",""), r.get("posname_th",""),
                r.get("status",""), r.get("camera_name","")]

    if format == "csv":
        import csv
        buf = io.StringIO()
        # BOM เพื่อให้ Excel เปิดภาษาไทยถูก
        buf.write("﻿")
        w = csv.writer(buf)
        w.writerow(headers)
        for r in rows:
            w.writerow(_row_values(r))
        data = buf.getvalue().encode("utf-8")
        return StreamingResponse(
            io.BytesIO(data), media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{fname}.csv"'},
        )

    if format == "xlsx":
        try:
            from openpyxl import Workbook
        except ImportError:
            raise HTTPException(500, "ต้องติดตั้ง openpyxl: pip install openpyxl")
        wb = Workbook()
        ws = wb.active
        ws.title = "Attendance"
        ws.append(headers)
        for r in rows:
            ws.append(_row_values(r))
        for col in range(1, len(headers) + 1):
            ws.column_dimensions[chr(64 + col)].width = 18
        out = io.BytesIO()
        wb.save(out); out.seek(0)
        return StreamingResponse(
            out, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f'attachment; filename="{fname}.xlsx"'},
        )

    # pdf
    try:
        from reportlab.lib.pagesizes import A4, landscape
        from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
        from reportlab.lib.styles import ParagraphStyle
        from reportlab.lib import colors
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
    except ImportError:
        raise HTTPException(500, "ต้องติดตั้ง reportlab: pip install reportlab")

    # โหลดฟอนต์ไทย — เลือกฟอนต์ที่ครอบคลุมทั้ง Latin + Thai
    # NotoSansThai มีแค่ glyph ภาษาไทย ตัวเลข/Latin จะหาย → ใช้ Sarabun/Garuda ที่ครบ
    # priority: Sarabun (TLWG) → Garuda (TLWG) → NotoSansThai (fallback)
    font_name = "Helvetica"
    bold_name = "Helvetica-Bold"
    THAI_FONTS = [
        ("Sarabun", "/usr/share/fonts/truetype/thai-tlwg/Sarabun.ttf",
                    "/usr/share/fonts/truetype/thai-tlwg/Sarabun-Bold.ttf"),
        ("Sarabun", "/usr/share/fonts/truetype/tlwg/Sarabun.ttf",
                    "/usr/share/fonts/truetype/tlwg/Sarabun-Bold.ttf"),
        ("Garuda",  "/usr/share/fonts/truetype/tlwg/Garuda.ttf",
                    "/usr/share/fonts/truetype/tlwg/Garuda-Bold.ttf"),
        ("NotoTH",  "/usr/share/fonts/truetype/noto/NotoSansThai-Regular.ttf",
                    "/usr/share/fonts/truetype/noto/NotoSansThai-Bold.ttf"),
    ]
    for name, reg_path, bold_path in THAI_FONTS:
        if os.path.exists(reg_path):
            try:
                pdfmetrics.registerFont(TTFont(name, reg_path))
                bold_id = name + "-Bold"
                if os.path.exists(bold_path):
                    pdfmetrics.registerFont(TTFont(bold_id, bold_path))
                else:
                    bold_id = name
                pdfmetrics.registerFontFamily(name, normal=name, bold=bold_id)
                font_name = name
                bold_name = bold_id
                break
            except Exception:
                pass

    # styles — ทุก cell ใช้ Paragraph ที่ระบุ fontName ตรงๆ → ภาษาไทยไม่เพี้ยน
    title_style  = ParagraphStyle("title",  fontName=bold_name, fontSize=14, leading=18,
                                   spaceAfter=8, textColor=colors.HexColor("#111111"))
    header_style = ParagraphStyle("header", fontName=bold_name, fontSize=8,  leading=10,
                                   textColor=colors.whitesmoke)
    cell_style   = ParagraphStyle("cell",   fontName=font_name, fontSize=8,  leading=10,
                                   textColor=colors.HexColor("#222222"))

    def _cell(text, style=cell_style):
        # escape XML special chars
        s = (str(text) if text is not None else "")
        s = s.replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")
        return Paragraph(s, style)

    out = io.BytesIO()
    doc = SimpleDocTemplate(out, pagesize=landscape(A4),
                            leftMargin=24, rightMargin=24, topMargin=24, bottomMargin=24)

    title = f"รายงานประวัติลงเวลา ({from_ or '-'} ถึง {to or '-'}) — {len(rows)} รายการ"

    # ทุก cell ห่อ Paragraph (ภาษาไทย render ผ่าน Paragraph ดีกว่า raw string)
    table_data = [
        [_cell(h, header_style) for h in headers]
    ] + [
        [_cell(v) for v in _row_values(r)] for r in rows
    ]
    tbl = Table(table_data, repeatRows=1)
    tbl.setStyle(TableStyle([
        ("BACKGROUND",    (0,0), (-1,0), colors.HexColor("#222222")),
        ("GRID",          (0,0), (-1,-1), 0.25, colors.grey),
        ("ROWBACKGROUNDS",(0,1), (-1,-1), [colors.whitesmoke, colors.HexColor("#f4f4f4")]),
        ("VALIGN",        (0,0), (-1,-1), "MIDDLE"),
        ("LEFTPADDING",   (0,0), (-1,-1), 4),
        ("RIGHTPADDING",  (0,0), (-1,-1), 4),
        ("TOPPADDING",    (0,0), (-1,-1), 3),
        ("BOTTOMPADDING", (0,0), (-1,-1), 3),
    ]))
    doc.build([Paragraph(title, title_style), Spacer(1, 6), tbl])
    out.seek(0)
    return StreamingResponse(
        out, media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{fname}.pdf"'},
    )
