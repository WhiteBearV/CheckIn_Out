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
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query, Depends, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, date
from db import get_connection

load_dotenv()

app = FastAPI(title="Face Attendance API", version="2.0.0")

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


@app.delete("/attendance/today/all")
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
def list_cameras():
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
def add_camera(body: CameraCreateBody):
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
def update_camera_flip(cam_id: str, body: CameraFlipBody):
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
def delete_camera(cam_id: str):
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
def cameras_raw_stream(cam_id: str):
    """
    MJPEG stream โดยตรงจากกล้องที่ระบุ (ไม่มี face recognition overlay)
    ──────────────────────────────────────────────────────────────────────
    ใช้ทดสอบว่ากล้องทำงานได้ก่อน start main.py
    """
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
def camera_stream():
    """
    MJPEG stream จากกล้อง
    ─────────────────────────────────────────────────────────
    ใช้ใน Vue dashboard: <img :src="'/api/camera/stream'">

    ⚠ ควรเรียก /camera/snapshot probe ก่อน (CameraView.vue ทำให้อัตโนมัติ)
      ถ้า main.py ใช้กล้องเดียวกัน อาจ conflict (IP camera รองรับ multi-client)

    Quality: JPEG 65%  |  Max FPS: 15
    """
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
def person_photo(per_id: str):
    """
    คืนรูป snapshot IN ล่าสุดของพนักงานวันนี้
    ────────────────────────────────────────────────────────
    ค้นหาใน PicSAVE/YYYY/MM/DD/*_{per_id}_IN.jpg
    ถ้าไม่พบ → 404 (Vue จะแสดง avatar initials แทน)

    ใช้ใน PersonCard.vue:
      <img :src="`/api/person-photo/${person.per_id}`" @error="useFallback" />
    """
    import glob as _glob
    from fastapi.responses import FileResponse
    from datetime import date as _date

    today   = _date.today()
    folder  = _ROOT / "PicSAVE" / today.strftime("%Y") / today.strftime("%m") / today.strftime("%d")
    pattern = str(folder / f"*_{per_id}_IN.jpg")
    matches = sorted(_glob.glob(pattern))

    if not matches:
        raise HTTPException(status_code=404, detail="No photo found")

    # คืนรูปล่าสุด (sort ตาม filename = เวลา)
    return FileResponse(matches[-1], media_type="image/jpeg",
                        headers={"Cache-Control": "max-age=300"})


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

_LIVE_STATE_PATH = _ROOT / "live_state.json"   # legacy path (main.py รันตรง)

@app.get("/session/live")
def session_live():
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

    # ── อ่าน per-camera state files (live_state_cam1.json, live_state_cam2.json ฯลฯ) ──
    for path in sorted(_ROOT.glob("live_state_*.json")):
        try:
            data = _json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        ts = data.get("ts")
        if ts is not None and (_time.time() - ts <= 5):
            any_active = True
            if latest_ts is None or ts > latest_ts:
                latest_ts = ts
        for p in data.get("persons", []):
            pid = p.get("per_id")
            if pid and pid not in merged:
                merged[pid] = p

    # ── Fallback: legacy live_state.json ────────────────────────────────────
    if not merged:
        if not _LIVE_STATE_PATH.exists():
            return {"active": False, "ts": None, "stale": True, "persons": []}
        try:
            data = _json.loads(_LIVE_STATE_PATH.read_text(encoding="utf-8"))
        except Exception:
            return {"active": False, "ts": None, "stale": True, "persons": []}
        stale = (data.get("ts") is None) or (_time.time() - data["ts"] > 5)
        data["stale"] = stale
        return data

    stale = not any_active
    return {
        "active":  any_active,
        "ts":      latest_ts,
        "stale":   stale,
        "persons": list(merged.values()),
    }


# ╔═══════════════════════════════════════════════════════════════════════════╗
# ║  Face Recognition Stream & Process Control (Dashboard)                    ║
# ╚═══════════════════════════════════════════════════════════════════════════╝

import sys as _sys
import subprocess as _subprocess

_LIVE_FRAME_PATH  = _ROOT / "live_frame.jpg"
_face_process: "_subprocess.Popen | None" = None


@app.post("/camera/face/start")
def face_process_start():
    """
    Start main.py เป็น background process
    main.py จะเขียน live_frame.jpg ทุก ~67ms สำหรับ /camera/face-stream
    """
    global _face_process
    if _face_process is not None and _face_process.poll() is None:
        return {"ok": False, "reason": "already running", "pid": _face_process.pid}
    try:
        env = os.environ.copy()
        env["FACE_HEADLESS"]       = "1"   # ปิด GUI window — stream ผ่าน live_frame.jpg แทน
        env["FACE_ALWAYS_ACTIVE"]  = "1"   # รัน 24/7 ข้าม Active Windows — หยุดเองเมื่อกด Stop
        _face_process = _subprocess.Popen(
            [_sys.executable, str(_ROOT / "main.py")],
            cwd=str(_ROOT),
            env=env,
        )
        return {"ok": True, "pid": _face_process.pid}
    except Exception as e:
        return {"ok": False, "reason": str(e)}


@app.post("/camera/face/stop")
def face_process_stop():
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
def camera_face_stream():
    """
    MJPEG stream จาก main.py (อ่านจาก live_frame.jpg)
    ─────────────────────────────────────────────────────────────────────
    main.py เขียน live_frame.jpg ทุก ~67ms (15fps) พร้อม overlay ทั้งหมด:
      - Oval guide + dim effect นอกวงรี
      - Face bounding boxes + liveness labels
      - Challenge overlay
      - HUD (FPS ถ้าเปิด)
    Dashboard แสดงผลผ่าน <img :src="'/api/camera/face-stream'">
    """
    def generate():
        import time
        while True:
            if _LIVE_FRAME_PATH.exists():
                try:
                    frame_bytes = _LIVE_FRAME_PATH.read_bytes()
                    yield (
                        b'--frame\r\nContent-Type: image/jpeg\r\n\r\n'
                        + frame_bytes + b'\r\n'
                    )
                except Exception:
                    pass
            time.sleep(0.067)

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
    return _ROOT / f"live_frame_{cam_id}.jpg"


def _live_state_path_for(cam_id: str) -> pathlib.Path:
    return _ROOT / f"live_state_{cam_id}.json"


@app.get("/cameras/{cam_id}/face-stream")
def cameras_face_stream(cam_id: str):
    """
    MJPEG stream จาก main.py พร้อม face recognition overlay สำหรับกล้องที่ระบุ
    อ่านจาก live_frame_{cam_id}.jpg ที่ main.py เขียนทุก ~67ms
    """
    if cam_id not in _CAMERAS:
        raise HTTPException(status_code=404, detail=f"Camera '{cam_id}' not found")

    live_frame = _live_frame_path_for(cam_id)

    def generate():
        import time
        while True:
            if live_frame.exists():
                try:
                    frame_bytes = live_frame.read_bytes()
                    yield (
                        b'--frame\r\nContent-Type: image/jpeg\r\n\r\n'
                        + frame_bytes
                        + b'\r\n'
                    )
                except Exception:
                    pass
            time.sleep(0.067)

    return StreamingResponse(
        generate(),
        media_type='multipart/x-mixed-replace; boundary=frame',
        headers={"Cache-Control": "no-cache, no-store"},
    )


@app.get("/cameras/{cam_id}/face/status")
def cameras_face_status(cam_id: str):
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

    return {
        "cam_id":        cam_id,
        "cam_name":      _CAMERAS[cam_id]["name"],
        "running":       running,
        "pid":           proc.pid if running else None,
        "has_frame":     has_frame,
        "frame_age_sec": frame_age,
    }


@app.post("/cameras/{cam_id}/face/start")
def cameras_face_start(cam_id: str):
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
def cameras_face_stop(cam_id: str):
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
