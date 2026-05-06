"""
stream_server.py — MJPEG streaming + JSON state API (Multi-Camera)
====================================================
Endpoints (per-camera):
  GET  /cameras              → list camera IDs ที่ active
  GET  /stream/{cam_id}      → MJPEG video stream
  GET  /snapshot/{cam_id}    → ภาพเดี่ยว JPEG
  GET  /state/{cam_id}       → JSON state สำหรับ canvas overlay
  GET  /snap/{cam_id}/{name} → thumbnail หน้าคนใน panel

Camera Management (GUI):
  GET    /cameras/config             → รายการกล้องทั้งหมดจาก cameras.json
  POST   /cameras/config             → เพิ่มกล้องใหม่
  PUT    /cameras/config/{cam_id}    → แก้ไข config กล้อง
  DELETE /cameras/config/{cam_id}    → ลบกล้อง

Legacy single-cam endpoints (→ cam1, backward compat):
  GET  /stream               → /stream/cam1
  GET  /snapshot             → /snapshot/cam1
  GET  /state                → /state/cam1
  GET  /snap/{name}          → /snap/cam1/{name}
  GET  /status               → ตรวจว่า stream พร้อม
  GET  /window               → ดูสถานะหน้าต่าง OpenCV
  POST /window               → toggle หน้าต่าง OpenCV

วิธีใช้:
  import stream_server
  stream_server.start()
  stream_server.push_frame(cam_id, frame)
  stream_server.push_state(cam_id, state_dict)
  stream_server.push_snapshot(cam_id, name, crop)
  stream_server.get_cv_window()
"""

import asyncio
import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Optional

import cv2
from dotenv import load_dotenv
from fastapi import FastAPI, Body, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, Response, JSONResponse
from pydantic import BaseModel
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
import uvicorn

load_dotenv()

import auth as _auth

# ─── cameras.json path ────────────────────────────────────────────────────────
_CAMERAS_JSON = Path(__file__).parent / "cameras.json"


# ─── Camera config helpers ────────────────────────────────────────────────────

def _load_cam_configs() -> list:
    """โหลด camera configs จาก cameras.json (ถ้ามี) หรือ fallback ไป config.CAMERAS"""
    if _CAMERAS_JSON.exists():
        try:
            with open(_CAMERAS_JSON, encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"[CAM_MGR] cameras.json อ่านไม่ได้: {e}")
    import config as _c
    return list(getattr(_c, "CAMERAS", []))


def _save_cam_configs(configs: list):
    """บันทึก camera configs ไปยัง cameras.json"""
    with open(_CAMERAS_JSON, "w", encoding="utf-8") as f:
        json.dump(configs, f, ensure_ascii=False, indent=2)


def _mask_url(url: str) -> str:
    """ซ่อน credentials ใน URL จริง — $VAR_NAME แสดงตรงๆ ได้เลย"""
    if not url or url.startswith("$"):
        return url
    import re
    return re.sub(r'(://)[^@/]+@', r'\1***@', url)


def _next_cam_id(configs: list) -> str:
    """หา ID ถัดไป เช่น cam4 ถ้ามี cam1-cam3 แล้ว"""
    nums = []
    for c in configs:
        cid = c.get("id", "")
        if cid.startswith("cam"):
            try:
                nums.append(int(cid[3:]))
            except ValueError:
                pass
    return f"cam{max(nums, default=0) + 1}"


class CameraConfigRequest(BaseModel):
    name: str
    cam_type: str = "usb"       # "usb" หรือ "ip"
    url: Optional[str] = ""
    index: Optional[int] = 0
    flip: bool = False

# ─── Per-camera buffers ───────────────────────────────────────────────────────
_lock        = threading.Lock()
_cam_frames: dict[str, bytes | None]         = {}   # cam_id → latest JPEG
_cam_counts: dict[str, int]                  = {}   # cam_id → frame counter
_cam_frame_ts: dict[str, float]              = {}   # cam_id → last frame ts (epoch)
_cam_states: dict[str, dict]                 = {}   # cam_id → latest state
_cam_snaps:      dict[str, dict[str, bytes]] = {}   # cam_id → {name: face-crop jpeg}
_cam_snaps_full: dict[str, dict[str, bytes]] = {}   # cam_id → {name: full-frame jpeg}

# ─── OpenCV window flag ───────────────────────────────────────────────────────
import config as _cfg
_cv_window: bool = _cfg.CV_WINDOW
del _cfg

_DEFAULT_CAM  = "cam1"
_active_cam   = _DEFAULT_CAM   # กล้องที่ legacy endpoints (/stream, /state, /snap) ชี้อยู่

# ─── Lifecycle callbacks (registered by main.py) ─────────────────────────────
# main.py เรียก register_lifecycle() เพื่อให้ stream_server รู้จัก start/stop fn
_start_fn = None   # callable() → start camera threads
_stop_fn  = None   # callable() → stop camera threads
_api_proc = None   # subprocess สำหรับ api.py

def register_lifecycle(start_fn, stop_fn):
    """เรียกจาก main.py เพื่อลงทะเบียน start/stop callback"""
    global _start_fn, _stop_fn
    _start_fn = start_fn
    _stop_fn  = stop_fn


# ─── Public API (เรียกจาก main.py) ───────────────────────────────────────────

def push_frame(cam_id: str, frame, quality: int = 70):
    """Push raw camera frame สำหรับ cam_id — thread-safe"""
    ok, buf = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, quality])
    if not ok:
        return
    with _lock:
        _cam_frames[cam_id] = buf.tobytes()
        _cam_counts[cam_id] = _cam_counts.get(cam_id, 0) + 1
        _cam_frame_ts[cam_id] = time.time()


def push_state(cam_id: str, state: dict):
    """Push detection state สำหรับ frontend canvas overlay"""
    with _lock:
        _cam_states[cam_id] = state


def push_snapshot(cam_id: str, name: str, crop, quality: int = 80):
    """Push face crop thumbnail สำหรับ /snap/{cam_id}/{name}"""
    if crop is None or crop.size == 0:
        return
    ok, buf = cv2.imencode('.jpg', crop, [cv2.IMWRITE_JPEG_QUALITY, quality])
    if ok:
        with _lock:
            if cam_id not in _cam_snaps:
                _cam_snaps[cam_id] = {}
            _cam_snaps[cam_id][name] = buf.tobytes()


def push_snapshot_full(cam_id: str, name: str, frame, quality: int = 75):
    """Push full camera frame สำหรับ /snapfull/{cam_id}/{name} (ใช้แสดงใน Dashboard)"""
    if frame is None or frame.size == 0:
        return
    ok, buf = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, quality])
    if ok:
        with _lock:
            if cam_id not in _cam_snaps_full:
                _cam_snaps_full[cam_id] = {}
            _cam_snaps_full[cam_id][name] = buf.tobytes()


def get_cv_window() -> bool:
    """main.py เรียกเพื่อตรวจว่าควรแสดง cv2.imshow ไหม"""
    return _cv_window


def set_cv_window(val: bool):
    """ตั้งค่า cv_window flag (เรียกจาก main ก่อน spawn threads)"""
    global _cv_window
    _cv_window = val


def set_active_cam(cam_id: str):
    """เปลี่ยนกล้อง default สำหรับ legacy endpoints"""
    global _active_cam
    _active_cam = cam_id


# ─── FastAPI app ──────────────────────────────────────────────────────────────
app = FastAPI(title="FaceReg", docs_url=None)

# Rate limiter — กัน brute-force ที่ /auth/* (ดู @limiter.limit ที่ endpoint)
limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter


def _rate_limit_handler(request: Request, exc: RateLimitExceeded) -> Response:
    """แทน default handler ของ slowapi — คืนข้อความภาษาไทยพร้อมเวลาที่ต้องรอ
    Frontend อ่านจาก response.json().detail (เหมือน 401/403 error อื่น ๆ)"""
    # inject headers ก่อนเพื่อดึง Retry-After ที่ slowapi คำนวณให้
    base = JSONResponse(status_code=429, content={})
    base = limiter._inject_headers(base, request.state.view_rate_limit)
    retry_s = int(base.headers.get("Retry-After", "60"))
    wait_text = f"{retry_s} วินาที" if retry_s < 60 else f"{(retry_s + 59) // 60} นาที"

    # อ่าน amount จาก rate-limit item (5 per minute → amount=5)
    rate_info = request.state.view_rate_limit
    item = rate_info[0] if isinstance(rate_info, tuple) else rate_info
    amount = getattr(item, "amount", "?")

    path = request.url.path
    if path == "/auth/login":
        detail = (f"คุณใส่รหัสผิด {amount} ครั้งติดต่อกัน "
                  f"— กรุณาลองใหม่ในอีก {wait_text}")
    elif path == "/auth/change-password":
        detail = (f"ขอเปลี่ยนรหัสบ่อยเกินไป (เกิน {amount} ครั้ง/นาที) "
                  f"— กรุณาลองใหม่ในอีก {wait_text}")
    else:
        detail = (f"ส่งคำขอเกินจำนวนที่กำหนด ({amount} ครั้ง) "
                  f"— กรุณาลองใหม่ในอีก {wait_text}")

    response = JSONResponse(status_code=429, content={"detail": detail})
    return limiter._inject_headers(response, request.state.view_rate_limit)


app.add_exception_handler(RateLimitExceeded, _rate_limit_handler)

# CORS — อนุญาตเฉพาะ origin ที่ตั้งใน .env (default: localhost vite/preview)
_cors_env = os.environ.get("CORS_ORIGINS", "http://localhost:5173,http://localhost:4173")
_cors_origins = [o.strip() for o in _cors_env.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)


# ─── Auth dependencies ───────────────────────────────────────────────────────
# ใช้ require_admin ครอบ endpoint mutating ทุกตัว
require_admin = _auth.require_admin
get_current_user = _auth.get_current_user


# ─── Auth endpoints ──────────────────────────────────────────────────────────
class _LoginReq(BaseModel):
    username: str
    password: str


class _ChangePwReq(BaseModel):
    old_password: str
    new_password: str


@app.post('/auth/login')
@limiter.limit("5/minute")        # กัน brute-force — 5 ครั้ง/นาที/IP
async def auth_login(request: Request, req: _LoginReq):
    """username/password → JWT token (exp 8h default)"""
    return _auth.login(req.username, req.password)


@app.get('/auth/me')
async def auth_me(user: dict = Depends(get_current_user)):
    """ตรวจ token + คืน user info (frontend ใช้เช็คว่ายัง login อยู่)
    must_change_password อ่านจาก DB ทุกครั้ง (ไม่เก็บใน JWT — กัน stale state)"""
    db_user = _auth._get_user_by_name(user["username"])
    return {
        "username":             user["username"],
        "role":                 user["role"],
        "must_change_password": bool(db_user["must_change_password"]) if db_user else False,
    }


@app.post('/auth/change-password')
@limiter.limit("10/minute")       # ผ่าน auth แล้ว แต่ยัง limit กัน password guessing
async def auth_change_password(request: Request, req: _ChangePwReq,
                               user: dict = Depends(get_current_user)):
    _auth.change_password(user["id"], req.old_password, req.new_password)
    return {"success": True}


async def _mjpeg_gen(cam_id: str):
    prev_count = -1
    while True:
        with _lock:
            jpeg  = _cam_frames.get(cam_id)
            count = _cam_counts.get(cam_id, 0)
        if jpeg and count != prev_count:
            prev_count = count
            yield (
                b'--frame\r\n'
                b'Content-Type: image/jpeg\r\n\r\n'
                + jpeg +
                b'\r\n'
            )
        else:
            await asyncio.sleep(0.01)


# ─── Per-camera endpoints ─────────────────────────────────────────────────────

@app.get('/cameras', dependencies=[Depends(get_current_user)])
async def cameras_list():
    """List camera IDs (in-memory buffer)"""
    with _lock:
        ids = set(_cam_frames.keys())
    return {"cameras": sorted(ids), "active": _active_cam}


@app.post('/cameras/{cam_id}/activate', dependencies=[Depends(require_admin)])
async def activate_cam(cam_id: str):
    """เปลี่ยนกล้อง active สำหรับ legacy endpoints"""
    global _active_cam
    with _lock:
        known = list(_cam_frames.keys())
    if cam_id not in known:
        return Response(status_code=404, content=f"cam_id '{cam_id}' ไม่พบ")
    _active_cam = cam_id
    print(f'[STREAM] Active cam → {cam_id}')
    return {"active": _active_cam}


# ─── Camera Config CRUD ───────────────────────────────────────────────────────

@app.get('/cameras/config', dependencies=[Depends(get_current_user)])
async def get_cameras_config():
    """รายการกล้องทั้งหมดจาก cameras.json (รวมสถานะ active, URL masked)
    เปิดให้ viewer ดูได้เพราะ response ไม่ leak credentials (URL masked แล้ว)"""
    configs = _load_cam_configs()
    with _lock:
        active_ids = set(_cam_frames.keys())
    result = []
    for c in configs:
        entry = {**c, "active": c.get("id", "") in active_ids}
        if "url" in entry:
            entry["url"] = _mask_url(entry["url"])
        result.append(entry)
    return {"cameras": result}


def _norm_url(u: str) -> str:
    """normalize URL สำหรับเทียบซ้ำ: lowercase + ตัด trailing slash + ตัด whitespace"""
    return (u or "").strip().rstrip("/").lower()


def _check_dup(configs: list, req: CameraConfigRequest, exclude_id: str = "") -> str:
    """
    ตรวจกล้องซ้ำ — return error message ภาษาไทย ("" = ไม่ซ้ำ)
    USB: ห้าม name ซ้ำ, ห้าม index ซ้ำ (เทียบเฉพาะกล้อง USB ด้วยกัน)
    IP : ห้าม name ซ้ำ, ห้าม url ซ้ำ (เทียบเฉพาะกล้อง IP ด้วยกัน)
    name ตรวจ case-insensitive ข้ามประเภท (USB และ IP จะมี name เดียวกันก็ไม่ได้)
    """
    new_name = req.name.strip().lower()
    is_ip    = (req.cam_type == "ip")

    for c in configs:
        if c.get("id") == exclude_id:
            continue
        # name ห้ามซ้ำ ข้ามประเภท
        if (c.get("name", "").strip().lower() == new_name):
            return f"ชื่อกล้อง '{req.name.strip()}' ถูกใช้แล้ว (กล้อง {c.get('id')})"
        # index ซ้ำ — เฉพาะ USB-USB
        if not is_ip and "index" in c and c.get("index") == (req.index or 0):
            return f"USB index {req.index or 0} ถูกใช้โดยกล้อง {c.get('id')} แล้ว"
        # url ซ้ำ — เฉพาะ IP-IP
        if is_ip and "url" in c and _norm_url(c.get("url", "")) == _norm_url(req.url or ""):
            if _norm_url(req.url or ""):   # ถ้า url ว่างเปล่าก็ไม่นับซ้ำ (ให้ name validation จับ)
                return f"URL นี้ถูกใช้โดยกล้อง {c.get('id')} แล้ว"
    return ""


@app.post('/cameras/config', dependencies=[Depends(require_admin)])
async def add_camera(req: CameraConfigRequest):
    """เพิ่มกล้องใหม่ — ID เรียงต่ออัตโนมัติ (cam1, cam2, ...)"""
    if not req.name.strip():
        return Response(status_code=400, content="ต้องระบุชื่อกล้อง")
    if req.cam_type == "ip" and not (req.url or "").strip():
        return Response(status_code=400, content="ต้องระบุ URL ของกล้อง IP")

    configs = _load_cam_configs()   # อาจ fallback จาก config.CAMERAS ถ้ายังไม่มี JSON

    dup_err = _check_dup(configs, req)
    if dup_err:
        return Response(status_code=409, content=dup_err)

    cam_id  = _next_cam_id(configs)
    new_cam: dict = {"id": cam_id, "name": req.name.strip(), "flip": req.flip}

    if req.cam_type == "ip":
        new_cam["url"] = (req.url or "").strip()
    else:
        new_cam["index"] = req.index if req.index is not None else 0

    configs.append(new_cam)
    _save_cam_configs(configs)
    print(f"[CAM_MGR] เพิ่มกล้อง {cam_id} ({req.name})")
    return {"success": True, "camera": new_cam}


@app.put('/cameras/config/{cam_id}', dependencies=[Depends(require_admin)])
async def update_camera(cam_id: str, req: CameraConfigRequest):
    """แก้ไข config กล้อง — ต้อง restart ระบบเพื่อให้มีผล"""
    if not req.name.strip():
        return Response(status_code=400, content="ต้องระบุชื่อกล้อง")
    if req.cam_type == "ip" and not (req.url or "").strip():
        return Response(status_code=400, content="ต้องระบุ URL ของกล้อง IP")

    configs = _load_cam_configs()

    dup_err = _check_dup(configs, req, exclude_id=cam_id)
    if dup_err:
        return Response(status_code=409, content=dup_err)

    for i, c in enumerate(configs):
        if c.get("id") == cam_id:
            updated: dict = {"id": cam_id, "name": req.name.strip(), "flip": req.flip}
            if req.cam_type == "ip":
                updated["url"]   = (req.url or "").strip()
            else:
                updated["index"] = req.index if req.index is not None else 0
            configs[i] = updated
            _save_cam_configs(configs)
            print(f"[CAM_MGR] แก้ไขกล้อง {cam_id}")
            return {"success": True, "camera": updated}

    return Response(status_code=404, content=f"cam_id '{cam_id}' ไม่พบ")


@app.delete('/cameras/config/{cam_id}', dependencies=[Depends(require_admin)])
async def delete_camera(cam_id: str):
    """ลบกล้องออกจาก cameras.json — ต้อง restart ระบบเพื่อให้มีผล"""
    configs = _load_cam_configs()
    new_configs = [c for c in configs if c.get("id") != cam_id]
    if len(new_configs) == len(configs):
        return Response(status_code=404, content=f"cam_id '{cam_id}' ไม่พบ")
    _save_cam_configs(new_configs)
    print(f"[CAM_MGR] ลบกล้อง {cam_id}")
    return {"success": True, "deleted": cam_id}


@app.get('/admin', response_class=Response, dependencies=[Depends(require_admin)])
async def admin_page():
    """หน้า GUI จัดการกล้อง — http://localhost:8001/admin"""
    html = r"""<!DOCTYPE html>
<html lang="th">
<head>
  <meta charset="UTF-8">
  <title>FaceReg — Camera Manager</title>
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <style>
    *{box-sizing:border-box;margin:0;padding:0}
    body{background:#0d0d0d;color:#e0e0e0;font-family:'Segoe UI',sans-serif;min-height:100vh}
    /* ─── Header ─── */
    .hdr{display:flex;align-items:center;gap:14px;padding:18px 24px;
         border-bottom:1px solid #1e1e1e;background:#111}
    .hdr-title{font-size:17px;font-weight:600;color:#fff;letter-spacing:.4px}
    .hdr-sub{font-size:12px;color:#555;font-family:monospace}
    .hdr-right{margin-left:auto;display:flex;gap:10px;align-items:center}
    /* ─── Notice ─── */
    .notice{background:#1a1200;border:1px solid #403000;border-radius:6px;
            padding:10px 16px;font-size:12px;color:#c8a000;margin:20px 24px 0}
    /* ─── Grid ─── */
    .grid{display:flex;flex-wrap:wrap;gap:16px;padding:20px 24px}
    /* ─── Camera Card ─── */
    .card{background:#141414;border:1px solid #252525;border-radius:10px;
          overflow:hidden;width:300px;flex-shrink:0;transition:border-color .2s}
    .card:hover{border-color:#333}
    .card.online{border-color:#1a4a1a}
    /* snapshot area */
    .snap-wrap{position:relative;height:160px;background:#0a0a0a;overflow:hidden}
    .snap-wrap img{width:100%;height:100%;object-fit:cover;display:block}
    .snap-wrap .no-snap{display:flex;align-items:center;justify-content:center;
                        height:100%;color:#333;font-size:12px;font-family:monospace}
    .cam-id-badge{position:absolute;top:8px;left:8px;background:rgba(0,0,0,.75);
                  color:#ccc;font-size:10px;font-family:monospace;padding:3px 8px;
                  border-radius:4px}
    .status-dot{position:absolute;top:10px;right:10px;width:10px;height:10px;
                border-radius:50%;background:#333;border:2px solid #222}
    .status-dot.online{background:#22cc44;border-color:#166626}
    /* card body */
    .card-body{padding:12px 14px}
    .cam-name{font-size:14px;font-weight:600;color:#fff;margin-bottom:4px;
              white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
    .cam-meta{font-size:11px;color:#555;font-family:monospace;margin-bottom:10px;
              white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
    .cam-meta span{color:#888}
    .card-actions{display:flex;gap:8px}
    /* ─── Buttons ─── */
    .btn{border:none;border-radius:5px;font-size:12px;font-weight:500;
         cursor:pointer;padding:6px 14px;transition:opacity .15s}
    .btn:hover{opacity:.8}
    .btn-primary{background:#00a8cc;color:#000}
    .btn-secondary{background:#252525;color:#aaa;border:1px solid #333}
    .btn-danger{background:#3a0a0a;color:#e05050;border:1px solid #5a1515}
    .btn-success{background:#0a2a18;color:#44cc77;border:1px solid #1a5a35}
    .btn-add{background:#004a66;color:#00d4ff;border:1px solid #006688;
             font-size:13px;padding:8px 20px;border-radius:6px}
    .stream-link{color:#00aacc;font-size:11px;text-decoration:none;font-family:monospace}
    .stream-link:hover{text-decoration:underline}
    /* ─── Modal ─── */
    .modal-bg{display:none;position:fixed;inset:0;background:rgba(0,0,0,.7);
              z-index:100;align-items:center;justify-content:center}
    .modal-bg.open{display:flex}
    .modal{background:#161616;border:1px solid #2a2a2a;border-radius:12px;
           padding:28px;width:420px;max-width:95vw}
    .modal h2{font-size:15px;font-weight:600;margin-bottom:20px;color:#fff}
    .form-row{margin-bottom:14px}
    .form-row label{display:block;font-size:11px;color:#777;margin-bottom:5px;
                    font-family:monospace;text-transform:uppercase;letter-spacing:.5px}
    .form-row input,.form-row select{
      width:100%;background:#0d0d0d;border:1px solid #2a2a2a;border-radius:5px;
      padding:8px 10px;color:#e0e0e0;font-size:13px;font-family:monospace;outline:none}
    .form-row input:focus,.form-row select:focus{border-color:#00a8cc}
    .form-row select option{background:#161616}
    .type-row{display:flex;gap:16px}
    .type-row label{display:flex;align-items:center;gap:6px;cursor:pointer;
                    font-size:13px;color:#bbb;font-family:monospace;
                    text-transform:none;letter-spacing:0}
    .flip-row{display:flex;align-items:center;gap:8px;font-size:13px;color:#bbb}
    .flip-row input[type=checkbox]{width:16px;height:16px;cursor:pointer;accent-color:#00a8cc}
    .modal-actions{display:flex;gap:10px;margin-top:22px;justify-content:flex-end}
    /* ─── Toast ─── */
    .toast{position:fixed;bottom:24px;right:24px;padding:10px 18px;border-radius:6px;
           font-size:13px;font-family:monospace;z-index:200;display:none;
           transition:opacity .3s}
    .toast.ok{background:#00a844;color:#fff}
    .toast.err{background:#cc2222;color:#fff}
    /* ─── Empty state ─── */
    .empty{color:#333;font-family:monospace;font-size:13px;padding:40px 24px}
  </style>
</head>
<body>

<div class="hdr">
  <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#00aacc" stroke-width="1.8">
    <circle cx="12" cy="12" r="3"/><path d="M2 12h3M19 12h3M12 2v3M12 19v3"/>
    <rect x="4" y="7" width="16" height="10" rx="2" stroke="#00aacc" stroke-width="1.5" fill="none"/>
  </svg>
  <div>
    <div class="hdr-title">Camera Manager</div>
    <div class="hdr-sub">FaceReg — จัดการกล้องผ่าน GUI</div>
  </div>
  <div class="hdr-right">
    <button class="btn btn-add" onclick="openAdd()">+ เพิ่มกล้อง</button>
  </div>
</div>

<div class="notice">
  ⚠&nbsp; การเพิ่ม / แก้ไข / ลบกล้อง จะมีผลหลัง <strong>restart ระบบ</strong> เท่านั้น
</div>

<div class="grid" id="grid">
  <div class="empty">กำลังโหลด...</div>
</div>

<!-- ─── Modal: Add / Edit ─── -->
<div class="modal-bg" id="modal-bg">
  <div class="modal">
    <h2 id="modal-title">เพิ่มกล้องใหม่</h2>

    <div class="form-row">
      <label>ชื่อกล้อง (Camera Name)</label>
      <input id="f-name" type="text" placeholder="เช่น CAM_ENTRANCE" maxlength="40">
    </div>

    <div class="form-row">
      <label>ประเภทกล้อง</label>
      <div class="type-row">
        <label><input type="radio" name="cam-type" value="usb" checked onchange="typeChange()"> USB Webcam</label>
        <label><input type="radio" name="cam-type" value="ip" onchange="typeChange()"> IP Camera (RTSP/HTTP)</label>
      </div>
    </div>

    <div class="form-row" id="row-index">
      <label>USB Index (0, 1, 2 ...)</label>
      <input id="f-index" type="number" value="0" min="0" max="20">
    </div>

    <div class="form-row" id="row-url" style="display:none">
      <label>RTSP / HTTP URL</label>
      <input id="f-url" type="text" placeholder="rtsp://admin:pass@192.168.1.x:554/stream">
    </div>

    <div class="form-row">
      <label>&nbsp;</label>
      <div class="flip-row">
        <input type="checkbox" id="f-flip">
        <span>กลับภาพซ้าย-ขวา (Flip Horizontal)</span>
      </div>
    </div>

    <div class="modal-actions">
      <button class="btn btn-secondary" onclick="closeModal()">ยกเลิก</button>
      <button class="btn btn-primary" onclick="saveCamera()">บันทึก</button>
    </div>
  </div>
</div>

<div class="toast" id="toast"></div>

<script>
let _editId = null   // null = add mode, string = edit mode
let _refreshTimer = null

/* ─── Load & render cameras ─── */
async function loadCameras() {
  const res = await fetch('/cameras/config')
  if (!res.ok) { showToast('โหลดข้อมูลไม่ได้', 'err'); return }
  const data = await res.json()
  renderGrid(data.cameras)
}

function renderGrid(cameras) {
  const grid = document.getElementById('grid')
  if (!cameras || cameras.length === 0) {
    grid.innerHTML = '<div class="empty">ยังไม่มีกล้อง — กด "+ เพิ่มกล้อง" เพื่อเริ่มต้น</div>'
    return
  }

  grid.innerHTML = cameras.map(c => {
    const isOnline = c.active
    const dotCls   = isOnline ? 'status-dot online' : 'status-dot'
    const cardCls  = isOnline ? 'card online' : 'card'

    // type label
    let typeMeta = ''
    if (c.url !== undefined && c.url !== '') {
      const short = c.url.length > 36 ? c.url.slice(0,33)+'...' : c.url
      typeMeta = `IP: <span>${short}</span>`
    } else if (c.index !== undefined) {
      typeMeta = `USB index: <span>${c.index}</span>`
    } else if (c.url === '') {
      typeMeta = `IP: <span>(ยังไม่ได้ตั้ง URL)</span>`
    }
    const flipMeta = c.flip ? '&nbsp;&nbsp;Flip: <span>✓</span>' : '&nbsp;&nbsp;Flip: <span>✗</span>'

    const snap = isOnline
      ? `<img id="snap-${c.id}" src="/snapshot/${c.id}?t=${Date.now()}"
             onerror="this.style.display='none';this.nextElementSibling.style.display='flex'">`
      : ''
    const noSnap = `<div class="no-snap" style="${isOnline?'display:none':''}">ไม่มีสัญญาณ</div>`

    return `
    <div class="${cardCls}" id="card-${c.id}">
      <div class="snap-wrap">
        ${snap}${noSnap}
        <div class="cam-id-badge">${c.id}</div>
        <div class="${dotCls}" title="${isOnline?'กำลังทำงาน':'ออฟไลน์'}"></div>
      </div>
      <div class="card-body">
        <div class="cam-name" title="${c.name}">${c.name}</div>
        <div class="cam-meta">${typeMeta}${flipMeta}</div>
        <div class="card-actions">
          <a class="stream-link" href="/stream/${c.id}" target="_blank">/stream/${c.id} ↗</a>
          <button class="btn btn-secondary" style="margin-left:auto"
                  onclick="openEdit('${c.id}')">แก้ไข</button>
          <button class="btn btn-danger"
                  onclick="deleteCamera('${c.id}','${c.name}')">ลบ</button>
        </div>
      </div>
    </div>`
  }).join('')
}

/* ─── Snapshot refresh (active cams only) ─── */
function refreshSnaps() {
  document.querySelectorAll('img[id^="snap-"]').forEach(img => {
    const base = img.src.split('?')[0]
    img.src = base + '?t=' + Date.now()
  })
}
setInterval(refreshSnaps, 2500)
setInterval(loadCameras, 5000)   // sync status dots ทุก 5 วิ

/* ─── Type toggle ─── */
function typeChange() {
  const val = document.querySelector('input[name="cam-type"]:checked').value
  document.getElementById('row-index').style.display = val==='usb' ? '' : 'none'
  document.getElementById('row-url').style.display   = val==='ip'  ? '' : 'none'
}

/* ─── Open Add modal ─── */
function openAdd() {
  _editId = null
  document.getElementById('modal-title').textContent = 'เพิ่มกล้องใหม่'
  document.getElementById('f-name').value  = ''
  document.getElementById('f-index').value = '0'
  document.getElementById('f-url').value   = ''
  document.getElementById('f-flip').checked = false
  document.querySelectorAll('input[name="cam-type"]')[0].checked = true
  typeChange()
  document.getElementById('modal-bg').classList.add('open')
  document.getElementById('f-name').focus()
}

/* ─── Open Edit modal ─── */
async function openEdit(camId) {
  const res   = await fetch('/cameras/config')
  const data  = await res.json()
  const cam   = data.cameras.find(c => c.id === camId)
  if (!cam) return

  _editId = camId
  document.getElementById('modal-title').textContent = `แก้ไขกล้อง — ${camId}`
  document.getElementById('f-name').value   = cam.name  || ''
  document.getElementById('f-flip').checked = cam.flip  || false

  const isIP = cam.url !== undefined
  document.querySelectorAll('input[name="cam-type"]').forEach(r => {
    r.checked = (r.value === (isIP ? 'ip' : 'usb'))
  })
  document.getElementById('f-url').value   = cam.url   || ''
  document.getElementById('f-index').value = cam.index !== undefined ? cam.index : 0
  typeChange()
  document.getElementById('modal-bg').classList.add('open')
  document.getElementById('f-name').focus()
}

function closeModal() {
  document.getElementById('modal-bg').classList.remove('open')
}

/* ─── Save (Add or Edit) ─── */
async function saveCamera() {
  const name     = document.getElementById('f-name').value.trim()
  const cam_type = document.querySelector('input[name="cam-type"]:checked').value
  const url      = document.getElementById('f-url').value.trim()
  const index    = parseInt(document.getElementById('f-index').value) || 0
  const flip     = document.getElementById('f-flip').checked

  if (!name) { showToast('กรุณาระบุชื่อกล้อง', 'err'); return }

  const body = JSON.stringify({name, cam_type, url, index, flip})
  const endpoint = _editId ? `/cameras/config/${_editId}` : '/cameras/config'
  const method   = _editId ? 'PUT' : 'POST'

  const res = await fetch(endpoint, {
    method, headers: {'Content-Type':'application/json'}, body
  })
  if (!res.ok) {
    const msg = await res.text()
    showToast('เกิดข้อผิดพลาด: '+msg, 'err')
    return
  }
  closeModal()
  showToast(_editId ? `แก้ไขกล้อง ${_editId} แล้ว` : 'เพิ่มกล้องใหม่แล้ว', 'ok')
  loadCameras()
}

/* ─── Delete ─── */
async function deleteCamera(camId, camName) {
  if (!confirm(`ลบกล้อง "${camName}" (${camId})?\n\nกล้องจะถูกลบออกจากระบบ — ต้อง restart เพื่อให้มีผล`)) return

  const res = await fetch(`/cameras/config/${camId}`, {method:'DELETE'})
  if (!res.ok) {
    showToast('ลบไม่ได้: '+camId, 'err')
    return
  }
  showToast(`ลบกล้อง ${camId} แล้ว`, 'ok')
  loadCameras()
}

/* ─── Toast ─── */
function showToast(msg, type='ok') {
  const t = document.getElementById('toast')
  t.textContent = msg
  t.className   = `toast ${type}`
  t.style.display = 'block'
  // error อ่านนานกว่า — duplicate message ภาษาไทยอาจยาว
  const dur = type === 'err' ? 6000 : 3000
  setTimeout(() => t.style.display='none', dur)
}

/* ─── Close modal on backdrop click ─── */
document.getElementById('modal-bg').addEventListener('click', e => {
  if (e.target === document.getElementById('modal-bg')) closeModal()
})

/* ─── ESC key ─── */
document.addEventListener('keydown', e => {
  if (e.key === 'Escape') closeModal()
})

// initial load
loadCameras()
</script>
</body>
</html>"""
    return Response(content=html, media_type="text/html; charset=utf-8")


@app.get('/stream/{cam_id}', dependencies=[Depends(get_current_user)])
async def stream_cam(cam_id: str):
    return StreamingResponse(
        _hybrid_mjpeg_gen(cam_id),
        media_type='multipart/x-mixed-replace; boundary=frame',
    )


@app.get('/snapshot/{cam_id}', dependencies=[Depends(get_current_user)])
async def snapshot_cam(cam_id: str):
    with _lock:
        jpeg = _cam_frames.get(cam_id)
    if jpeg is None:
        return Response(status_code=503)
    return Response(content=jpeg, media_type='image/jpeg')


@app.get('/state/{cam_id}', dependencies=[Depends(get_current_user)])
async def state_cam(cam_id: str):
    with _lock:
        s = dict(_cam_states.get(cam_id, {}))
    return s


@app.get('/snap/{cam_id}/{name}', dependencies=[Depends(get_current_user)])
async def snap_person_cam(cam_id: str, name: str):
    with _lock:
        jpeg = _cam_snaps.get(cam_id, {}).get(name)
    if jpeg is None:
        return Response(status_code=404)
    return Response(content=jpeg, media_type='image/jpeg',
                    headers={'Cache-Control': 'no-store'})


@app.get('/snapfull/{cam_id}/{name}', dependencies=[Depends(get_current_user)])
async def snapfull_person_cam(cam_id: str, name: str):
    with _lock:
        jpeg = _cam_snaps_full.get(cam_id, {}).get(name)
    if jpeg is None:
        return Response(status_code=404)
    return Response(content=jpeg, media_type='image/jpeg',
                    headers={'Cache-Control': 'no-store'})


# ─── Push endpoints (headless main.py → stream_server in-memory cache) ────────
# ใช้แทนการเขียนไฟล์ live_frame / live_state / live_snap / live_snapfull
# TODO(security): /push/* ยังไม่ guard — ถ้า bind 0.0.0.0 จะเปิดให้ใครใน LAN
# push frame ปลอมได้ ควรเพิ่ม INTERNAL_PUSH_TOKEN (.env) + ตรวจใน header
@app.post('/push/frame/{cam_id}')
async def push_frame_endpoint(cam_id: str, request: Request):
    body = await request.body()
    if not body:
        return Response(status_code=400)
    with _lock:
        _cam_frames[cam_id] = body
        _cam_counts[cam_id] = _cam_counts.get(cam_id, 0) + 1
        _cam_frame_ts[cam_id] = time.time()
    return {'ok': True, 'bytes': len(body)}


@app.post('/push/state/{cam_id}')
async def push_state_endpoint(cam_id: str, request: Request):
    import json as _j
    try:
        state = _j.loads((await request.body()).decode('utf-8') or '{}')
    except Exception:
        return Response(status_code=400)
    with _lock:
        _cam_states[cam_id] = state
    return {'ok': True}


@app.post('/push/snap/{cam_id}/{name}')
async def push_snap_endpoint(cam_id: str, name: str, request: Request):
    body = await request.body()
    if not body:
        return Response(status_code=400)
    with _lock:
        if cam_id not in _cam_snaps:
            _cam_snaps[cam_id] = {}
        _cam_snaps[cam_id][name] = body
    return {'ok': True, 'bytes': len(body)}


@app.post('/push/snapfull/{cam_id}/{name}')
async def push_snapfull_endpoint(cam_id: str, name: str, request: Request):
    body = await request.body()
    if not body:
        return Response(status_code=400)
    with _lock:
        if cam_id not in _cam_snaps_full:
            _cam_snaps_full[cam_id] = {}
        _cam_snaps_full[cam_id][name] = body
    return {'ok': True, 'bytes': len(body)}


# ─── Cache & System control ───────────────────────────────────────────────────

@app.post('/cache/clear', dependencies=[Depends(require_admin)])
async def cache_clear():
    """ล้าง snapshot buffer ใน RAM (snap/snapfull เก็บ in-memory ทั้งหมดแล้ว)
    เก็บกวาดไฟล์ live_snap_*.jpg ที่อาจตกค้างจาก version เก่าด้วย"""
    with _lock:
        _cam_snaps.clear()
        _cam_snaps_full.clear()
    legacy_deleted = 0
    for pattern in ('live_snap_*.jpg', 'live_snapfull_*.jpg'):
        for f in _ROOT.glob(pattern):
            try:
                f.unlink()
                legacy_deleted += 1
            except OSError:
                pass
    return {'cleared': True, 'legacy_files_deleted': legacy_deleted}


_ROOT      = Path(__file__).parent
_procs: dict[str, subprocess.Popen] = {}   # 'main' | 'api' → Popen
_user_intent_started = False  # True หลัง /system/start, False หลัง /system/stop
                              # ใช้เพื่อให้ /system/status สะท้อน "ผู้ใช้กด Start หรือยัง"
                              # ไม่ใช่แค่ port probe (เพราะ npm run dev ก็เปิด api ไว้ตลอด)

# ─── Watchdog state ──────────────────────────────────────────────────────────
# respawn child process (main.py / api.py) ถ้า crash ขณะ user สั่ง Start ค้างไว้
_watchdog_thread: Optional[threading.Thread] = None
_watchdog_stop = threading.Event()
_watchdog_interval = 3.0           # วินาที: ตรวจถี่แค่ไหน
_watchdog_max_restarts = 5         # restart ได้กี่ครั้งใน window
_watchdog_window = 60.0            # วินาที: window สำหรับนับ restart
_watchdog_grace_after_start = 8.0  # วินาที: หลัง spawn ใหม่ ให้เวลา process boot
_proc_restart_log: dict[str, list] = {'main': [], 'api': []}  # timestamps
_proc_last_spawn: dict[str, float] = {'main': 0.0, 'api': 0.0}
_proc_disabled: dict[str, str] = {}  # key → reason (กันลูปไม่จบ)

# ─── In-memory active-cam detection ──────────────────────────────────────────
def _mem_active_cams(max_age: float = 5.0) -> list:
    """กล้องที่ frame ล่าสุดมีอายุ < max_age วินาที"""
    now = time.time()
    with _lock:
        return [cid for cid, ts in _cam_frame_ts.items() if (now - ts) < max_age]


async def _hybrid_mjpeg_gen(cam_id: str):
    """MJPEG generator (in-memory only) — ส่ง last frame ทันทีเมื่อ browser
    เปิด connection ใหม่ ไม่ดำขณะรอ frame ถัดไป"""
    prev_count = -1
    first      = True

    while True:
        with _lock:
            jpeg  = _cam_frames.get(cam_id)
            count = _cam_counts.get(cam_id, 0)
        if jpeg and (first or count != prev_count):
            first      = False
            prev_count = count
            yield (b'--frame\r\nContent-Type: image/jpeg\r\n\r\n'
                   + jpeg + b'\r\n')
            continue
        await asyncio.sleep(0.05)


def _proc_alive(key: str) -> bool:
    p = _procs.get(key)
    return p is not None and p.poll() is None

def _api_alive() -> bool:
    """probe port 8000 — เช็คว่ามี API server ตอบสนองไหม
    ครอบคลุมกรณีรัน uvicorn แยก (เช่น `npm run dev` เปิด api ไว้แล้ว)
    เพื่อไม่ spawn ซ้ำซ้อน"""
    import socket
    try:
        with socket.create_connection(('127.0.0.1', 8000), timeout=0.3):
            return True
    except OSError:
        return False

def _face_state_fresh() -> bool:
    now = time.time()
    with _lock:
        return any((now - s.get('ts', 0)) < 5 for s in _cam_states.values())

def _face_running() -> bool:
    return (_proc_alive('main') or _face_state_fresh()
            or bool(_mem_active_cams()))


# ─── Spawn helpers (ใช้ทั้งจาก /system/start และ watchdog) ───────────────────
def _spawn_main_proc() -> subprocess.Popen:
    env = {**os.environ,
           'FACE_HEADLESS':     '1',
           'FACE_CAMERA_CHILD': '1'}
    p = subprocess.Popen(
        [sys.executable, str(_ROOT / 'main.py')],
        cwd=str(_ROOT),
        env=env,
    )
    _proc_last_spawn['main'] = time.time()
    return p


def _spawn_api_proc() -> subprocess.Popen:
    p = subprocess.Popen(
        [sys.executable, '-m', 'uvicorn', 'api:app',
         '--host', '0.0.0.0', '--port', '8000'],
        cwd=str(_ROOT),
    )
    _proc_last_spawn['api'] = time.time()
    return p


def _record_restart(key: str) -> bool:
    """เพิ่ม restart timestamp; return False ถ้าเกิน rate limit (ห้าม respawn)"""
    now = time.time()
    log = _proc_restart_log.setdefault(key, [])
    log.append(now)
    # ตัด timestamp ที่หลุด window
    log[:] = [t for t in log if (now - t) < _watchdog_window]
    if len(log) > _watchdog_max_restarts:
        _proc_disabled[key] = (
            f'crashed {len(log)} times in {_watchdog_window:.0f}s '
            f'— watchdog disabled for "{key}", check logs'
        )
        print(f'[WATCHDOG] DISABLED "{key}" — {_proc_disabled[key]}')
        return False
    return True


def _watchdog_loop():
    """ตรวจสอบ child process ทุก interval วิ ถ้าตายโดยไม่ตั้งใจ → respawn"""
    print(f'[WATCHDOG] เริ่มตรวจ child process (interval={_watchdog_interval}s, '
          f'limit={_watchdog_max_restarts}/{_watchdog_window:.0f}s)')
    while not _watchdog_stop.wait(_watchdog_interval):
        if not _user_intent_started:
            continue   # user ยังไม่กด Start หรือกด Stop ไปแล้ว → ไม่ทำอะไร

        # ── main.py ──────────────────────────────────────────────────────────
        if 'main' not in _proc_disabled:
            should_run = _start_fn is None  # spawn mode (standalone)
            if should_run and 'main' in _procs:
                p = _procs['main']
                age = time.time() - _proc_last_spawn.get('main', 0)
                if p.poll() is not None and age > _watchdog_grace_after_start:
                    code = p.returncode
                    print(f'[WATCHDOG] main.py died (exit={code}) — respawning')
                    if _record_restart('main'):
                        try:
                            _procs['main'] = _spawn_main_proc()
                            print('[WATCHDOG] main.py respawned ✓')
                        except Exception as e:
                            print(f'[WATCHDOG] respawn main FAILED: {e}')

        # ── api.py ───────────────────────────────────────────────────────────
        if 'api' not in _proc_disabled and 'api' in _procs:
            p = _procs['api']
            age = time.time() - _proc_last_spawn.get('api', 0)
            if p.poll() is not None and age > _watchdog_grace_after_start:
                # ก่อน respawn เช็คว่ามี service อื่นมายึด port 8000 หรือยัง
                if _api_alive():
                    continue   # มี process อื่นยึดอยู่ ไม่ต้อง spawn ซ้ำ
                code = p.returncode
                print(f'[WATCHDOG] api.py died (exit={code}) — respawning')
                if _record_restart('api'):
                    try:
                        _procs['api'] = _spawn_api_proc()
                        print('[WATCHDOG] api.py respawned ✓')
                    except Exception as e:
                        print(f'[WATCHDOG] respawn api FAILED: {e}')


def _watchdog_start():
    global _watchdog_thread
    if _watchdog_thread and _watchdog_thread.is_alive():
        return
    _watchdog_stop.clear()
    _watchdog_thread = threading.Thread(
        target=_watchdog_loop, daemon=True, name='watchdog')
    _watchdog_thread.start()


@app.get('/system/watchdog', dependencies=[Depends(get_current_user)])
async def system_watchdog_status():
    """ดูสถานะ watchdog + restart history"""
    now = time.time()
    return {
        'enabled': _watchdog_thread is not None and _watchdog_thread.is_alive(),
        'user_intent_started': _user_intent_started,
        'interval_s': _watchdog_interval,
        'limit': f'{_watchdog_max_restarts}/{_watchdog_window:.0f}s',
        'main': {
            'alive':   _proc_alive('main'),
            'restarts_in_window': len(_proc_restart_log.get('main', [])),
            'last_spawn_age_s':   round(now - _proc_last_spawn.get('main', 0), 1)
                                   if _proc_last_spawn.get('main') else None,
            'disabled': _proc_disabled.get('main'),
        },
        'api': {
            'alive':   _proc_alive('api'),
            'port_responding': _api_alive(),
            'restarts_in_window': len(_proc_restart_log.get('api', [])),
            'last_spawn_age_s':   round(now - _proc_last_spawn.get('api', 0), 1)
                                   if _proc_last_spawn.get('api') else None,
            'disabled': _proc_disabled.get('api'),
        },
    }


@app.get('/system/status')
async def system_status():
    """badge สีเขียวเฉพาะตอนผู้ใช้สั่ง Start แล้วเท่านั้น
    (ไม่ใช่แค่ port มี service ตอบ — เช่น npm run dev เปิด api ไว้แม้ไม่ได้กด Start)"""
    if not _user_intent_started:
        return {'face': False, 'api': False}
    return {'face': _face_running(),
            'api':  _proc_alive('api') or _api_alive()}


@app.post('/system/start', dependencies=[Depends(require_admin)])
async def system_start():
    """Start face recognition (subprocess FACE_HEADLESS) + api.py"""
    global _user_intent_started
    _user_intent_started = True
    # user สั่ง start ใหม่ → reset watchdog disable + restart counter
    _proc_disabled.clear()
    for k in _proc_restart_log:
        _proc_restart_log[k].clear()
    result = {}

    # ── face recognition ──────────────────────────────────────────────────────
    if _start_fn is not None:
        # python main.py รันอยู่แล้ว → restart workers
        try:
            await asyncio.to_thread(_start_fn)
            result['face'] = 'restarted'
        except Exception as e:
            result['face'] = f'error: {e}'
    elif _face_running():
        result['face'] = 'already_running'
    else:
        try:
            _procs['main'] = _spawn_main_proc()
            result['face'] = 'started'
        except Exception as e:
            result['face'] = f'error: {e}'

    # ── api.py subprocess ─────────────────────────────────────────────────────
    if _proc_alive('api') or _api_alive():
        # มี API ตอบที่ port 8000 อยู่แล้ว (อาจเป็น uvicorn จาก npm run dev) — ไม่ spawn ซ้ำ
        result['api'] = 'already_running'
    else:
        try:
            _procs['api'] = _spawn_api_proc()
            result['api'] = 'started'
        except Exception as e:
            result['api'] = f'error: {e}'

    _watchdog_start()
    return result


@app.post('/system/stop', dependencies=[Depends(require_admin)])
async def system_stop():
    """Stop face recognition + api.py (graceful shutdown → save PicSAVE)"""
    global _user_intent_started
    _user_intent_started = False
    result = {}

    # หยุด face recognition
    if _stop_fn:
        try:
            _stop_fn()
            result['face'] = 'stopped'
        except Exception as e:
            result['face'] = f'error: {e}'
    if _proc_alive('main'):
        _procs['main'].terminate()   # SIGTERM → main.py จะ save_snapshots() ก่อนตาย
        try:
            await asyncio.wait_for(
                asyncio.to_thread(_procs['main'].wait),
                timeout=8,
            )
        except asyncio.TimeoutError:
            _procs['main'].kill()    # kill ถ้ารอนานเกิน 8 วิ
        result['face'] = 'terminated'

    # หยุด api
    if _proc_alive('api'):
        _procs['api'].terminate()
        result['api'] = 'terminated'
    else:
        result['api'] = 'not_running'

    # ล้าง in-memory buffers ทั้งหมด
    with _lock:
        _cam_frames.clear()
        _cam_counts.clear()
        _cam_frame_ts.clear()
        _cam_states.clear()
    # เก็บกวาดไฟล์ legacy ที่อาจตกค้างจาก version เก่า (ครั้งเดียว)
    legacy = 0
    for pattern in ('live_frame_*.jpg', 'live_state_*.json',
                    'live_snap_*.jpg', 'live_snapfull_*.jpg'):
        for f in _ROOT.glob(pattern):
            try:
                f.unlink()
                legacy += 1
            except OSError:
                pass
    result['legacy_files_deleted'] = legacy

    return result


@app.post('/cameras/reload', dependencies=[Depends(require_admin)])
async def cameras_reload():
    """Hotload กล้องที่เพิ่งเพิ่มใหม่ใน cameras.json โดยไม่ต้อง restart ระบบ
    (เหมือนกดปุ่ม R ที่หลังบ้าน — spawn thread ให้เฉพาะกล้องใหม่)"""
    if _start_fn is None:
        return {'reloaded': 0, 'msg': 'ระบบไม่ได้รันในโหมด direct (ใช้ START ก่อน)'}
    try:
        import asyncio as _aio
        result = await _aio.to_thread(_start_fn)
        return {'reloaded': True, 'msg': 'reload สำเร็จ'}
    except Exception as e:
        return {'reloaded': False, 'msg': str(e)}


# ─── Legacy single-cam endpoints (→ cam1) ────────────────────────────────────

@app.get('/stream', dependencies=[Depends(get_current_user)])
async def stream():
    return StreamingResponse(
        _mjpeg_gen(_active_cam),
        media_type='multipart/x-mixed-replace; boundary=frame',
    )


@app.get('/snapshot', dependencies=[Depends(get_current_user)])
async def snapshot():
    with _lock:
        jpeg = _cam_frames.get(_active_cam)
    if jpeg is None:
        return Response(status_code=503)
    return Response(content=jpeg, media_type='image/jpeg')


@app.get('/status', dependencies=[Depends(get_current_user)])
async def status():
    with _lock:
        jpeg  = _cam_frames.get(_active_cam)
        count = _cam_counts.get(_active_cam, 0)
    return {"ready": jpeg is not None, "frames_pushed": count}


@app.get('/state', dependencies=[Depends(get_current_user)])
async def state_endpoint():
    with _lock:
        s = dict(_cam_states.get(_active_cam, {}))
    return s


@app.get('/snap/{name}', dependencies=[Depends(get_current_user)])
async def snap_person(name: str):
    with _lock:
        jpeg = _cam_snaps.get(_active_cam, {}).get(name)
    if jpeg is None:
        return Response(status_code=404)
    return Response(content=jpeg, media_type='image/jpeg')


@app.get('/window', dependencies=[Depends(get_current_user)])
async def window_get():
    return {"show_window": _cv_window}


@app.post('/window', dependencies=[Depends(require_admin)])
async def window_toggle():
    global _cv_window
    _cv_window = not _cv_window
    print(f'[STREAM] OpenCV window → {"ON" if _cv_window else "OFF"}')
    return {"show_window": _cv_window}


# ─── Start (daemon thread) ────────────────────────────────────────────────────
def start(port: int = 8001):
    def _run():
        uvicorn.run(app, host='0.0.0.0', port=port,
                    log_level='warning', access_log=False)
    t = threading.Thread(target=_run, daemon=True, name='stream-server')
    t.start()
    print(f'[STREAM] Per-cam stream  → http://localhost:{port}/stream/{{cam_id}}')
    print(f'[STREAM] Camera list     → http://localhost:{port}/cameras')
    print(f'[STREAM] Legacy stream   → http://localhost:{port}/stream  (→ active cam)')
    print(f'[STREAM] Camera admin    → http://localhost:{port}/admin')


# ─── Standalone mode ─────────────────────────────────────────────────────────
# รัน: python stream_server.py
# จากนั้นเปิด browser แล้วกด START เพื่อสั่งให้ spawn main.py + api.py
@app.on_event('startup')
async def _on_startup():
    _auth.bootstrap_default_users()
    _watchdog_start()


if __name__ == '__main__':
    import uvicorn as _uv
    port = int(os.environ.get('STREAM_PORT', 8001))
    print(f'[STREAM] Standalone mode  http://localhost:{port}')
    print(f'[STREAM] Admin page    →  http://localhost:{port}/admin')
    print('[STREAM] กดปุ่ม START ในหน้าเว็บเพื่อเปิดระบบ')
    _uv.run(app, host='0.0.0.0', port=port,
            log_level='warning', access_log=False)
