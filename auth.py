"""
auth.py — ระบบ login (JWT + bcrypt) สำหรับ stream_server.py และ api.py
========================================================================
- bootstrap_default_users() — สร้าง admin/viewer ตอนรันครั้งแรก ถ้ายังไม่มี user ในตาราง
- login(user, pw) → token (JWT, exp 8h)
- get_current_user / require_admin / require_viewer — FastAPI dependencies
- change_password / set_password / list_users / delete_user — admin operations
"""

import os
from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
import jwt
from fastapi import Header, HTTPException, status

from db import get_connection

# ─── Config ──────────────────────────────────────────────────────────────────
_JWT_SECRET = os.environ.get("JWT_SECRET", "")
_JWT_ALG    = "HS256"
_JWT_TTL_HR = int(os.environ.get("JWT_TTL_HOURS", "8"))

# Default users ที่จะสร้างถ้าตาราง users ว่าง (boot ครั้งแรก)
_DEFAULT_USERS = [
    ("admin",  "Admin12345", "admin"),
    ("viewer", "User12345",  "viewer"),
]


# ─── Password hashing ────────────────────────────────────────────────────────

def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:
        return False


# ─── JWT ─────────────────────────────────────────────────────────────────────

def _ensure_secret() -> str:
    if not _JWT_SECRET:
        raise RuntimeError(
            "JWT_SECRET ยังไม่ได้ตั้งใน .env — สุ่ม 32 bytes แล้วใส่ไว้"
        )
    return _JWT_SECRET


def create_token(user_id: int, username: str, role: str) -> str:
    secret = _ensure_secret()
    now = datetime.now(timezone.utc)
    payload = {
        "sub":      str(user_id),
        "username": username,
        "role":     role,
        "iat":      int(now.timestamp()),
        "exp":      int((now + timedelta(hours=_JWT_TTL_HR)).timestamp()),
    }
    return jwt.encode(payload, secret, algorithm=_JWT_ALG)


def decode_token(token: str) -> dict:
    secret = _ensure_secret()
    try:
        return jwt.decode(token, secret, algorithms=[_JWT_ALG])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="token หมดอายุ — ล็อกอินใหม่")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="token ไม่ถูกต้อง")


# ─── DB operations ───────────────────────────────────────────────────────────

def _get_user_by_name(username: str) -> Optional[dict]:
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT id, username, password_hash, role, last_login "
            "FROM users WHERE username = %s",
            (username,),
        )
        row = cur.fetchone()
    if not row:
        return None
    return {
        "id":            row[0],
        "username":      row[1],
        "password_hash": row[2],
        "role":          row[3],
        "last_login":    row[4],
    }


def _touch_last_login(user_id: int) -> None:
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute("UPDATE users SET last_login = NOW() WHERE id = %s", (user_id,))
        conn.commit()


def login(username: str, password: str) -> dict:
    """ตรวจ user/pass — คืน {token, username, role} ถ้าผ่าน, ไม่ผ่านโยน 401"""
    user = _get_user_by_name(username)
    if not user or not verify_password(password, user["password_hash"]):
        # ข้อความเดียวกันทั้งสองกรณี — กัน user enumeration
        raise HTTPException(status_code=401, detail="username หรือ password ไม่ถูกต้อง")
    _touch_last_login(user["id"])
    token = create_token(user["id"], user["username"], user["role"])
    return {"token": token, "username": user["username"], "role": user["role"]}


def change_password(user_id: int, old_password: str, new_password: str) -> None:
    if len(new_password) < 6:
        raise HTTPException(status_code=400, detail="password อย่างน้อย 6 ตัวอักษร")
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT password_hash FROM users WHERE id = %s", (user_id,))
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="ไม่พบ user")
        if not verify_password(old_password, row[0]):
            raise HTTPException(status_code=401, detail="password เดิมไม่ถูกต้อง")
        cur.execute(
            "UPDATE users SET password_hash = %s WHERE id = %s",
            (hash_password(new_password), user_id),
        )
        conn.commit()


def set_password(username: str, new_password: str) -> None:
    """admin reset password — ไม่ต้องตรวจ password เดิม (ใช้จาก CLI)"""
    if len(new_password) < 6:
        raise ValueError("password อย่างน้อย 6 ตัวอักษร")
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(
            "UPDATE users SET password_hash = %s WHERE username = %s",
            (hash_password(new_password), username),
        )
        if cur.rowcount == 0:
            raise ValueError(f"ไม่พบ user '{username}'")
        conn.commit()


def add_user(username: str, password: str, role: str) -> None:
    if role not in ("admin", "viewer"):
        raise ValueError("role ต้องเป็น 'admin' หรือ 'viewer'")
    if len(password) < 6:
        raise ValueError("password อย่างน้อย 6 ตัวอักษร")
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO users (username, password_hash, role) VALUES (%s, %s, %s)",
            (username, hash_password(password), role),
        )
        conn.commit()


def delete_user(username: str) -> None:
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM users WHERE username = %s", (username,))
        if cur.rowcount == 0:
            raise ValueError(f"ไม่พบ user '{username}'")
        conn.commit()


def list_users() -> list:
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT id, username, role, created_at, last_login "
            "FROM users ORDER BY id"
        )
        rows = cur.fetchall()
    return [
        {"id": r[0], "username": r[1], "role": r[2],
         "created_at": r[3].isoformat() if r[3] else None,
         "last_login": r[4].isoformat() if r[4] else None}
        for r in rows
    ]


def bootstrap_default_users() -> None:
    """ตอน boot ถ้าตาราง users ว่าง → seed admin + viewer"""
    try:
        with get_connection() as conn, conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM users")
            count = cur.fetchone()[0]
            if count > 0:
                return
            for username, password, role in _DEFAULT_USERS:
                cur.execute(
                    "INSERT INTO users (username, password_hash, role) "
                    "VALUES (%s, %s, %s)",
                    (username, hash_password(password), role),
                )
            conn.commit()
            print(f"[AUTH] seed default users: "
                  f"{', '.join(u for u, _, _ in _DEFAULT_USERS)}")
    except Exception as e:
        print(f"[AUTH] bootstrap failed: {e}")


# ─── FastAPI dependencies ────────────────────────────────────────────────────

def _extract_bearer(authorization: Optional[str]) -> str:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="ต้องส่ง Authorization: Bearer <token>")
    return authorization.split(" ", 1)[1].strip()


def get_current_user(authorization: Optional[str] = Header(None)) -> dict:
    """FastAPI dependency — verify token, คืน {id, username, role}"""
    token = _extract_bearer(authorization)
    payload = decode_token(token)
    return {
        "id":       int(payload.get("sub", 0)),
        "username": payload.get("username", ""),
        "role":     payload.get("role", ""),
    }


def require_admin(authorization: Optional[str] = Header(None)) -> dict:
    user = get_current_user(authorization)
    if user["role"] != "admin":
        raise HTTPException(status_code=403, detail="admin เท่านั้น")
    return user
