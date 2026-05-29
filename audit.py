"""
audit.py — เขียน event เข้า audit_logs

ใช้:
    import audit
    audit.log("auth.login.success", user=user, request=request)
    audit.log("camera.delete", user=user, target=cam_id, request=request,
              prev_config={"name": "...", "url": "..."})

หลักการ:
- log() ห้าม raise — ถ้า DB ดับก็แค่ print warning แล้ว return
  (จะ break flow user ไม่ได้)
- success=False เป็นพารามิเตอร์ keyword สำหรับ event ล้มเหลว
- request: FastAPI Request — ดึง IP + User-Agent อัตโนมัติ
- ส่วน details ใช้ kwargs — แปลงเป็น JSONB
"""
from __future__ import annotations
import json
from typing import Optional, Any

from db import get_connection


_INSERT_SQL = """
    INSERT INTO audit_logs (user_id, username, action, target, ip, user_agent, details, success)
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
"""


def _extract_request_meta(request) -> tuple[Optional[str], Optional[str]]:
    """ดึง IP + User-Agent จาก FastAPI Request (None ถ้าไม่ส่ง request)"""
    if request is None:
        return None, None
    try:
        ip = request.client.host if request.client else None
    except Exception:
        ip = None
    ua = (request.headers.get("user-agent", "") or "")[:255] or None
    return ip, ua


def log(
    action: str,
    *,
    user: Optional[dict] = None,
    target: Optional[str] = None,
    request: Any = None,
    success: bool = True,
    **details,
) -> None:
    """บันทึก event เข้า audit_logs — swallow exceptions (ไม่ break user request)"""
    ip, ua = _extract_request_meta(request)
    user_id  = (user or {}).get("id")
    username = (user or {}).get("username")
    details_json = json.dumps(details, default=str, ensure_ascii=False) if details else None

    try:
        with get_connection() as conn, conn.cursor() as cur:
            cur.execute(_INSERT_SQL, (
                user_id, username, action, target, ip, ua, details_json, success,
            ))
            conn.commit()
    except Exception as e:
        print(f"[AUDIT] failed to log {action!r} for {username!r}: {e}")


def fetch(
    limit:     int = 100,
    offset:    int = 0,
    action:    Optional[str] = None,
    user_id:   Optional[int] = None,
    since:     Optional[str] = None,    # ISO date 'YYYY-MM-DD'
    until:     Optional[str] = None,
    success:   Optional[bool] = None,
) -> list[dict]:
    """ดู audit log — ใช้จาก /audit/logs endpoint (admin only)"""
    clauses, params = [], []
    if action:
        clauses.append("action = %s");        params.append(action)
    if user_id:
        clauses.append("user_id = %s");       params.append(user_id)
    if since:
        clauses.append("ts >= %s::date");     params.append(since)
    if until:
        clauses.append("ts <  (%s::date + INTERVAL '1 day')"); params.append(until)
    if success is not None:
        clauses.append("success = %s");       params.append(success)

    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    sql = (
        f"SELECT id, ts, user_id, username, action, target, ip, user_agent, details, success "
        f"FROM audit_logs {where} "
        f"ORDER BY ts DESC, id DESC "
        f"LIMIT %s OFFSET %s"
    )
    params.extend([limit, offset])

    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(sql, params)
        rows = cur.fetchall()

    return [
        {
            "id":         r[0],
            "ts":         r[1].isoformat() if r[1] else None,
            "user_id":    r[2],
            "username":   r[3],
            "action":     r[4],
            "target":     r[5],
            "ip":         r[6],
            "user_agent": r[7],
            "details":    r[8],
            "success":    r[9],
        }
        for r in rows
    ]
