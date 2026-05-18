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
import json as _json
import hashlib
import asyncio as _asyncio
from dotenv import load_dotenv
import jwt as _jwt
from fastapi import FastAPI, HTTPException, Query, Depends, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime, date, timedelta
from db import get_connection

load_dotenv()

app = FastAPI(title="Face Attendance API", version="2.0.0")

# ── Startup: เริ่ม background scheduler ──────────────────────────────────────
@app.on_event("startup")
async def _startup():
    _asyncio.create_task(_mode_watcher_task())

# ── Active Windows (อ่านจาก config.py เหมือน main.py) ────────────────────────
try:
    import config as _face_cfg
    _ACTIVE_WINDOWS = _face_cfg.ACTIVE_WINDOWS
except Exception:
    from datetime import time as _dtime
    _ACTIVE_WINDOWS = [(_dtime(5, 0), _dtime(22, 0))]

def _api_in_active_window(t) -> bool:
    """ตรวจว่าเวลา t อยู่ใน Active Window (เหมือน _in_active_window ใน main.py)"""
    for start, end in _ACTIVE_WINDOWS:
        if start <= end:
            if start <= t < end:
                return True
        else:                    # ข้ามเที่ยงคืน
            if t >= start or t < end:
                return True
    return False

# ── CORS ──────────────────────────────────────────────────────────────────────
# อนุญาต Vue dev server (port 5173) เรียก API ได้ระหว่าง development
# ในโหมด production ถ้า serve dashboard จาก FastAPI เองไม่ต้องใช้ CORS
# เพิ่ม origin อื่นๆ ได้ใน allow_origins list
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",    # Vue dev server (default port)
        "http://127.0.0.1:5173",
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Static files (Dashboard build output) ────────────────────────────────────
# หลังจาก `npm run build` ใน dashboard/ แล้ว ไฟล์จะอยู่ที่ static/
# FastAPI จะเสิร์ฟ dashboard ที่  http://localhost:8000/dashboard/
# ถ้ายังไม่ได้ build ให้ comment 2 บรรทัดนี้ออกก่อน
import pathlib
_ROOT = pathlib.Path(__file__).parent

# ── Frame/State files directory ───────────────────────────────────────────────
# ปกติเก็บใน _ROOT/live/ เพื่อไม่ให้ไฟล์ live_* กระจายใน root
# บน Docker ตั้ง FACE_FRAMES_DIR=/tmp/frames เพื่อใช้ tmpfs (RAM) แทน disk
# → กำจัด I/O jitter ที่ทำให้ MJPEG stream กระตุก
_FRAMES_DIR = pathlib.Path(os.environ.get("FACE_FRAMES_DIR", str(_ROOT / "live")))
_FRAMES_DIR.mkdir(parents=True, exist_ok=True)

# ── Dashboard static files (Vue build output) ────────────────────────────────
_static_dir = _ROOT / "static"
if _static_dir.exists():
    app.mount("/dashboard", StaticFiles(directory=_static_dir, html=True), name="dashboard")

# ── PicSAVE: serve รูป snapshot จาก main.py ──────────────────────────────────
# รูปเก็บที่ PicSAVE/YYYY/MM/DD/HH-MM-SS_{per_id}_IN.jpg
# เข้าถึงได้ที่ /snapshots/2026/04/07/08-30-00_1234567890123_IN.jpg
_picsave_dir = _ROOT / "PicSAVE"
if _picsave_dir.exists():
    app.mount("/snapshots", StaticFiles(directory=_picsave_dir), name="snapshots")

@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse(url="/dashboard/")

@app.get("/api/session/live", include_in_schema=False)
def session_live_compat():
    """Alias: /api/session/live → /session/live (compat — deprecated, ไม่ต้อง auth)"""
    from fastapi.responses import JSONResponse
    return JSONResponse({"active": False, "persons": [], "stale": True, "ts": 0})


# ╔═══════════════════════════════════════════════════════════════════════════╗
# ║  JWT Authentication & RBAC                                               ║
# ╚═══════════════════════════════════════════════════════════════════════════╝

_JWT_SECRET = os.environ.get("JWT_SECRET_KEY", "dev-secret-please-change-in-production")
_JWT_ALGO   = "HS256"
_JWT_EXPIRE = timedelta(hours=8)

_bearer = HTTPBearer(auto_error=False)

PERMISSIONS_META = {
    "attendance.view":   "ดูรายการลงเวลา",
    "attendance.clear":  "ล้างข้อมูลวันนี้",
    "cameras.view":      "ดูกล้องและ Live Feed",
    "cameras.manage":    "จัดการกล้อง (เพิ่ม/ลบ/แก้ไข)",
    "users.manage":      "จัดการผู้ใช้และ Roles",
}


def _hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()


def _create_token(sub: str, role: str, display_name: str, permissions: list) -> str:
    payload = {
        "sub":          sub,
        "role":         role,
        "display_name": display_name,
        "permissions":  permissions,
        "exp":          datetime.utcnow() + _JWT_EXPIRE,
    }
    return _jwt.encode(payload, _JWT_SECRET, algorithm=_JWT_ALGO)


def _decode_token(token: str) -> dict:
    return _jwt.decode(token, _JWT_SECRET, algorithms=[_JWT_ALGO])


def _has_permission(user: dict, permission: str) -> bool:
    perms = user.get("permissions", [])
    return "*" in perms or permission in perms


def _require_auth(cred: HTTPAuthorizationCredentials = Depends(_bearer)) -> dict:
    if not cred:
        raise HTTPException(status_code=401, detail="ต้องเข้าสู่ระบบก่อน")
    try:
        return _decode_token(cred.credentials)
    except _jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Session หมดอายุ กรุณาเข้าสู่ระบบใหม่")
    except Exception:
        raise HTTPException(status_code=401, detail="Token ไม่ถูกต้อง")


def _require_perm(permission: str):
    def _dep(user: dict = Depends(_require_auth)):
        if not _has_permission(user, permission):
            raise HTTPException(status_code=403, detail=f"ไม่มีสิทธิ์: {permission}")
        return user
    return _dep


def _require_admin(user: dict = Depends(_require_auth)):
    if not _has_permission(user, "users.manage"):
        raise HTTPException(status_code=403, detail="ต้องมีสิทธิ์ users.manage")
    return user


def _assert_superadmin_survives(cur, exclude_role_id=None, exclude_user_id=None):
    """ตรวจว่ายังมี Role ที่มี ['*'] และมีผู้ใช้ active อย่างน้อย 1 คนหลังการเปลี่ยนแปลง"""
    if exclude_role_id is not None:
        cur.execute(
            "SELECT id FROM dashboard_roles WHERE permissions @> '[\"*\"]'::jsonb AND id != %s",
            (exclude_role_id,)
        )
    else:
        cur.execute("SELECT id FROM dashboard_roles WHERE permissions @> '[\"*\"]'::jsonb")
    super_role_ids = [r[0] for r in cur.fetchall()]
    if not super_role_ids:
        raise HTTPException(status_code=400,
            detail="ต้องมี Role ที่มีสิทธิ์ทั้งหมด (*) อย่างน้อย 1 Role เสมอ")
    placeholders = ', '.join(['%s'] * len(super_role_ids))
    params: list = super_role_ids[:]
    extra = ""
    if exclude_user_id is not None:
        extra = " AND id != %s"
        params.append(exclude_user_id)
    cur.execute(
        f"SELECT COUNT(*) FROM dashboard_users WHERE role_id IN ({placeholders}) AND is_active = TRUE{extra}",
        params
    )
    if cur.fetchone()[0] == 0:
        raise HTTPException(status_code=400,
            detail="ต้องมีผู้ใช้ที่ active อย่างน้อย 1 คนใน Role ที่มีสิทธิ์ทั้งหมด (*) เสมอ")


def _init_auth_tables():
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS dashboard_roles (
                    id           SERIAL PRIMARY KEY,
                    name         VARCHAR(50)  UNIQUE NOT NULL,
                    display_name VARCHAR(100) NOT NULL,
                    permissions  JSONB        NOT NULL DEFAULT '[]'
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS dashboard_users (
                    id            SERIAL PRIMARY KEY,
                    username      VARCHAR(50)  UNIQUE NOT NULL,
                    password_hash VARCHAR(255) NOT NULL,
                    display_name  VARCHAR(100) NOT NULL,
                    role_id       INTEGER REFERENCES dashboard_roles(id) ON DELETE SET NULL,
                    is_active     BOOLEAN DEFAULT TRUE,
                    created_at    TIMESTAMPTZ DEFAULT NOW()
                )
            """)
            cur.execute("SELECT COUNT(*) FROM dashboard_roles")
            if cur.fetchone()[0] == 0:
                cur.execute("""
                    INSERT INTO dashboard_roles (name, display_name, permissions) VALUES
                    ('admin',  'ผู้ดูแลระบบ',   '["*"]'::jsonb),
                    ('viewer', 'ผู้ดูรายงาน', '["attendance.view","cameras.view"]'::jsonb)
                """)
            cur.execute("SELECT COUNT(*) FROM dashboard_users")
            if cur.fetchone()[0] == 0:
                cur.execute("""
                    INSERT INTO dashboard_users (username, password_hash, display_name, role_id)
                    SELECT 'admin',  %s, 'ผู้ดูแลระบบ',  id FROM dashboard_roles WHERE name='admin'
                """, (_hash_password("admin1234"),))
                cur.execute("""
                    INSERT INTO dashboard_users (username, password_hash, display_name, role_id)
                    SELECT 'viewer', %s, 'ผู้ดูรายงาน', id FROM dashboard_roles WHERE name='viewer'
                """, (_hash_password("viewer1234"),))
        conn.commit()

try:
    _init_auth_tables()
    print("[AUTH] Auth tables ready")
except Exception as _e:
    print(f"[AUTH] Warning: could not init auth tables: {_e}")


# ╔═══════════════════════════════════════════════════════════════════════════╗
# ║  Auth Endpoints                                                           ║
# ╚═══════════════════════════════════════════════════════════════════════════╝

class LoginRequest(BaseModel):
    username: str
    password: str

@app.post("/auth/login")
def auth_login(req: LoginRequest):
    """เข้าสู่ระบบ — คืน JWT token"""
    pw_hash = _hash_password(req.password)
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT u.id, u.username, u.display_name, u.is_active,
                       r.name AS role, r.permissions
                FROM dashboard_users u
                LEFT JOIN dashboard_roles r ON u.role_id = r.id
                WHERE u.username = %s AND u.password_hash = %s
            """, (req.username, pw_hash))
            row = cur.fetchone()

    if not row:
        raise HTTPException(status_code=401, detail="ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง")

    _id, username, display_name, is_active, role, permissions = row
    if not is_active:
        raise HTTPException(status_code=403, detail="บัญชีนี้ถูกระงับการใช้งาน")

    perms = permissions if isinstance(permissions, list) else []
    token = _create_token(username, role or "", display_name, perms)
    return {
        "token":        token,
        "username":     username,
        "display_name": display_name,
        "role":         role,
        "permissions":  perms,
    }


@app.get("/auth/me")
def auth_me(user: dict = Depends(_require_auth)):
    """ดึง permission ล่าสุดจาก DB (ไม่ใช่จาก token) เพื่อให้ frontend sync เสมอ"""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT u.display_name, r.name, r.permissions
                FROM dashboard_users u
                JOIN dashboard_roles r ON u.role_id = r.id
                WHERE u.username = %s AND u.is_active = TRUE
            """, (user["sub"],))
            row = cur.fetchone()
    if not row:
        raise HTTPException(status_code=401, detail="ผู้ใช้ถูกระงับหรือไม่มีในระบบ")
    display_name, role, permissions = row
    return {
        "username":     user["sub"],
        "display_name": display_name,
        "role":         role,
        "permissions":  permissions if isinstance(permissions, list) else [],
    }


# ╔═══════════════════════════════════════════════════════════════════════════╗
# ║  RBAC Management Endpoints (users.manage permission required)             ║
# ╚═══════════════════════════════════════════════════════════════════════════╝

@app.get("/admin/permissions")
def list_permissions(_: dict = Depends(_require_perm("users.manage"))):
    """รายการ permissions ทั้งหมดในระบบ"""
    return [{"key": k, "label": v} for k, v in PERMISSIONS_META.items()]


# ── Roles ────────────────────────────────────────────────────────────────────

@app.get("/admin/roles")
def list_roles(_: dict = Depends(_require_perm("users.manage"))):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT r.id, r.name, r.display_name, r.permissions,
                       COUNT(u.id) AS user_count
                FROM dashboard_roles r
                LEFT JOIN dashboard_users u ON u.role_id = r.id
                GROUP BY r.id ORDER BY r.id
            """)
            rows = cur.fetchall()
    return [
        {"id": r[0], "name": r[1], "display_name": r[2],
         "permissions": r[3], "user_count": r[4]}
        for r in rows
    ]


class RoleCreateBody(BaseModel):
    name:         str
    display_name: str
    permissions:  List[str] = []

@app.post("/admin/roles", status_code=201)
def create_role(body: RoleCreateBody, _: dict = Depends(_require_perm("users.manage"))):
    with get_connection() as conn:
        with conn.cursor() as cur:
            try:
                cur.execute("""
                    INSERT INTO dashboard_roles (name, display_name, permissions)
                    VALUES (%s, %s, %s::jsonb) RETURNING id
                """, (body.name.strip(), body.display_name.strip(),
                      _json.dumps(body.permissions)))
                new_id = cur.fetchone()[0]
            except Exception:
                raise HTTPException(status_code=409, detail="ชื่อ Role นี้มีอยู่แล้ว")
        conn.commit()
    return {"id": new_id, "name": body.name, "display_name": body.display_name,
            "permissions": body.permissions}


class RoleUpdateBody(BaseModel):
    display_name: Optional[str] = None
    permissions:  Optional[List[str]] = None

@app.put("/admin/roles/{role_id}")
def update_role(role_id: int, body: RoleUpdateBody,
                _: dict = Depends(_require_perm("users.manage"))):
    fields, vals = [], []
    if body.display_name is not None:
        fields.append("display_name = %s"); vals.append(body.display_name.strip())
    if body.permissions is not None:
        fields.append("permissions = %s::jsonb"); vals.append(_json.dumps(body.permissions))
    if not fields:
        raise HTTPException(status_code=400, detail="ไม่มีข้อมูลที่ต้องอัพเดต")
    vals.append(role_id)
    with get_connection() as conn:
        with conn.cursor() as cur:
            # ถ้าเปลี่ยน permissions และไม่มี * → ตรวจว่ายังมี superadmin role อื่น
            if body.permissions is not None and '*' not in body.permissions:
                _assert_superadmin_survives(cur, exclude_role_id=role_id)
            cur.execute(f"UPDATE dashboard_roles SET {', '.join(fields)} WHERE id = %s", vals)
            if cur.rowcount == 0:
                raise HTTPException(status_code=404, detail="ไม่พบ Role")
        conn.commit()
    return {"ok": True}


@app.delete("/admin/roles/{role_id}")
def delete_role(role_id: int, _: dict = Depends(_require_perm("users.manage"))):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM dashboard_users WHERE role_id = %s", (role_id,))
            if cur.fetchone()[0] > 0:
                raise HTTPException(status_code=409,
                    detail="ไม่สามารถลบ Role ที่มีผู้ใช้อยู่ได้ กรุณาเปลี่ยน Role ผู้ใช้ก่อน")
            _assert_superadmin_survives(cur, exclude_role_id=role_id)
            cur.execute("DELETE FROM dashboard_roles WHERE id = %s", (role_id,))
            if cur.rowcount == 0:
                raise HTTPException(status_code=404, detail="ไม่พบ Role")
        conn.commit()
    return {"ok": True}


# ── Users ────────────────────────────────────────────────────────────────────

@app.get("/admin/users")
def list_users(_: dict = Depends(_require_perm("users.manage"))):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT u.id, u.username, u.display_name, u.is_active,
                       u.created_at, r.id AS role_id, r.name AS role_name,
                       r.display_name AS role_display
                FROM dashboard_users u
                LEFT JOIN dashboard_roles r ON u.role_id = r.id
                ORDER BY u.id
            """)
            rows = cur.fetchall()
    return [
        {
            "id":           r[0],
            "username":     r[1],
            "display_name": r[2],
            "is_active":    r[3],
            "created_at":   r[4].isoformat() if r[4] else None,
            "role_id":      r[5],
            "role_name":    r[6],
            "role_display": r[7],
        }
        for r in rows
    ]


class UserCreateBody(BaseModel):
    username:     str
    password:     str
    display_name: str
    role_id:      int
    is_active:    bool = True

@app.post("/admin/users", status_code=201)
def create_user(body: UserCreateBody, _: dict = Depends(_require_perm("users.manage"))):
    if len(body.password) < 6:
        raise HTTPException(status_code=400, detail="รหัสผ่านต้องมีอย่างน้อย 6 ตัวอักษร")
    with get_connection() as conn:
        with conn.cursor() as cur:
            try:
                cur.execute("""
                    INSERT INTO dashboard_users
                        (username, password_hash, display_name, role_id, is_active)
                    VALUES (%s, %s, %s, %s, %s) RETURNING id
                """, (body.username.strip(), _hash_password(body.password),
                      body.display_name.strip(), body.role_id, body.is_active))
                new_id = cur.fetchone()[0]
            except Exception:
                raise HTTPException(status_code=409, detail="ชื่อผู้ใช้นี้มีอยู่แล้ว")
        conn.commit()
    return {"id": new_id, "username": body.username, "display_name": body.display_name}


class UserUpdateBody(BaseModel):
    display_name: Optional[str] = None
    role_id:      Optional[int] = None
    is_active:    Optional[bool] = None

@app.put("/admin/users/{user_id}")
def update_user(user_id: int, body: UserUpdateBody,
                current: dict = Depends(_require_perm("users.manage"))):
    fields, vals = [], []
    if body.display_name is not None:
        fields.append("display_name = %s"); vals.append(body.display_name.strip())
    if body.role_id is not None:
        fields.append("role_id = %s"); vals.append(body.role_id)
    if body.is_active is not None:
        # ห้าม deactivate ตัวเอง
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT username FROM dashboard_users WHERE id = %s", (user_id,))
                row = cur.fetchone()
        if row and row[0] == current["sub"] and not body.is_active:
            raise HTTPException(status_code=400, detail="ไม่สามารถระงับบัญชีของตัวเองได้")
        fields.append("is_active = %s"); vals.append(body.is_active)
    if not fields:
        raise HTTPException(status_code=400, detail="ไม่มีข้อมูลที่ต้องอัพเดต")

    # ตรวจ superadmin constraint ถ้า deactivate หรือเปลี่ยน role
    if body.is_active is False or body.role_id is not None:
        with get_connection() as conn:
            with conn.cursor() as cur:
                if body.role_id is not None:
                    # เปลี่ยน role → ตรวจว่า role ใหม่มี * หรือเปล่า
                    cur.execute("SELECT permissions FROM dashboard_roles WHERE id = %s", (body.role_id,))
                    role_row = cur.fetchone()
                    new_perms = role_row[0] if role_row else []
                    if '*' not in (new_perms or []):
                        # role ใหม่ไม่ใช่ superadmin → ตรวจว่ายังมี superadmin user อื่น
                        _assert_superadmin_survives(cur, exclude_user_id=user_id)
                else:
                    # แค่ deactivate → ตรวจว่ายังมี superadmin user active อื่น
                    _assert_superadmin_survives(cur, exclude_user_id=user_id)

    vals.append(user_id)
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(f"UPDATE dashboard_users SET {', '.join(fields)} WHERE id = %s", vals)
            if cur.rowcount == 0:
                raise HTTPException(status_code=404, detail="ไม่พบผู้ใช้")
        conn.commit()
    return {"ok": True}


class PasswordResetBody(BaseModel):
    new_password: str

@app.post("/admin/users/{user_id}/reset-password")
def reset_user_password(user_id: int, body: PasswordResetBody,
                        _: dict = Depends(_require_perm("users.manage"))):
    if len(body.new_password) < 6:
        raise HTTPException(status_code=400, detail="รหัสผ่านต้องมีอย่างน้อย 6 ตัวอักษร")
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE dashboard_users SET password_hash = %s WHERE id = %s",
                (_hash_password(body.new_password), user_id)
            )
            if cur.rowcount == 0:
                raise HTTPException(status_code=404, detail="ไม่พบผู้ใช้")
        conn.commit()
    return {"ok": True}


@app.delete("/admin/users/{user_id}")
def delete_user(user_id: int, current: dict = Depends(_require_perm("users.manage"))):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT username FROM dashboard_users WHERE id = %s", (user_id,))
            row = cur.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="ไม่พบผู้ใช้")
            if row[0] == current["sub"]:
                raise HTTPException(status_code=400, detail="ไม่สามารถลบบัญชีของตัวเองได้")
            _assert_superadmin_survives(cur, exclude_user_id=user_id)
            cur.execute("DELETE FROM dashboard_users WHERE id = %s", (user_id,))
        conn.commit()
    return {"ok": True}


@app.post("/auth/change-password")
def change_own_password(
    body: PasswordResetBody,
    current: dict = Depends(_require_auth)
):
    """เปลี่ยนรหัสผ่านของตัวเอง"""
    if len(body.new_password) < 6:
        raise HTTPException(status_code=400, detail="รหัสผ่านต้องมีอย่างน้อย 6 ตัวอักษร")
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE dashboard_users SET password_hash = %s WHERE username = %s",
                (_hash_password(body.new_password), current["sub"])
            )
        conn.commit()
    return {"ok": True}

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


@app.get("/attendance/today/check")
def check_attendance_today(
    per_id: str = Query(...),
    status: str = Query(...),
    _: dict = Depends(_require_perm("attendance.view")),
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
def attendance_today(_: dict = Depends(_require_perm("attendance.view"))):
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

    # ── Enrich records ที่ per_name ว่าง ──────────────────────────────
    # ถ้าตอน check-in ดึงชื่อจาก external API ไม่ได้ → ชื่อจะว่างใน DB
    # แก้โดย fetch ใหม่ต่อ per_id (cache ต่อ request) แล้ว update DB ด้วย
    from api_client import fetch_person_by_pid as _fetch
    _api_cache: dict = {}   # per_id → person dict (cache ภายใน request นี้)
    _to_update: list = []   # [(per_id, name, prename_th, per_name, per_surname, posname_th, organize_th, organize_id)]

    result = []
    for r in rows:
        rec = {
            "id":          r[0],
            "per_id":      r[1],
            "name":        r[2] or "",
            "prename_th":  r[3] or "",
            "per_name":    r[4] or "",
            "per_surname": r[5] or "",
            "posname_th":  r[6] or "",
            "organize_th": r[7] or "",
            "organize_id": r[8] or "",
            "status":      r[9],
            "camera_name": r[10],
            "check_time":  r[11].isoformat() if r[11] else None,
        }

        # enrich เฉพาะ record ที่ per_name ว่าง
        if not rec["per_name"] and rec["per_id"]:
            pid = rec["per_id"]
            if pid not in _api_cache:
                try:
                    _api_cache[pid] = _fetch(pid)
                except Exception:
                    _api_cache[pid] = None

            p = _api_cache.get(pid)
            if p:
                rec["name"]        = p.get("name", "")        or rec["name"]
                rec["prename_th"]  = p.get("prename_th", "")  or rec["prename_th"]
                rec["per_name"]    = p.get("per_name", "")    or rec["per_name"]
                rec["per_surname"] = p.get("per_surname", "") or rec["per_surname"]
                rec["posname_th"]  = p.get("posname_th", "")  or rec["posname_th"]
                rec["organize_th"] = p.get("organize_th", "") or rec["organize_th"]
                rec["organize_id"] = p.get("organize_id", "") or rec["organize_id"]
                # mark ให้ update DB ครั้งเดียวต่อ per_id (ไม่ update ซ้ำทุก record)
                if pid not in {u[0] for u in _to_update}:
                    _to_update.append((
                        rec["name"], rec["prename_th"], rec["per_name"],
                        rec["per_surname"], rec["posname_th"],
                        rec["organize_th"], rec["organize_id"], pid,
                    ))

        result.append(rec)

    # อัปเดต DB ครั้งเดียวสำหรับทุก per_id ที่ enrich ได้
    if _to_update:
        try:
            with get_connection() as conn:
                with conn.cursor() as cur:
                    cur.executemany("""
                        UPDATE attendance_logs
                        SET name=%s, prename_th=%s, per_name=%s, per_surname=%s,
                            posname_th=%s, organize_th=%s, organize_id=%s
                        WHERE per_id=%s
                          AND (per_name IS NULL OR per_name = '')
                    """, _to_update)
        except Exception:
            pass

    return result


@app.post("/attendance/checkout/{per_id}")
def manual_checkout(per_id: str, _: dict = Depends(_require_perm("attendance.clear"))):
    """
    ลงชื่อออกด้วยตนเองจาก Dashboard
    - ต้องมี IN วันนี้ก่อน
    - ถ้ามี OUT วันนี้แล้ว → แจ้งว่าซ้ำ
    - ใช้ชื่อ/หน่วยงานจาก IN record ล่าสุดของวันนี้
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT 1 FROM attendance_logs
                WHERE per_id = %s
                  AND DATE(check_time) = CURRENT_DATE
                  AND status = 'OUT'
                LIMIT 1
            """, (per_id,))
            if cur.fetchone():
                return {"success": False, "reason": "วันนี้ลงชื่อออกแล้ว"}

            cur.execute("""
                SELECT name, prename_th, per_name, per_surname,
                       posname_th, organize_th, organize_id, camera_name
                FROM attendance_logs
                WHERE per_id = %s
                  AND DATE(check_time) = CURRENT_DATE
                  AND status = 'IN'
                ORDER BY check_time DESC
                LIMIT 1
            """, (per_id,))
            row = cur.fetchone()
            if not row:
                return {"success": False, "reason": "ยังไม่มีการลงชื่อเข้าวันนี้"}

            name, prename_th, per_name, per_surname, posname_th, organize_th, organize_id, camera_name = row

            cur.execute("""
                INSERT INTO attendance_logs
                    (per_id, status, camera_name, check_time,
                     name, prename_th, per_name, per_surname,
                     posname_th, organize_th, organize_id)
                VALUES (%s, 'OUT', %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                per_id, camera_name or 'manual', datetime.now(),
                name, prename_th, per_name, per_surname,
                posname_th, organize_th, organize_id,
            ))
        conn.commit()

    return {"success": True, "per_id": per_id, "status": "OUT"}


@app.get("/attendance/{per_id}")
def attendance_by_person(
    per_id: str,
    start_date: Optional[date] = Query(None),
    end_date:   Optional[date] = Query(None),
    _: dict = Depends(_require_perm("attendance.view")),
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


@app.put("/attendance/{log_id}", dependencies=[Depends(_require_perm("attendance.clear"))])
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


@app.delete("/attendance/{log_id}", dependencies=[Depends(_require_perm("attendance.clear"))])
def delete_attendance(log_id: int):
    """ลบ record ลงเวลา (ลบถาวร)"""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM attendance_logs WHERE id = %s", (log_id,))
            if cur.rowcount == 0:
                raise HTTPException(status_code=404, detail="Attendance record not found")
        conn.commit()

    return {"success": True, "id": log_id}


@app.delete("/attendance/today/all", dependencies=[Depends(_require_perm("attendance.clear"))])
def clear_today_attendance():
    """
    ล้างข้อมูลการลงเวลาทั้งหมดของวันนี้ + session cache
    ─────────────────────────────────────────────────────────────────────
    ใช้สำหรับ testing เท่านั้น — ลบ attendance_logs ของวันนี้ทั้งหมด
    พร้อมลบ live_state.json และ live_frame.jpg เพื่อรีเซ็ต session

    ⚠ ไม่กระทบข้อมูลวันอื่น
    """
    import pathlib as _pl

    # ── ลบ attendance ของวันนี้ ────────────────────────────────────────
    deleted_rows = 0
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM attendance_logs WHERE DATE(check_time) = CURRENT_DATE"
            )
            deleted_rows = cur.rowcount
        conn.commit()

    # ── ลบ session cache files ─────────────────────────────────────────
    cache_cleared = []
    for p in (_pl.Path(__file__).parent / "live_state.json",
              _pl.Path(__file__).parent / "live_frame.jpg"):
        try:
            p.unlink(missing_ok=True)
            cache_cleared.append(p.name)
        except Exception:
            pass

    return {
        "success":       True,
        "deleted_rows":  deleted_rows,
        "cache_cleared": cache_cleared,
    }


# ╔═══════════════════════════════════════════════════════════════════════════╗
# ║  System Mode & Scheduler (Active Windows — เหมือน GUI main.py)            ║
# ╚═══════════════════════════════════════════════════════════════════════════╝

@app.get("/system/mode")
def system_mode():
    """
    คืนโหมดระบบปัจจุบันตาม ACTIVE_WINDOWS ใน config.py
      mode = "face" : อยู่ในช่วง Active Window → เปิด face recognition
      mode = "cctv" : นอกช่วง → โหมด CCTV เท่านั้น
    """
    now = datetime.now()
    in_window = _api_in_active_window(now.time())
    windows = [
        {"start": s.strftime("%H:%M"), "end": e.strftime("%H:%M")}
        for s, e in _ACTIVE_WINDOWS
    ]
    return {
        "mode":           "face" if in_window else "cctv",
        "in_window":      in_window,
        "current_time":   now.strftime("%H:%M:%S"),
        "active_windows": windows,
    }


def _do_auto_checkout_all(now: datetime) -> int:
    """
    checkout ทุกคนที่มี IN วันนี้แต่ยังไม่มี OUT
    ใช้ชื่อ/หน่วยงานจาก IN record ล่าสุดของแต่ละคน
    คืนจำนวนคนที่ checkout สำเร็จ
    """
    count = 0
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT DISTINCT ON (a.per_id)
                        a.per_id, a.name, a.prename_th, a.per_name, a.per_surname,
                        a.posname_th, a.organize_th, a.organize_id, a.camera_name
                    FROM attendance_logs a
                    WHERE DATE(a.check_time) = CURRENT_DATE
                      AND a.status = 'IN'
                      AND a.per_id NOT IN (
                          SELECT per_id FROM attendance_logs
                          WHERE DATE(check_time) = CURRENT_DATE AND status = 'OUT'
                      )
                    ORDER BY a.per_id, a.check_time DESC
                """)
                rows = cur.fetchall()

            for row in rows:
                per_id, name, prename_th, per_name, per_surname, posname_th, organize_th, organize_id, camera_name = row
                with conn.cursor() as cur:
                    cur.execute("""
                        INSERT INTO attendance_logs
                            (per_id, status, camera_name, check_time,
                             name, prename_th, per_name, per_surname,
                             posname_th, organize_th, organize_id)
                        VALUES (%s, 'OUT', %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """, (
                        per_id, camera_name or 'auto', now,
                        name, prename_th, per_name, per_surname,
                        posname_th, organize_th, organize_id,
                    ))
                count += 1
            conn.commit()
        print(f"[AUTO-CHECKOUT] checkout {count} คน  {now.strftime('%H:%M:%S')}")
    except Exception as e:
        print(f"[AUTO-CHECKOUT] error: {e}")
    return count


@app.post("/attendance/auto-checkout", dependencies=[Depends(_require_perm("attendance.clear"))])
def attendance_auto_checkout():
    """
    checkout ทุกคนที่ IN วันนี้แต่ยังไม่มี OUT
    เรียกจาก Dashboard เมื่อ active window สิ้นสุด (หรือ manual trigger)
    """
    now   = datetime.now()
    count = _do_auto_checkout_all(now)
    return {"success": True, "checked_out": count, "time": now.isoformat()}


# ── Background Scheduler: ตรวจ face→cctv transition แล้ว auto-checkout ───────
_sched_last_in_window: "bool | None" = None   # None = ยังไม่ได้ตรวจครั้งแรก

async def _mode_watcher_task():
    """
    Background coroutine ที่รันตลอดอายุ api.py
    ตรวจทุก 30 วินาที — เมื่อ transition face→cctv → auto-checkout ทันที
    เหมือนพฤติกรรมของ main.py ใน ALWAYS_ACTIVE mode
    """
    global _sched_last_in_window
    while True:
        await _asyncio.sleep(30)
        try:
            now       = datetime.now()
            in_window = _api_in_active_window(now.time())

            if _sched_last_in_window is True and not in_window:
                print(f"[SCHEDULER] face→cctv transition {now.strftime('%H:%M')} → auto-checkout")
                _do_auto_checkout_all(now)

            _sched_last_in_window = in_window
        except Exception as e:
            print(f"[SCHEDULER] watcher error: {e}")


# ╔═══════════════════════════════════════════════════════════════════════════╗
# ║  Camera Endpoints (สำหรับ Dashboard หน้ากล้อง)                            ║
# ╚═══════════════════════════════════════════════════════════════════════════╝

import cv2
import threading
from fastapi.responses import StreamingResponse

# ── กำหนดแหล่งกล้อง ────────────────────────────────────────────────────────
# ลำดับการค้นหา:
#   1. env CAMERA_URL (เช่น rtsp://... หรือ "1" สำหรับ USB index 1)
#   2. default = 0 (USB camera index 0)
#
# วิธีเปลี่ยน: ตั้งค่าใน .env
#   CAMERA_URL=rtsp://admin:pass@192.168.1.13:554/...   ← IP camera
#   CAMERA_URL=1                                         ← USB index 1
def _get_camera_source():
    raw = os.environ.get("CAMERA_URL", "")
    if not raw:
        return 0          # USB camera index 0
    if raw.isdigit():
        return int(raw)   # USB camera index N
    return raw            # RTSP / HTTP URL string

# ── Helper: เปิดกล้องพร้อม timeout ────────────────────────────────────────────
# รัน VideoCapture ใน thread แยก เพื่อไม่ให้ block FastAPI event loop
# คืน (cap, True) ถ้าเปิดได้, (None, False) ถ้า timeout
def _open_camera(source, timeout_sec: float = 12.0):
    """
    เปิดกล้องใน thread แยกเพื่อไม่ block event loop
    - USB (int): ใช้ CAP_V4L2 บน Linux
    - RTSP/HTTP (str): ใช้ CAP_FFMPEG + rtsp_transport=tcp
    คืน (cap, True) ถ้าสำเร็จ, (None, False) ถ้า timeout หรือเปิดไม่ได้
    """
    result = [None, False]

    def _open():
        if isinstance(source, str):
            # RTSP/HTTP — ใช้ FFMPEG backend + TCP transport (เสถียรกว่า UDP)
            os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = (
                "rtsp_transport;tcp|stimeout;5000000"
            )
            cap = cv2.VideoCapture(source, cv2.CAP_FFMPEG)
        else:
            cap = cv2.VideoCapture(source, cv2.CAP_V4L2)
            if not cap.isOpened():          # fallback ถ้า V4L2 ไม่มี
                cap = cv2.VideoCapture(source)
        result[0] = cap
        result[1] = cap.isOpened()

    t = threading.Thread(target=_open, daemon=True)
    t.start()
    t.join(timeout=timeout_sec)

    if t.is_alive():    # thread ยังรันอยู่ = timeout
        return None, False
    return result[0], result[1]


# ╔═══════════════════════════════════════════════════════════════════════════╗
# ║  Multi-Camera Configuration                                               ║
# ╟───────────────────────────────────────────────────────────────────────────╢
# ║  แก้ไขกล้องที่นี่ — เพิ่ม/ลบ entry ใน CAMERAS_CONFIG ได้เลย             ║
# ║                                                                           ║
# ║  แต่ละกล้อง:                                                              ║
# ║    id     — รหัสไม่ซ้ำ (ใช้ใน URL เช่น /cameras/cam1/stream)            ║
# ║    name   — ชื่อแสดงผลบน Dashboard                                       ║
# ║    source — USB index (int) หรือ RTSP/HTTP URL (str)                     ║
# ║                                                                           ║
# ║  Override ผ่าน .env:                                                      ║
# ║    CAMERA1_URL=0          ← USB index 0 (laptop webcam)                  ║
# ║    CAMERA1_URL=1          ← USB index 1 (external webcam)                ║
# ║    CAMERA2_URL=rtsp://... ← IP camera                                    ║
# ╚═══════════════════════════════════════════════════════════════════════════╝

def _parse_cam_source(raw: str, default):
    """แปลง string จาก env var → int index หรือ string URL"""
    if not raw:
        return default
    return int(raw) if raw.isdigit() else raw

_RTSP_CAM2 = "rtsp://admin:@dmin123456@192.168.1.13:554/unicast/c1/s0/live"

# ── Default cameras (ใช้เมื่อ cameras_config.json ยังไม่มี) ──────────────────
_DEFAULT_CAMERAS_CONFIG = [
    {
        "id":     "cam1",
        "name":   "กล้อง 1 (Laptop)",
        "source": _parse_cam_source(os.environ.get("CAMERA1_URL", ""), 0),
        "flip":   False,
    },
    {
        "id":     "cam2",
        "name":   "กล้อง 2 (IP Camera)",
        "source": _parse_cam_source(os.environ.get("CAMERA2_URL", ""), _RTSP_CAM2),
        "flip":   False,
    },
]

_CAMERAS_CONFIG_PATH = _ROOT / "cameras_config.json"

def _load_cameras_config() -> list:
    """โหลด cameras config จาก JSON file (ถ้ามี) หรือ fallback ไป default"""
    if _CAMERAS_CONFIG_PATH.exists():
        try:
            data = _json.loads(_CAMERAS_CONFIG_PATH.read_text(encoding="utf-8"))
            if isinstance(data, list):
                # normalize: แปลง source string→int ถ้าเป็นตัวเลข
                for c in data:
                    src = c.get("source", "")
                    if isinstance(src, str) and src.isdigit():
                        c["source"] = int(src)
                    if "flip" not in c:
                        c["flip"] = False
                return data
        except Exception:
            pass
    return [dict(c) for c in _DEFAULT_CAMERAS_CONFIG]

def _save_cameras_config(cfg: list):
    """บันทึก cameras config ลง JSON file"""
    # serialize: int source → string เพื่อ JSON compat
    serializable = []
    for c in cfg:
        entry = dict(c)
        serializable.append(entry)
    _CAMERAS_CONFIG_PATH.write_text(
        _json.dumps(serializable, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

CAMERAS_CONFIG: list = _load_cameras_config()
_CAMERAS: dict = {c["id"]: c for c in CAMERAS_CONFIG}


@app.get("/cameras")
def list_cameras(_: dict = Depends(_require_perm("cameras.view"))):
    """คืนรายการกล้องทั้งหมดที่ตั้งค่าไว้ — ใช้โดย Dashboard เพื่อ render panels"""
    return [
        {
            "id":          c["id"],
            "name":        c["name"],
            "source_type": "rtsp" if isinstance(c["source"], str) else "usb",
            "source":      str(c["source"]),
            "flip":        c.get("flip", False),
        }
        for c in CAMERAS_CONFIG
    ]


class CameraCreateBody(BaseModel):
    name:        str
    source_type: str   # "usb" | "rtsp"
    source:      str   # port number (str of int) for usb, URL for rtsp
    flip:        bool = False


@app.post("/cameras")
def add_camera(body: CameraCreateBody, _: dict = Depends(_require_perm("cameras.manage"))):
    """เพิ่มกล้องใหม่ — บันทึกลง cameras_config.json"""
    # แปลง source
    if body.source_type == "usb":
        source = int(body.source) if body.source.isdigit() else 0
    else:
        source = body.source.strip()

    # สร้าง unique id
    existing_ids = {c["id"] for c in CAMERAS_CONFIG}
    base = "cam"
    n = len(CAMERAS_CONFIG) + 1
    while f"{base}{n}" in existing_ids:
        n += 1
    new_id = f"{base}{n}"

    new_cam = {
        "id":     new_id,
        "name":   body.name.strip(),
        "source": source,
        "flip":   body.flip,
    }

    CAMERAS_CONFIG.append(new_cam)
    _CAMERAS[new_id] = new_cam
    _save_cameras_config(CAMERAS_CONFIG)

    return {
        "ok":   True,
        "id":   new_id,
        "name": new_cam["name"],
    }


class CameraFlipBody(BaseModel):
    flip: bool


@app.patch("/cameras/{cam_id}/flip")
def update_camera_flip(cam_id: str, body: CameraFlipBody,
                       _: dict = Depends(_require_perm("cameras.manage"))):
    """
    อัพเดต flip ของกล้องที่ระบุ — บันทึกลง cameras_config.json
    ถ้า face process กำลังรัน → restart อัตโนมัติเพื่อให้ CAMERA_FLIP มีผล
    (flip ทำที่ main.py ก่อนวาด overlay จึงไม่กระทบ bounding box / label)
    """
    if cam_id not in _CAMERAS:
        raise HTTPException(status_code=404, detail=f"Camera '{cam_id}' not found")

    _CAMERAS[cam_id]["flip"] = body.flip
    for c in CAMERAS_CONFIG:
        if c["id"] == cam_id:
            c["flip"] = body.flip
            break
    _save_cameras_config(CAMERAS_CONFIG)

    # restart process ถ้ากำลังรันอยู่
    restarted = False
    proc = _face_processes.get(cam_id)
    if proc is not None and proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except Exception:
            proc.kill()
        _face_processes.pop(cam_id, None)

        # start ใหม่พร้อม flip setting ใหม่
        cam = _CAMERAS[cam_id]
        try:
            env = os.environ.copy()
            env["FACE_HEADLESS"]        = "1"
            env["FACE_ALWAYS_ACTIVE"]   = "1"
            env["FACE_CAMERA_CHILD"]    = "1"
            env["CAMERA_URL"]           = str(cam["source"])
            env["CAMERA_FLIP"]          = "1" if body.flip else "0"
            env["FACE_LIVE_FRAME_PATH"] = str(_live_frame_path_for(cam_id))
            env["FACE_LIVE_STATE_PATH"] = str(_live_state_path_for(cam_id))
            env["FACE_BOOT_PATH"]       = str(_boot_path_for(cam_id))
            new_proc = _subprocess.Popen(
                [_sys.executable, str(_ROOT / "main.py")],
                cwd=str(_ROOT),
                env=env,
            )
            _face_processes[cam_id] = new_proc
            restarted = True
        except Exception:
            pass

    return {"ok": True, "cam_id": cam_id, "flip": body.flip, "restarted": restarted}


@app.delete("/cameras/{cam_id}")
def delete_camera(cam_id: str, _: dict = Depends(_require_perm("cameras.manage"))):
    """ลบกล้องออก — หยุด process ถ้ากำลังรัน แล้วบันทึกลง cameras_config.json"""
    if cam_id not in _CAMERAS:
        raise HTTPException(status_code=404, detail=f"Camera '{cam_id}' not found")

    # หยุด face process ถ้ากำลังทำงาน
    proc = _face_processes.get(cam_id)
    if proc is not None and proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except Exception:
            proc.kill()
    _face_processes.pop(cam_id, None)

    # ลบออกจาก config
    CAMERAS_CONFIG[:] = [c for c in CAMERAS_CONFIG if c["id"] != cam_id]
    _CAMERAS.pop(cam_id, None)
    _save_cameras_config(CAMERAS_CONFIG)

    return {"ok": True, "deleted": cam_id}


@app.get("/cameras/{cam_id}/stream")
def cameras_raw_stream(cam_id: str, token: Optional[str] = Query(None)):
    """
    MJPEG stream โดยตรงจากกล้องที่ระบุ (ไม่มี face recognition overlay)
    ──────────────────────────────────────────────────────────────────────
    ใช้ทดสอบว่ากล้องทำงานได้ก่อน start main.py
    """
    # ตรวจ auth ผ่าน query param (img src ไม่รองรับ header)
    if not token:
        raise HTTPException(status_code=401, detail="ต้องเข้าสู่ระบบก่อน")
    try:
        tok_data = _decode_token(token)
        if not _has_permission(tok_data, "cameras.view"):
            raise HTTPException(status_code=403, detail="ไม่มีสิทธิ์ cameras.view")
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=401, detail="Token ไม่ถูกต้อง")

    cam = _CAMERAS.get(cam_id)
    if not cam:
        raise HTTPException(status_code=404, detail=f"Camera '{cam_id}' not found")

    def generate():
        import time
        source = cam["source"]
        cap, ok = _open_camera(source, timeout_sec=10.0)
        if not ok:
            if cap:
                cap.release()
            yield (
                b'--frame\r\nContent-Type: image/jpeg\r\n\r\n'
                + _make_error_frame(f"{cam['name']}: ไม่พร้อม")
                + b'\r\n'
            )
            return
        interval = 1.0 / 15
        try:
            while True:
                t0 = time.time()
                ret, frame = cap.read()
                if not ret:
                    break
                ok2, buf = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 65])
                if ok2:
                    yield (
                        b'--frame\r\nContent-Type: image/jpeg\r\n\r\n'
                        + buf.tobytes()
                        + b'\r\n'
                    )
                elapsed = time.time() - t0
                if elapsed < interval:
                    time.sleep(interval - elapsed)
        finally:
            cap.release()

    return StreamingResponse(
        generate(),
        media_type='multipart/x-mixed-replace; boundary=frame',
        headers={"Cache-Control": "no-cache, no-store"},
    )


@app.get("/camera/info")
def camera_info():
    """
    คืน metadata ของกล้องที่จะใช้ stream
    ใช้โดย CameraView.vue เพื่อแสดง type / source
    """
    source = _get_camera_source()
    cam_type = "RTSP / IP Camera" if isinstance(source, str) else "USB Camera"
    return {
        "type":   cam_type,
        "source": str(source),
    }


@app.get("/camera/snapshot")
def camera_snapshot():
    """
    ถ่ายภาพเดียวจากกล้อง → JPEG
    ──────────────────────────────────────────────────────
    ใช้เป็น probe: Vue จะเรียก endpoint นี้ก่อน start MJPEG stream
    เพื่อตรวจสอบว่ากล้องพร้อมและ fail fast ถ้าเชื่อมต่อไม่ได้
    Timeout: 8 วินาที
    """
    from fastapi.responses import Response as _Resp

    source = _get_camera_source()
    cap, ok = _open_camera(source, timeout_sec=8.0)

    if not ok:
        if cap: cap.release()
        raise HTTPException(status_code=503, detail="Camera unavailable or timeout")

    try:
        ret, frame = cap.read()
        if not ret:
            raise HTTPException(status_code=503, detail="Cannot read frame")
        _, buf = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
        return _Resp(
            content=buf.tobytes(),
            media_type="image/jpeg",
            headers={"Cache-Control": "no-cache"},
        )
    finally:
        cap.release()


@app.get("/camera/stream")
def camera_stream(token: Optional[str] = Query(None)):
    """
    MJPEG stream จากกล้อง
    ─────────────────────────────────────────────────────────
    ใช้ใน Vue dashboard: <img :src="'/api/camera/stream?token=...'">

    ⚠ ควรเรียก /camera/snapshot probe ก่อน (CameraView.vue ทำให้อัตโนมัติ)
      ถ้า main.py ใช้กล้องเดียวกัน อาจ conflict (IP camera รองรับ multi-client)

    Quality: JPEG 65%  |  Max FPS: 15
    """
    if not token:
        raise HTTPException(status_code=401, detail="ต้องเข้าสู่ระบบก่อน")
    try:
        tok_data = _decode_token(token)
        if not _has_permission(tok_data, "cameras.view"):
            raise HTTPException(status_code=403, detail="ไม่มีสิทธิ์ cameras.view")
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=401, detail="Token ไม่ถูกต้อง")

    JPEG_QUALITY = 65
    MAX_FPS      = 15

    def generate():
        import time
        source = _get_camera_source()
        cap, ok = _open_camera(source, timeout_sec=10.0)

        if not ok:
            if cap: cap.release()
            yield (b'--frame\r\nContent-Type: image/jpeg\r\n\r\n'
                   + _make_error_frame("Camera unavailable") + b'\r\n')
            return

        interval = 1.0 / MAX_FPS
        try:
            while True:
                t0 = time.time()
                ret, frame = cap.read()
                if not ret:
                    break
                ok2, buf = cv2.imencode(
                    '.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY]
                )
                if ok2:
                    yield (b'--frame\r\nContent-Type: image/jpeg\r\n\r\n'
                           + buf.tobytes() + b'\r\n')
                elapsed = time.time() - t0
                if elapsed < interval:
                    time.sleep(interval - elapsed)
        finally:
            cap.release()

    return StreamingResponse(
        generate(),
        media_type='multipart/x-mixed-replace; boundary=frame',
        headers={"Cache-Control": "no-cache, no-store"},
    )


@app.get("/person-photo/{per_id}")
def person_photo(per_id: str, status: str = Query("IN", regex="^(IN|OUT)$")):
    """
    รูป verify จากกล้อง (PicSAVE เท่านั้น) — ใช้ใน AttendanceFeed
      status=IN  → _IN.jpg  → _OUT.jpg → 404
      status=OUT → _OUT.jpg → _IN.jpg  → 404
    ไม่ใช้ per_picpath เด็ดขาด เพื่อให้แสดงรูปที่ถ่ายตอน verify จริงๆ
    """
    import glob as _glob
    from fastapi.responses import FileResponse
    from datetime import date as _date

    today  = _date.today()
    folder = _ROOT / "PicSAVE" / today.strftime("%Y") / today.strftime("%m") / today.strftime("%d")

    suffixes = ["_IN.jpg", "_OUT.jpg"] if status == "IN" else ["_OUT.jpg", "_IN.jpg"]
    for suffix in suffixes:
        matches = sorted(_glob.glob(str(folder / f"*_{per_id}{suffix}")))
        if matches:
            return FileResponse(matches[-1], media_type="image/jpeg",
                                headers={"Cache-Control": "no-cache"})

    raise HTTPException(status_code=404, detail="No verify photo found")


@app.get("/person-profile/{per_id}")
def person_profile(per_id: str):
    """
    รูปโปรไฟล์จาก External API (per_picpath เท่านั้น) — ใช้ใน PersonCard
    ไม่ใช้ PicSAVE เด็ดขาด เพื่อแสดงรูปโปรไฟล์ทางการ
    """
    import requests as _req
    from fastapi.responses import Response

    try:
        from api_client import fetch_person_by_pid
        person  = fetch_person_by_pid(per_id)
        pic_url = (person or {}).get("per_picpath", "")
        if pic_url:
            r = _req.get(pic_url, timeout=5)
            if r.ok:
                ctype = r.headers.get("content-type", "image/jpeg")
                return Response(content=r.content, media_type=ctype,
                                headers={"Cache-Control": "max-age=3600"})
    except Exception:
        pass

    raise HTTPException(status_code=404, detail="No profile photo")


@app.get("/person-face/{per_id}")
def person_face(per_id: str):
    """
    คืนรูป face crop (bounding box) ล่าสุดของพนักงานวันนี้
    ────────────────────────────────────────────────────────
    ค้นหาใน PicSAVE/YYYY/MM/DD/*_{per_id}_FACE.jpg
    ถ้าไม่พบ → fallback ไปที่ _IN.jpg → ถ้ายังไม่มี → 404

    ใช้ใน CameraView.vue fullscreen sidebar:
      <img :src="`/api/person-face/${p.per_id}`" />
    """
    import glob as _glob
    from fastapi.responses import FileResponse
    from datetime import date as _date

    today   = _date.today()
    folder  = _ROOT / "PicSAVE" / today.strftime("%Y") / today.strftime("%m") / today.strftime("%d")

    # ลองหา FACE crop ก่อน
    matches = sorted(_glob.glob(str(folder / f"*_{per_id}_FACE.jpg")))
    if matches:
        return FileResponse(matches[-1], media_type="image/jpeg",
                            headers={"Cache-Control": "no-cache"})

    # fallback: ใช้ IN photo ถ้ายังไม่มี FACE (เช่น session เก่าก่อน update)
    matches = sorted(_glob.glob(str(folder / f"*_{per_id}_IN.jpg")))
    if matches:
        return FileResponse(matches[-1], media_type="image/jpeg",
                            headers={"Cache-Control": "max-age=300"})

    raise HTTPException(status_code=404, detail="No face photo found")


# ╔═══════════════════════════════════════════════════════════════════════════╗
# ║  Live Session Endpoint (อ่านสถานะ real-time จาก main.py)                  ║
# ╚═══════════════════════════════════════════════════════════════════════════╝

import json as _json
import time as _time

_LIVE_STATE_PATH = _FRAMES_DIR / "live_state.json"   # legacy path (main.py รันตรง)

@app.get("/session/live")
def session_live(_: dict = Depends(_require_perm("cameras.view"))):
    """
    คืนสถานะ live รวมจากทุกกล้อง
    ─────────────────────────────────────────────────────────────────────
    อ่านจาก live_state_{cam_id}.json (per-camera, start จาก /cameras/{id}/face/start)
    และ fallback ไปที่ live_state.json (legacy: main.py รันตรง / old /camera/face/start)

    Response:
      {
        "active": bool,   — มีกล้องอย่างน้อย 1 ตัวที่ main.py กำลังรัน
        "ts": float,      — unix timestamp ล่าสุด
        "stale": bool,    — true ถ้าข้อมูลเก่าเกิน 5 วินาที
        "persons": [...]  — รายชื่อรวมจากทุกกล้อง (ไม่ซ้ำ per_id)
      }
    """
    merged: dict[str, dict] = {}
    any_active = False
    latest_ts: float | None = None
    found_cam_files = False

    # ── อ่าน per-camera state files (live_state_cam1.json, live_state_cam2.json ฯลฯ) ──
    # ค้นหาทั้งใน _FRAMES_DIR (tmpfs) และ _ROOT (legacy)
    _now = _time.time()
    _state_paths = sorted({*_FRAMES_DIR.glob("live_state_*.json"), *_ROOT.glob("live_state_*.json")})
    for path in _state_paths:
        found_cam_files = True
        try:
            data = _json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        ts          = data.get("ts")
        data_active = data.get("active", True)   # True = face mode, False = CCTV mode
        is_recent   = ts is not None and (_now - ts <= 5)

        if is_recent:
            if latest_ts is None or ts > latest_ts:
                latest_ts = ts
            if data_active:
                # face recognition mode เท่านั้นที่นับว่า active
                any_active = True
        for p in data.get("persons", []):
            pid = p.get("per_id")
            if pid and pid not in merged:
                merged[pid] = p

    # ── ถ้ามี per-camera files → ใช้ผลที่รวมมาแล้ว (แม้ไม่มีคนในกล้อง) ──
    if found_cam_files:
        stale = not any_active
        return {
            "active":  any_active,
            "ts":      latest_ts,
            "stale":   stale,
            "persons": list(merged.values()),
        }

    # ── Fallback: legacy live_state.json (เมื่อไม่มี per-camera files) ──────
    if not _LIVE_STATE_PATH.exists():
        return {"active": False, "ts": None, "stale": True, "persons": []}
    try:
        data = _json.loads(_LIVE_STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"active": False, "ts": None, "stale": True, "persons": []}
    ts          = data.get("ts")
    data_active = data.get("active", True)
    is_recent   = ts is not None and (_now - ts <= 5)
    # stale เมื่อ: ts เก่า หรือ main.py อยู่ใน CCTV mode (face recognition หยุด)
    stale = not is_recent or not data_active
    data["stale"] = stale
    return data


# ╔═══════════════════════════════════════════════════════════════════════════╗
# ║  Face Recognition Stream & Process Control (Dashboard)                    ║
# ╚═══════════════════════════════════════════════════════════════════════════╝

import sys as _sys
import subprocess as _subprocess

_LIVE_FRAME_PATH  = _FRAMES_DIR / "live_frame.jpg"
_face_process: "_subprocess.Popen | None" = None


@app.post("/camera/face/start")
def face_process_start(_: dict = Depends(_require_perm("cameras.manage"))):
    """
    Start main.py เป็น background process
    main.py จะเขียน live_frame.jpg ทุก ~67ms สำหรับ /camera/face-stream
    """
    global _face_process
    if _face_process is not None and _face_process.poll() is None:
        return {"ok": False, "reason": "already running", "pid": _face_process.pid}
    try:
        env = os.environ.copy()
        env["FACE_HEADLESS"]        = "1"
        env["FACE_ALWAYS_ACTIVE"]   = "1"
        env["FACE_CAMERA_CHILD"]    = "1"
        # ชี้ live files ไปที่ _FRAMES_DIR เดียวกับที่ api.py อ่าน
        env["FACE_LIVE_FRAME_PATH"] = str(_FRAMES_DIR / "live_frame.jpg")
        env["FACE_LIVE_STATE_PATH"] = str(_FRAMES_DIR / "live_state.json")
        _face_process = _subprocess.Popen(
            [_sys.executable, str(_ROOT / "main.py")],
            cwd=str(_ROOT),
            env=env,
        )
        return {"ok": True, "pid": _face_process.pid}
    except Exception as e:
        return {"ok": False, "reason": str(e)}


@app.post("/camera/face/stop")
def face_process_stop(_: dict = Depends(_require_perm("cameras.manage"))):
    """หยุด main.py background process"""
    global _face_process
    if _face_process is None or _face_process.poll() is not None:
        return {"ok": False, "reason": "not running"}
    _face_process.terminate()
    try:
        _face_process.wait(timeout=5)
    except _subprocess.TimeoutExpired:
        _face_process.kill()
    return {"ok": True}


@app.delete("/camera/face/cache")
def face_cache_clear():
    """
    ล้าง cache ที่ main.py เขียนไว้ (ไม่กระทบ database)
    ─────────────────────────────────────────────────────────────────────
    ลบไฟล์:
      live_frame.jpg  — frame ล่าสุดจากกล้อง
      live_state.json — สถานะ session (persons / liveness)
    """
    cleared = []
    for path in (_LIVE_FRAME_PATH, _LIVE_STATE_PATH):
        try:
            path.unlink(missing_ok=True)
            cleared.append(path.name)
        except Exception as e:
            pass
    return {"ok": True, "cleared": cleared}


@app.get("/camera/face/status")
def face_process_status():
    """
    สถานะ main.py process + ข้อมูล live_frame.jpg
    ─────────────────────────────────────────────────────────────────────
    running:       main.py กำลังรันอยู่
    has_frame:     live_frame.jpg มีอยู่
    frame_age_sec: อายุของ frame (วินาที) — ถ้า > 5 = main.py อาจหยุด
    """
    global _face_process
    running = _face_process is not None and _face_process.poll() is None
    has_frame = _LIVE_FRAME_PATH.exists()
    frame_age = None
    if has_frame:
        frame_age = round(_time.time() - _LIVE_FRAME_PATH.stat().st_mtime, 1)
    return {
        "running": running,
        "pid": _face_process.pid if running else None,
        "has_frame": has_frame,
        "frame_age_sec": frame_age,
    }


@app.get("/camera/face-stream")
def camera_face_stream(token: Optional[str] = Query(None)):
    """
    MJPEG stream จาก main.py (อ่านจาก live_frame.jpg)
    ─────────────────────────────────────────────────────────────────────
    main.py เขียน live_frame.jpg ทุก ~67ms (15fps) พร้อม overlay ทั้งหมด
    Dashboard แสดงผลผ่าน <img :src="'/api/camera/face-stream?token=...'">
    """
    if not token:
        raise HTTPException(status_code=401, detail="ต้องเข้าสู่ระบบก่อน")
    try:
        tok_data = _decode_token(token)
        if not _has_permission(tok_data, "cameras.view"):
            raise HTTPException(status_code=403, detail="ไม่มีสิทธิ์ cameras.view")
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=401, detail="Token ไม่ถูกต้อง")

    def generate():
        import time
        last_mtime = 0.0
        while True:
            try:
                mtime = _LIVE_FRAME_PATH.stat().st_mtime
                if mtime != last_mtime:
                    last_mtime = mtime
                    frame_bytes = _LIVE_FRAME_PATH.read_bytes()
                    yield (
                        b'--frame\r\nContent-Type: image/jpeg\r\n\r\n'
                        + frame_bytes + b'\r\n'
                    )
            except (FileNotFoundError, OSError):
                pass
            time.sleep(0.033)  # poll 30fps แต่ส่งเฉพาะเมื่อ main.py เขียน frame ใหม่

    return StreamingResponse(
        generate(),
        media_type='multipart/x-mixed-replace; boundary=frame',
        headers={"Cache-Control": "no-cache, no-store"},
    )


def _make_error_frame(msg: str) -> bytes:
    """สร้าง JPEG frame สีเข้มพร้อมข้อความ error (แสดงเมื่อกล้องไม่พร้อม)"""
    blank = __import__('numpy').zeros((240, 320, 3), dtype=__import__('numpy').uint8)
    blank[:] = (26, 26, 26)   # #1A1A1A background
    cv2.putText(blank, msg, (20, 120),
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (80, 80, 80), 2)
    _, buf = cv2.imencode('.jpg', blank)
    return buf.tobytes()


# ╔═══════════════════════════════════════════════════════════════════════════╗
# ║  Multi-Camera Face Recognition Endpoints                                  ║
# ╟───────────────────────────────────────────────────────────────────────────╢
# ║  จัดการ main.py แยกต่างหากสำหรับแต่ละกล้อง                               ║
# ║  แต่ละกล้องเขียน live_frame_{cam_id}.jpg และ live_state_{cam_id}.json    ║
# ╚═══════════════════════════════════════════════════════════════════════════╝

_face_processes: dict[str, "_subprocess.Popen"] = {}


def _live_frame_path_for(cam_id: str) -> pathlib.Path:
    return _FRAMES_DIR / f"live_frame_{cam_id}.jpg"


def _live_state_path_for(cam_id: str) -> pathlib.Path:
    return _FRAMES_DIR / f"live_state_{cam_id}.json"


def _boot_path_for(cam_id: str) -> pathlib.Path:
    return _FRAMES_DIR / f"boot_status_{cam_id}.json"


@app.get("/cameras/{cam_id}/face-stream")
def cameras_face_stream(cam_id: str, token: Optional[str] = Query(None)):
    """
    MJPEG stream จาก main.py พร้อม face recognition overlay สำหรับกล้องที่ระบุ
    อ่านจาก live_frame_{cam_id}.jpg ที่ main.py เขียนทุก ~67ms
    """
    if not token:
        raise HTTPException(status_code=401, detail="ต้องเข้าสู่ระบบก่อน")
    try:
        tok_data = _decode_token(token)
        if not _has_permission(tok_data, "cameras.view"):
            raise HTTPException(status_code=403, detail="ไม่มีสิทธิ์ cameras.view")
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=401, detail="Token ไม่ถูกต้อง")

    if cam_id not in _CAMERAS:
        raise HTTPException(status_code=404, detail=f"Camera '{cam_id}' not found")

    live_frame = _live_frame_path_for(cam_id)

    def generate():
        import time
        last_mtime = 0.0
        while True:
            try:
                mtime = live_frame.stat().st_mtime
                if mtime != last_mtime:
                    last_mtime = mtime
                    frame_bytes = live_frame.read_bytes()
                    yield (
                        b'--frame\r\nContent-Type: image/jpeg\r\n\r\n'
                        + frame_bytes
                        + b'\r\n'
                    )
            except (FileNotFoundError, OSError):
                pass
            time.sleep(0.033)  # poll 30fps แต่ส่งเฉพาะเมื่อ main.py เขียน frame ใหม่

    return StreamingResponse(
        generate(),
        media_type='multipart/x-mixed-replace; boundary=frame',
        headers={"Cache-Control": "no-cache, no-store"},
    )


@app.get("/cameras/{cam_id}/face/status")
def cameras_face_status(cam_id: str, _: dict = Depends(_require_perm("cameras.view"))):
    """สถานะ main.py process + live frame สำหรับกล้องที่ระบุ"""
    if cam_id not in _CAMERAS:
        raise HTTPException(status_code=404, detail=f"Camera '{cam_id}' not found")

    proc = _face_processes.get(cam_id)
    running = proc is not None and proc.poll() is None
    live_frame = _live_frame_path_for(cam_id)
    has_frame = live_frame.exists()
    frame_age = None
    if has_frame:
        frame_age = round(_time.time() - live_frame.stat().st_mtime, 1)

    boot_msg = None
    boot_path = _boot_path_for(cam_id)
    if boot_path.exists():
        try:
            import json as _j
            boot_msg = _j.loads(boot_path.read_text(encoding="utf-8")).get("msg")
        except Exception:
            pass

    return {
        "cam_id":        cam_id,
        "cam_name":      _CAMERAS[cam_id]["name"],
        "running":       running,
        "pid":           proc.pid if running else None,
        "has_frame":     has_frame,
        "frame_age_sec": frame_age,
        "boot_msg":      boot_msg,
    }


@app.post("/cameras/{cam_id}/face/start")
def cameras_face_start(cam_id: str, _: dict = Depends(_require_perm("cameras.manage"))):
    """
    Start main.py สำหรับกล้องที่ระบุ
    ─────────────────────────────────────────────────────────────────────
    ส่ง env vars ไปให้ main.py:
      CAMERA_URL           — camera source (index หรือ RTSP URL)
      FACE_LIVE_FRAME_PATH — path ของ live_frame_{cam_id}.jpg
      FACE_LIVE_STATE_PATH — path ของ live_state_{cam_id}.json
    """
    cam = _CAMERAS.get(cam_id)
    if not cam:
        raise HTTPException(status_code=404, detail=f"Camera '{cam_id}' not found")

    proc = _face_processes.get(cam_id)
    if proc is not None and proc.poll() is None:
        return {"ok": False, "reason": "already running", "pid": proc.pid}

    try:
        env = os.environ.copy()
        env["FACE_HEADLESS"]        = "1"
        env["FACE_ALWAYS_ACTIVE"]   = "1"
        env["FACE_CAMERA_CHILD"]    = "1"   # ป้องกัน multi-camera recursive spawn
        env["CAMERA_URL"]           = str(cam["source"])
        env["CAMERA_FLIP"]          = "1" if cam.get("flip", False) else "0"
        env["FACE_LIVE_FRAME_PATH"] = str(_live_frame_path_for(cam_id))
        env["FACE_LIVE_STATE_PATH"] = str(_live_state_path_for(cam_id))
        env["FACE_BOOT_PATH"]       = str(_boot_path_for(cam_id))

        proc = _subprocess.Popen(
            [_sys.executable, str(_ROOT / "main.py")],
            cwd=str(_ROOT),
            env=env,
        )
        _face_processes[cam_id] = proc
        return {"ok": True, "pid": proc.pid}
    except Exception as e:
        return {"ok": False, "reason": str(e)}


@app.post("/cameras/{cam_id}/face/stop")
def cameras_face_stop(cam_id: str, _: dict = Depends(_require_perm("cameras.manage"))):
    """หยุด main.py process สำหรับกล้องที่ระบุ"""
    if cam_id not in _CAMERAS:
        raise HTTPException(status_code=404, detail=f"Camera '{cam_id}' not found")

    proc = _face_processes.get(cam_id)
    if proc is None or proc.poll() is not None:
        return {"ok": False, "reason": "not running"}

    proc.terminate()
    try:
        proc.wait(timeout=5)
    except _subprocess.TimeoutExpired:
        proc.kill()
    return {"ok": True}
