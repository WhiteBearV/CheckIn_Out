"""
main.py — Main loop (InsightFace / ArcFace)
=============================================
เปลี่ยนจาก face_recognition (dlib 128d) → InsightFace (ArcFace 512d)

ติดตั้ง:
  pip install insightface onnxruntime-gpu   # (หรือ onnxruntime สำหรับ CPU)

ครั้งแรกที่รัน จะ download model buffalo_l อัตโนมัติ (~300MB)
"""

import os
import sys
import glob


def _ensure_nvidia_libs():
    """
    ตั้ง LD_LIBRARY_PATH ให้ชี้ไปที่ CUDA/cuDNN libs ใน venv ก่อน
    เพื่อให้ onnxruntime-gpu ใช้ GPU ได้โดยไม่ crash
    re-exec ตัวเองถ้าต้องการ
    """
    if os.environ.get("_NVIDIA_LIBS_SET"):
        return
    venv_prefix = os.path.dirname(os.path.dirname(sys.executable))
    nvidia_paths = sorted(glob.glob(
        f"{venv_prefix}/lib/python*/site-packages/nvidia/*/lib"
    ))
    if not nvidia_paths:
        return
    existing = os.environ.get("LD_LIBRARY_PATH", "")
    new_path = ":".join(nvidia_paths) + (":" + existing if existing else "")
    os.environ["LD_LIBRARY_PATH"] = new_path
    os.environ["_NVIDIA_LIBS_SET"] = "1"
    os.environ["PYTHONUNBUFFERED"] = "1"
    os.execv(sys.executable, [sys.executable, "-u"] + sys.argv)


# _ensure_nvidia_libs() เรียกเฉพาะตอนรันตรง (__main__)
# ถ้า import โดย stream_server ให้ข้ามเพื่อป้องกัน os.execv() crash

import cv2
import pickle
import time
import numpy as np
import mediapipe as mp
from datetime import datetime, timedelta
from numpy.linalg import norm

import threading as _t
import config as cfg
from camera import ThreadedCamera
from session_manager import SessionManager
from api_client import mask_pid
import ui_renderer as ui
import stream_server
from pathlib import Path as _pl_mod

# ─── Headless mode — POST ทุกอย่างเข้า stream_server in-memory cache ────────
# เมื่อ FACE_HEADLESS=1 (spawn จาก stream_server) main.py กับ stream_server
# คนละ process — สื่อสารผ่าน HTTP POST localhost (ไม่แตะ disk)

# HTTP client (singleton) — pool ใช้ซ้ำเพื่อลด latency
_STREAM_BASE  = f"http://127.0.0.1:{int(os.environ.get('STREAM_PORT', 8001))}"
_PUSH_TOKEN   = os.environ.get("INTERNAL_PUSH_TOKEN", "")
_PUSH_HEADERS = {"X-Push-Token": _PUSH_TOKEN} if _PUSH_TOKEN else {}
_http_session = None

def _get_http_session():
    global _http_session
    if _http_session is None:
        import requests
        from requests.adapters import HTTPAdapter
        _http_session = requests.Session()
        _http_session.mount('http://', HTTPAdapter(pool_connections=4, pool_maxsize=8))
    return _http_session

def _post_live_frame(cam_id: str, frame_bgr):
    """POST JPEG-encoded frame ไปเก็บใน stream_server._cam_frames (in-memory)"""
    import cv2 as _cv2
    try:
        ok, buf = _cv2.imencode('.jpg', frame_bgr, [_cv2.IMWRITE_JPEG_QUALITY, 70])
        if not ok:
            return
        _get_http_session().post(
            f"{_STREAM_BASE}/push/frame/{cam_id}",
            data=buf.tobytes(),
            headers={'Content-Type': 'image/jpeg', **_PUSH_HEADERS},
            timeout=1.0,
        )
    except Exception:
        pass

def _post_live_state(cam_id: str, state: dict):
    """POST JSON state ไปเก็บใน stream_server._cam_states (in-memory)"""
    import json as _j
    try:
        _get_http_session().post(
            f"{_STREAM_BASE}/push/state/{cam_id}",
            data=_j.dumps(state, ensure_ascii=False).encode('utf-8'),
            headers={'Content-Type': 'application/json', **_PUSH_HEADERS},
            timeout=1.0,
        )
    except Exception:
        pass

def _post_live_snap(cam_id: str, name: str, crop):
    """POST face crop ไปเก็บใน stream_server._cam_snaps (in-memory)
    ใช้ urllib quote เพื่อให้ name (อาจมี '*' จาก masked PID) เดินผ่าน HTTP path ได้"""
    from urllib.parse import quote
    import cv2 as _cv2
    try:
        ok, buf = _cv2.imencode('.jpg', crop, [_cv2.IMWRITE_JPEG_QUALITY, 80])
        if not ok:
            return
        _get_http_session().post(
            f"{_STREAM_BASE}/push/snap/{cam_id}/{quote(name, safe='')}",
            data=buf.tobytes(),
            headers={'Content-Type': 'image/jpeg', **_PUSH_HEADERS},
            timeout=1.0,
        )
    except Exception:
        pass

def _post_live_snapfull(cam_id: str, name: str, frame):
    """POST full frame ไปเก็บใน stream_server._cam_snaps_full (in-memory)"""
    from urllib.parse import quote
    import cv2 as _cv2
    try:
        ok, buf = _cv2.imencode('.jpg', frame, [_cv2.IMWRITE_JPEG_QUALITY, 75])
        if not ok:
            return
        _get_http_session().post(
            f"{_STREAM_BASE}/push/snapfull/{cam_id}/{quote(name, safe='')}",
            data=buf.tobytes(),
            headers={'Content-Type': 'image/jpeg', **_PUSH_HEADERS},
            timeout=1.0,
        )
    except Exception:
        pass


# ─── Multi-cam display buffer (worker thread → main thread) ──────────────────
# Single slot — เฉพาะกล้องที่ถูกเลือก (_sel_cam) เท่านั้นที่เขียน
# ไม่มี per-cam dict → ไม่มีโอกาส bleeding ข้ามกล้อง
_disp_lock       = _t.Lock()
_disp_slot       = {"frame": None}   # frame ล่าสุดจากกล้องที่ active
_cam_has_pushed  = set()             # cam_id ที่เคย push แล้ว (สำหรับ status dot)
_sel_cam         = {"id": ""}        # กล้องที่เลือกอยู่ — worker อ่าน, main thread เขียน
_stop_event      = _t.Event()        # set() เพื่อหยุดทุก worker

# ─── ดึงความละเอียดหน้าจอจริงจาก xrandr ───
import subprocess as _sp, re as _re

def _get_screen_size() -> tuple[int, int]:
    try:
        out = _sp.check_output(["xrandr", "--current"], text=True)
        m = _re.search(r"(\d+)x(\d+)\+0\+0", out)   # primary display อยู่ที่ +0+0
        if m:
            return int(m.group(1)), int(m.group(2))
    except Exception:
        pass
    return cfg.SCREEN_FALLBACK_W, cfg.SCREEN_FALLBACK_H

SCREEN_W, SCREEN_H = _get_screen_size()
del _sp, _re


# ─── Active Window Helpers ───────────────────
def _in_active_window(t, windows) -> bool:
    """ตรวจว่าเวลา t อยู่ในช่วง Active Window ใดช่วงหนึ่งหรือเปล่า
    รองรับช่วงที่ข้ามเที่ยงคืน เช่น (23:00, 01:00)"""
    for start, end in windows:
        if start <= end:                     # ช่วงปกติ ไม่ข้ามเที่ยงคืน
            if start <= t < end:
                return True
        else:                                # ข้ามเที่ยงคืน
            if t >= start or t < end:
                return True
    return False


def _next_window_start(now_dt: datetime, windows) -> datetime:
    """คืน datetime ของจุดเริ่มต้น window ถัดไปจาก now_dt"""
    candidates = []
    for win_start, _ in windows:
        candidate = datetime.combine(now_dt.date(), win_start)
        if candidate <= now_dt:
            candidate += timedelta(days=1)
        candidates.append(candidate)
    return min(candidates)


# ─── InsightFace landmark → dict (สำหรับ DepthAnalyzer) ──────
def landmarks_68_to_dict(pts) -> dict:
    """
    แปลง 68-point landmarks (array shape 68x2 หรือ 68x3)
    เป็น dict แบบที่ DepthAnalyzer ใช้ (เหมือน face_recognition)

    dlib 68-point mapping:
      0-16   chin (17 points)
      17-21  left_eyebrow (5)
      22-26  right_eyebrow (5)
      27-30  nose_bridge (4)
      31-35  nose_tip (5)
      36-41  left_eye (6)
      42-47  right_eye (6)
    """
    p = [(float(pts[i][0]), float(pts[i][1])) for i in range(68)]
    return {
        "chin":           p[0:17],
        "left_eyebrow":   p[17:22],
        "right_eyebrow":  p[22:27],
        "nose_bridge":    p[27:31],
        "nose_tip":       p[31:36],
        "left_eye":       p[36:42],
        "right_eye":      p[42:48],
    }


# ─── Face Matching (cosine similarity) ──────
def identify_face(embedding, known_norms: np.ndarray, known_names) -> str:
    """เทียบ 512d embedding กับฐานข้อมูล ด้วย cosine similarity (vectorized)
    known_norms: pre-normalized matrix (N, 512) สร้างครั้งเดียวตอน startup"""
    if known_norms is None or len(known_norms) == 0:
        return "Unknown"
    emb_norm = embedding / (norm(embedding) + 1e-10)
    sims = known_norms @ emb_norm          # (N,512) @ (512,) → (N,)
    best_idx = int(np.argmax(sims))
    if sims[best_idx] >= cfg.FACE_TOLERANCE:
        return known_names[best_idx]
    return "Unknown"


def _compute_guide_state(face_with_names, liveness_map,
                         oval_cx, oval_cy, oval_ew, oval_eh, now_ts):
    """คำนวณ guide overlay state สำหรับ web canvas"""
    if not cfg.GUIDE_OVERLAY or cfg.TEST_MODE:
        return {"enabled": False}

    C = cfg.Color

    # หาหน้าในวงรี
    face_in_oval = False
    oval_name    = None
    for face_box, name in face_with_names:
        top, right, bottom, left = face_box
        fcx = (left + right) / 2.0
        fcy = (top + bottom) / 2.0
        if (((fcx - oval_cx) / oval_ew) ** 2 +
                ((fcy - oval_cy) / oval_eh) ** 2) <= cfg.GUIDE_IN_OVAL_TOL:
            face_in_oval, oval_name = True, name
            break

    oval_color = list(C.OVAL_DEFAULT)
    main_text  = "Place your face in the oval"
    sub_text   = ""

    if face_in_oval and oval_name and oval_name in (liveness_map or {}):
        lv = liveness_map[oval_name]

        if lv.confirmed:
            oval_color = list(C.CHECKED_IN)
            main_text  = "Verified!"
        elif lv.failed:
            oval_color = list(C.LIVENESS_FAIL)
            retry_at   = lv.start_ts + cfg.LIVENESS_TIMEOUT + cfg.LIVENESS_RETRY_AFTER
            main_text  = "Verification failed"
            sub_text   = f"{lv.fail_reason or ''}  |  Retry {max(0, retry_at - now_ts):.0f}s"
        elif lv.challenge_phase == "active":
            cn, dn    = lv.challenge_number, len(lv.challenge_done)
            rem       = max(0, cfg.CHALLENGE_TIMEOUT - (now_ts - lv.challenge_start_ts))
            oval_color = list(C.CHALLENGE)
            main_text  = f"Show {cn} finger(s)"
            sub_text   = f"Step {dn+1}/{cfg.CHALLENGE_COUNT}  |  {rem:.1f}s left"
        else:
            oval_color = list(C.LIVENESS)
            dp = lv.depth_pass_count
            m  = "OK" if lv.motion_ok  else "--"
            bk = f"{lv.blink_count}/{cfg.BLINK_MIN}" if not lv.blink_ok else "OK"
            t  = "OK" if lv.texture_ok else "--"
            s  = "OK" if lv.screen_ok  else "FAIL"
            f  = "OK" if lv.fas_ok     else (f"{lv.fas_score:.1f}" if lv.fas_score >= 0 else "--")

            if dp < cfg.DEPTH_FRAMES_REQUIRED:
                main_text = f"Hold still...  {dp}/{cfg.DEPTH_FRAMES_REQUIRED}"
            elif cfg.BLINK_ENABLED and not lv.blink_ok:
                main_text = f"Please blink  {lv.blink_count}/{cfg.BLINK_MIN}"
            elif not lv.motion_ok:
                main_text = "Move your head slightly"
            elif not lv.texture_ok:
                main_text = "Hold still (texture)..."
            elif not lv.fas_ok:
                main_text = "Hold still (AI check)..."
            else:
                main_text = "Hold still..."

            bk_part  = f"  Blink {bk}" if cfg.BLINK_ENABLED else ""
            scr_part = f"  Scr {s}"    if cfg.SCREEN_DETECT_ENABLED else ""
            sub_text = f"Mot {m}{bk_part}  Tex {t}{scr_part}  FAS {f}"

    elif face_in_oval:
        oval_color = list(C.LIVENESS)
        main_text  = "Hold still..."

    return {
        "enabled":    True,
        "oval":       {"cx": oval_cx, "cy": oval_cy, "ew": oval_ew, "eh": oval_eh},
        "oval_color": oval_color,
        "dim_factor": cfg.GUIDE_DIM_FACTOR,
        "main_text":  main_text,
        "sub_text":   sub_text,
    }


# ─── Camera Management Helpers ────────────────────────────────────────────────
_ENV_PATH = _pl_mod(__file__).parent / ".env"


# ─── .env helpers ─────────────────────────────────────────────────────────────

def _env_set(key: str, value: str):
    """เพิ่ม / อัปเดต KEY=value ใน .env (สร้างไฟล์ถ้ายังไม่มี)"""
    lines: list[str] = []
    if _ENV_PATH.exists():
        with open(_ENV_PATH, encoding="utf-8") as _f:
            lines = _f.readlines()
    new_lines, found = [], False
    for line in lines:
        if line.strip().startswith(f"{key}="):
            new_lines.append(f"{key}={value}\n")
            found = True
        else:
            new_lines.append(line)
    if not found:
        new_lines.append(f"{key}={value}\n")
    with open(_ENV_PATH, "w", encoding="utf-8") as _f:
        _f.writelines(new_lines)


def _env_del(key: str):
    """ลบ KEY=... ออกจาก .env"""
    if not _ENV_PATH.exists():
        return
    with open(_ENV_PATH, encoding="utf-8") as _f:
        lines = _f.readlines()
    with open(_ENV_PATH, "w", encoding="utf-8") as _f:
        _f.writelines(l for l in lines if not l.strip().startswith(f"{key}="))


def _cam_env_key(cam_id: str) -> str:
    """cam4 → CAM4_URL"""
    return cam_id.upper().replace("-", "_") + "_URL"


def _resolve_url(url) -> str:
    """แปลง '$VAR_NAME' → os.environ.get('VAR_NAME') | ค่าตรง"""
    if isinstance(url, str) and url.startswith("$"):
        return os.environ.get(url[1:], "")
    return url or ""




def run_camera(cam_cfg: dict, cam_stop_event=None):
    """Main loop สำหรับกล้อง 1 ตัว — รัน 1 thread ต่อ cam_cfg"""
    cam_id      = cam_cfg["id"]
    camera_name = cam_cfg["name"]
    cam_flip    = cam_cfg.get("flip", cfg.CAMERA_FLIP)

    # FACE_HEADLESS=1: spawn จาก stream_server → เขียน frame/state ลงไฟล์แทน push buffer
    _HEADLESS      = os.environ.get('FACE_HEADLESS', '').lower() in ('1', 'true', 'yes')
    _ALWAYS_ACTIVE = os.environ.get('FACE_ALWAYS_ACTIVE', '').lower() in ('1', 'true', 'yes')
    if _HEADLESS:
        print(f'[{cam_id}] Headless mode — POST → {_STREAM_BASE}/push/* (in-memory)', flush=True)

    # ─── โหลด face encodings (ArcFace 512d) ───
    if not os.path.exists(cfg.ENCODINGS_FILE):
        raise FileNotFoundError(
            f"ไม่พบ {cfg.ENCODINGS_FILE}\n"
            f"รัน encode_faces_arcface.py ก่อน"
        )
    with open(cfg.ENCODINGS_FILE, "rb") as f:
        data = pickle.load(f)
    known_names = data["names"]
    # Pre-normalize embeddings เป็น matrix ครั้งเดียว → ใช้ vectorized dot product
    _raw = np.array(data["encodings"], dtype=np.float32)
    known_norms = _raw / (np.linalg.norm(_raw, axis=1, keepdims=True) + 1e-10)
    print(f"[DB] โหลด {len(known_names)} คน จาก {cfg.ENCODINGS_FILE}")

    # ─── InsightFace ───
    from insightface.app import FaceAnalysis
    import onnxruntime as ort

    available = ort.get_available_providers()
    use_providers = [p for p in available if p != "TensorrtExecutionProvider"]
    print(f"[ORT] Using: {use_providers}")

    # ใช้เฉพาะ models ที่จำเป็น — ข้าม genderage + 2d106det (ไม่ได้ใช้ ลด inference 2/5)
    _needed = ["detection", "landmark_3d_68", "recognition"]
    try:
        app = FaceAnalysis(
            name="buffalo_l",
            providers=use_providers,
            allowed_modules=_needed,
        )
    except Exception as e:
        print(f"[WARN] GPU ใช้ไม่ได้: {e}")
        print("[WARN] Fallback → CPU")
        app = FaceAnalysis(
            name="buffalo_l",
            providers=["CPUExecutionProvider"],
            allowed_modules=_needed,
        )
    app.prepare(ctx_id=0, det_size=cfg.DET_SIZE)
    print(f"[ARCFACE] InsightFace ready  det_size={cfg.DET_SIZE}")

    # ─── เปิดกล้อง ───
    cam_src = cam_cfg.get("url") or cam_cfg.get("index", 0)
    if isinstance(cam_src, str) and cam_src:
        print(f"[CAM] {cam_id} IP camera: {cam_src}")
    else:
        print(f"[CAM] {cam_id} USB index: {cam_src}")
    try:
        cam = ThreadedCamera(cam_src)
    except Exception as e:
        print(f"[CAM ERROR] {cam_id} เปิดกล้องไม่ได้: {e}")
        print(f"[CAM ERROR] {cam_id} worker หยุดทำงาน — กล้องอื่นยังรันต่อ")
        return

    # ─── MediaPipe Hands ───
    hands = mp.solutions.hands.Hands(
        static_image_mode=False,
        max_num_hands=1,
        min_detection_confidence=cfg.HAND_DETECTION_CONF,
        min_tracking_confidence=cfg.HAND_TRACKING_CONF,
    )

    # ─── Session Manager ───
    session = SessionManager()

    # ─── แสดงข้อมูลเริ่มต้น ───
    print(f"=== [{cam_id}] ระบบตรวจใบหน้า (ArcFace + Multi-Layer Anti-Spoof) ===")
    print(f"[CAM]       {cam_id}  {cam.width}x{cam.height}")
    print(f"[DEPTH]     {cfg.DEPTH_FRAMES_REQUIRED}/{cfg.DEPTH_FRAMES_WINDOW}")
    print(f"[TEXTURE]   {'ON' if cfg.TEXTURE_ENABLED else 'OFF'}")
    print(f"[SCREEN]    {'ON' if cfg.SCREEN_DETECT_ENABLED else 'OFF'}")
    if cfg.CHALLENGE_ENABLED:
        print(f"[CHALLENGE] x{cfg.CHALLENGE_COUNT}  timeout={cfg.CHALLENGE_TIMEOUT}s")
    print(f"[FAS]       {'ON' if cfg.FAS_ENABLED else 'OFF'}")

    # ─── หน้าต่าง ───
    win_name      = f"Face Attendance - {camera_name}"
    is_fullscreen = cfg.FULLSCREEN
    _window_ready = False   # True หลัง imshow ครั้งแรก

    # สร้าง window เฉพาะตอนที่ CV_WINDOW เปิด (ป้องกัน X11 crash ใน background thread)
    if stream_server.get_cv_window():
        cv2.namedWindow(win_name, cv2.WINDOW_NORMAL)

    def _apply_fullscreen():
        cv2.setWindowProperty(win_name, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)
        cv2.moveWindow(win_name, 0, 0)
        cv2.resizeWindow(win_name, SCREEN_W, SCREEN_H)

    def _apply_windowed():
        cv2.setWindowProperty(win_name, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_NORMAL)
        cv2.resizeWindow(win_name, cfg.WINDOWED_W, cfg.WINDOWED_H)
        cv2.moveWindow(win_name, 100, 100)

    def _toggle_fullscreen():
        nonlocal is_fullscreen
        is_fullscreen = not is_fullscreen
        if is_fullscreen:
            _apply_fullscreen()
        else:
            _apply_windowed()

    def _imshow(display):
        """imshow + apply fullscreen หลัง frame แรก (Linux ต้อง map window ก่อน)
        Multi-cam: push frame ไป _disp_frames ให้ main thread แสดงแทน
        """
        nonlocal _window_ready
        if not stream_server.get_cv_window():
            with _disp_lock:
                _cam_has_pushed.add(cam_id)
                if cam_id == _sel_cam["id"]:      # เขียนเฉพาะกล้องที่ถูกเลือก
                    _disp_slot["frame"] = display.copy()
            return
        if is_fullscreen and (display.shape[1] != SCREEN_W or display.shape[0] != SCREEN_H):
            display = cv2.resize(display, (SCREEN_W, SCREEN_H), interpolation=cv2.INTER_LINEAR)
        cv2.imshow(win_name, display)
        if not _window_ready:
            _window_ready = True
            cv2.waitKey(1)   # ให้ window manager map หน้าต่างก่อน
            if is_fullscreen:
                _apply_fullscreen()

    # ─── ตัวแปร loop ───
    start_ts      = datetime.now().timestamp()
    checkout_done = False
    frame_count   = 0
    _was_active: bool | None = None   # None = iteration แรก (ยังไม่รู้ว่า active หรือเปล่า)
    last_faces    = []     # cache ผลลัพธ์ insightface
    fps_counter  = 0
    fps_timer    = start_ts
    display_fps  = 0.0
    last_face_ts = start_ts

    # ─── Screen Debug EMA (TEST_MODE) ───
    # smoothing กันกระพริบ — ค่าตัวเลขใช้ EMA, ค่า bool ใช้ latest
    _EMA_A = cfg.SCREEN_DEBUG_EMA_ALPHA
    _screen_ema: dict = {}   # EMA ของ float values
    _screen_debug_display: dict = {}   # ส่งเข้า build_panel

    # ─── Panel cache ของกล้องนี้โดยเฉพาะ (ป้องกัน race กับกล้องอื่น) ───
    _local_panel_cache: dict = {"panel": None, "key": None, "tick": 0}

    # ─── คำนวณ oval ───
    def _compute_oval(h, w):
        cx = w // 2
        cy = int(h * cfg.GUIDE_OVAL_CY)
        ew = int(h * cfg.GUIDE_OVAL_EW)
        eh = int(h * cfg.GUIDE_OVAL_EH)
        return cx, cy, ew, eh

    # ═══════════════════════════════════════
    # MAIN LOOP
    # ═══════════════════════════════════════
    while True:
        ret, frame = cam.read()
        if not ret or frame is None:
            continue
        if cam_flip:
            frame = cv2.flip(frame, 1)

        now    = datetime.now()
        now_ts = now.timestamp()
        frame_count += 1

        # ─── FPS ───
        fps_counter += 1
        if now_ts - fps_timer >= 1.0:
            display_fps = fps_counter / (now_ts - fps_timer)
            fps_counter, fps_timer = 0, now_ts

        # ─── Checkout (TEST_MODE / CHECKOUT_TIME) ───
        should_checkout = (
            (now_ts - start_ts >= cfg.TEST_DURATION_SECONDS) if cfg.TEST_MODE
            else (now.time() >= cfg.CHECKOUT_TIME)
        )
        if should_checkout and not checkout_done:
            checkout_done = True
            session.do_checkout(camera_name, now)
        if cfg.TEST_MODE and checkout_done:
            break

        # ─── Active Window Check ───
        _active = True if _ALWAYS_ACTIVE else _in_active_window(now.time(), cfg.ACTIVE_WINDOWS)

        if _active and _was_active is False:
            # idle → active: เริ่มช่วงใหม่ — reset session และ checkout flag
            session       = SessionManager()
            last_faces    = []
            last_face_ts  = now_ts
            checkout_done = False
            print(f"[SCHEDULER] Active window เริ่ม {now.strftime('%H:%M:%S')}")

        if not _active and _was_active is True:
            # active → idle: checkout คนที่ยังไม่ได้ออก แล้วพัก
            if not checkout_done:
                checkout_done = True
                session.do_checkout(camera_name, now)
            session.save_snapshots()
            print(f"[SCHEDULER] Idle mode เริ่ม {now.strftime('%H:%M:%S')}")

        _was_active = _active

        if not _active:
            # ── Idle mode: แสดงหน้าจอรอ ลด CPU/GPU ──
            next_dt = _next_window_start(now, cfg.ACTIVE_WINDOWS)

            _idle_state = {
                "ts": now_ts, "fps": display_fps,
                "frame_size": list(frame.shape[:2]),
                "idle": True,
                "next_window": next_dt.strftime("%H:%M") if next_dt else None,
                "faces": [], "guide": {"enabled": False}, "persons": {},
                "hud": {"show_fps": cfg.SHOW_FPS, "test_mode": False,
                        "checkout_done": False, "remaining": 0},
            }
            if _HEADLESS:
                _post_live_state(cam_id, _idle_state)
            else:
                stream_server.push_state(cam_id, _idle_state)

            ui.draw_idle_screen(frame, now, next_dt)
            idle_panel = np.zeros((frame.shape[0], cfg.PANEL_WIDTH, 3), dtype=np.uint8)
            idle_display = np.hstack([frame, idle_panel])
            if _HEADLESS:
                _post_live_frame(cam_id, idle_display)
            else:
                stream_server.push_frame(cam_id, idle_display)
            _imshow(idle_display)
            if stream_server.get_cv_window():
                key = cv2.waitKey(500) & 0xFF
                if key == ord("q") or key == 27:
                    break
                elif key == ord("f"):
                    _toggle_fullscreen()
            else:
                if _stop_event.wait(0.5):
                    break
            continue                         # ข้ามการประมวลผลใบหน้าทั้งหมด

        # ─── Face detection (InsightFace) ───
        do_detect = (frame_count % cfg.DETECT_EVERY_N_FRAMES == 0)
        if do_detect:
            last_faces = app.get(frame)

        # ─── Hand detection ───
        hand_results = None
        has_challenge = any(
            lv.challenge_phase == "active"
            for lv in session.liveness.values()
            if not lv.confirmed and not lv.failed
        )
        if has_challenge:   # ทุกเฟรม (ไม่ขึ้นกับ do_detect) → จับนิ้วแม่นขึ้น
            hand_results = hands.process(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))

        # ─── Reset expired ───
        session.cleanup_expired(now_ts)

        # ─── No-face reset ───
        if last_faces:
            last_face_ts = now_ts
        elif now_ts - last_face_ts >= cfg.NO_FACE_RESET_SEC:
            for name in list(session.liveness.keys()):
                person = session.persons.get(name)
                if not person or not person.checked_in:
                    del session.liveness[name]
            last_faces = []
            last_face_ts = now_ts

        # Raw frame สำหรับ web stream (ก่อนวาด overlay)
        raw_frame = frame.copy()

        # copy frame เฉพาะเมื่อมีคนที่ยังไม่ได้ snapshot (ประหยัด copy ส่วนใหญ่)
        _need_snapshot = any(
            not p.checked_in
            for p in session.persons.values()
        ) or not session.persons
        orig_frame = frame.copy() if _need_snapshot else frame

        # ─── Oval params ───
        fh, fw = frame.shape[:2]
        oval_cx, oval_cy, oval_ew, oval_eh = _compute_oval(fh, fw)

        # ─── Process faces ───
        _face_with_names = []

        for face in last_faces:
            # ── bbox ──
            x1, y1, x2, y2 = face.bbox.astype(int)
            left, top, right, bottom = x1, y1, x2, y2
            face_w = right - left
            face_box = (top, right, bottom, left)

            # ── ตรวจว่าอยู่ในวงรี ──
            fcx = (left + right) / 2.0
            fcy = (top + bottom) / 2.0
            in_oval = (
                ((fcx - oval_cx) / oval_ew) ** 2 +
                ((fcy - oval_cy) / oval_eh) ** 2
            ) <= cfg.GUIDE_IN_OVAL_TOL

            if not in_oval:
                ui.draw_face_box(frame, left, top, right, bottom,
                                 cfg.Color.UNKNOWN, "Move into oval")
                continue

            # ── Identify (ArcFace 512d) ──
            embedding = face.embedding
            name = identify_face(embedding, known_norms, known_names)

            # ── Face crop ──
            pad = cfg.FACE_CROP_PAD
            crop = orig_frame[max(0, top-pad):min(fh, bottom+pad),
                              max(0, left-pad):min(fw, right+pad)]

            if name == "Unknown":
                ui.draw_face_box(frame, left, top, right, bottom,
                                 cfg.Color.UNKNOWN, "Unknown")
                continue

            _face_with_names.append((face_box, name))

            # ── Push face thumbnail + full frame สำหรับ web frontend ──
            # ใช้ masked pid (4 ตัวท้าย) เป็นชื่อไฟล์ / key — ไม่รั่ว per_id 13 หลัก
            mkey = mask_pid(name)
            if _HEADLESS:
                if crop.size > 0:
                    _post_live_snap(cam_id, mkey, crop)
                _post_live_snapfull(cam_id, mkey, raw_frame)
            else:
                if crop.size > 0:
                    stream_server.push_snapshot(cam_id, mkey, crop)
                stream_server.push_snapshot_full(cam_id, mkey, raw_frame)

            # ── Landmarks (68-point → dict) ──
            lm_dict = None
            if face.landmark_3d_68 is not None:
                lm_dict = landmarks_68_to_dict(face.landmark_3d_68)
            elif face.landmark_2d_106 is not None:
                # fallback: ใช้ 5-point จาก kps (ไม่ครบ แต่ดีกว่าไม่มี)
                lm_dict = None  # DepthAnalyzer จะข้ามถ้าไม่มี

            # ── Liveness ──
            person, liveness = session.get_or_create(name, now, crop)

            if lm_dict:
                session.engine.update(
                    liveness, lm_dict, crop, face_box, face_w,
                    frame, hand_results, now_ts, do_detect,
                )
            else:
                # ไม่มี 68-point landmarks → ข้าม depth/motion แต่ยัง check texture/screen/FAS
                session.engine.update(
                    liveness, {}, crop, face_box, face_w,
                    frame, hand_results, now_ts, do_detect,
                )

            if liveness.confirmed and not person.checked_in:
                person.snapshot = orig_frame.copy()
            elif liveness.confirmed and person.checked_in and not person.checked_out:
                # ผ่าน liveness ซ้ำหลัง absence → อัปเดต last_seen (ไม่สร้าง record ใหม่)
                is_reverify = person.absence_reset  # True เฉพาะ frame แรกที่ผ่านหลัง absence
                session.confirm_presence(name, now)
                if is_reverify:
                    person.snapshot_out = orig_frame.copy()

            session.try_checkin(name, camera_name)

            # ── Screen Debug (TEST_MODE) — เก็บค่าล่าสุด อัปเดต EMA ทีหลัง ──
            if cfg.TEST_MODE and do_detect:
                _raw_dbg = session.engine.screen.detect_debug(frame, face_box)
                if _raw_dbg.get("valid"):
                    _float_keys = ["ratio", "inner_density",
                                   "fft_score", "fft_peak_rate", "fft_radial_cov"]
                    for _k in _float_keys:
                        _v = _raw_dbg.get(_k, 0.0)
                        _screen_ema[_k] = (_EMA_A * _v
                                           + (1 - _EMA_A) * _screen_ema.get(_k, _v))
                    # ดึง timing จาก liveness state ของคนแรกที่เจอ
                    _lv = next(iter(session.liveness.values()), None)
                    _scr_dur  = (now_ts - _lv.screen_detect_start_ts
                                 if _lv and _lv.screen_detect_start_ts > 0 else 0.0)
                    _real_dur = (now_ts - _lv.screen_real_start_ts
                                 if _lv and _lv.screen_real_start_ts > 0 else 0.0)

                    _screen_debug_display = {
                        "valid":          True,
                        "ratio":          _screen_ema.get("ratio", 0.0),
                        "threshold":      _raw_dbg.get("threshold", cfg.SCREEN_EDGE_MAX),
                        "inner_density":  _screen_ema.get("inner_density", 0.0),
                        "inner_thresh":   _raw_dbg.get("inner_thresh", cfg.SCREEN_INNER_MAX),
                        "fft_score":      _screen_ema.get("fft_score", 1.0),
                        "fft_thresh":     _raw_dbg.get("fft_thresh", cfg.FFT_SCORE_MIN),
                        "fft_peak_rate":  _screen_ema.get("fft_peak_rate", 0.0),
                        "fft_radial_cov": _screen_ema.get("fft_radial_cov", 0.0),
                        "screen_timer":   _scr_dur,
                        "real_timer":     _real_dur,
                        "screen_confirm": cfg.SCREEN_CONFIRM_SEC,
                        "real_reset":     cfg.SCREEN_RESET_SEC,
                        # bool ใช้ค่าล่าสุดตรงๆ (ไม่ smooth)
                        "is_border":  _raw_dbg.get("is_border", False),
                        "is_inner":   _raw_dbg.get("is_inner", False),
                        "is_fft":     _raw_dbg.get("is_fft", False),
                        "is_screen":  _raw_dbg.get("is_screen", False),
                    }

            # ── Draw ──
            if cfg.SHOW_LANDMARKS and lm_dict:
                ui.draw_landmarks(frame, lm_dict, scale=1.0)

            color, label = ui.get_face_visual(name, person, liveness)
            ui.draw_face_box(frame, left, top, right, bottom, color, label)

        # ─── Guide overlay ───
        ui.draw_face_guide(frame, _face_with_names,
                           session.liveness, session.persons, now_ts)

        # ─── Hands + HUD + Panel ───
        ui.draw_hands(frame, hand_results)

        remaining = max(0, cfg.TEST_DURATION_SECONDS - int(now_ts - start_ts)) if cfg.TEST_MODE else 0
        ui.draw_hud(frame, display_fps, cfg.TEST_MODE, checkout_done, remaining, cfg.SHOW_FPS)

        panel = ui.build_panel(session.persons, session.liveness, frame.shape[0],
                               screen_debug=_screen_debug_display if cfg.TEST_MODE else None,
                               _cache=_local_panel_cache)

        # ─── Push rendered frame + state สำหรับ web ───
        remaining = max(0, cfg.TEST_DURATION_SECONDS - int(now_ts - start_ts)) if cfg.TEST_MODE else 0
        _combined = np.hstack([frame, panel])
        _state = {
            "ts":         now_ts,
            "fps":        display_fps,
            "frame_size": list(raw_frame.shape[:2]),
            "idle":       False,
            "next_window": None,
            "faces": [
                {
                    "name":  mask_pid(name),
                    "bbox":  [int(l), int(t), int(r2), int(b)],
                    "color": list(ui.get_face_visual(name,
                                  session.persons.get(name),
                                  session.liveness.get(name))[0]),
                    "label": ui.get_face_visual(name,
                                  session.persons.get(name),
                                  session.liveness.get(name))[1],
                    "in_oval": True,
                }
                for (t, r2, b, l), name in _face_with_names
            ],
            "guide": _compute_guide_state(
                _face_with_names, session.liveness,
                oval_cx, oval_cy, oval_ew, oval_eh, now_ts,
            ),
            "persons": {
                mask_pid(n): {
                    "display_name": p.display_name or mask_pid(n),
                    # per_id เต็มยังอยู่ในสตรีม JSON (ต้องใช้ lookup รูปจาก External API
                    # ผ่าน /person/{per_id}) — แต่ UI display + ชื่อไฟล์จะ mask ทั้งหมด
                    "per_id":        p.per_id or "",
                    "per_id_masked": mask_pid(p.per_id),
                    "organize_th":  p.organize_th or "",
                    "posname_th":   p.posname_th or "",
                    "checked_in":   p.checked_in,
                    "checked_out":  p.checked_out,
                    "first_seen":   p.first_seen.strftime("%H:%M:%S") if p.first_seen else "-",
                    "last_seen":    p.last_seen.strftime("%H:%M:%S")  if p.last_seen  else "-",
                }
                for n, p in session.persons.items()
            },
            "hud": {
                "test_mode":     cfg.TEST_MODE,
                "checkout_done": checkout_done,
                "remaining":     remaining,
                "show_fps":      cfg.SHOW_FPS,
            },
        }
        stream_frame = raw_frame.copy()
        ui.draw_face_guide(stream_frame, _face_with_names,
                           session.liveness, session.persons, now_ts)
        ui.draw_hands(stream_frame, hand_results)

        if _HEADLESS:
            _post_live_frame(cam_id, stream_frame)
            _post_live_state(cam_id, _state)
        else:
            stream_server.push_frame(cam_id, stream_frame)
            stream_server.push_state(cam_id, _state)

        _imshow(_combined)

        if stream_server.get_cv_window():
            key = cv2.waitKey(1) & 0xFF
            if key == ord("q") or key == 27:
                break
            elif key == ord("f"):
                _toggle_fullscreen()
        else:
            if _stop_event.is_set() or (cam_stop_event and cam_stop_event.is_set()):
                break
            # check file flag (subprocess mode)
            _flag = _pl_mod(__file__).parent / f"cam_stop_{cam_id}.flag"
            if _flag.exists():
                try: _flag.unlink()
                except: pass
                print(f"[MAIN] cam_stop flag detected: {cam_id}")
                break
            time.sleep(0.001)

    session.save_snapshots()
    hands.close()
    cam.release()
    if stream_server.get_cv_window():
        cv2.destroyWindow(win_name)


_camera_threads: list = []   # track worker threads สำหรับ restart
_cam_stop_events: dict = {}  # cam_id → threading.Event สำหรับหยุดเฉพาะกล้อง


def stop_cameras():
    """หยุด camera workers ทั้งหมด"""
    _stop_event.set()
    print("[MAIN] stop_cameras() called")


def stop_camera(cam_id: str):
    """หยุดเฉพาะ camera worker ตาม cam_id (in-process หรือ file flag)"""
    ev = _cam_stop_events.get(cam_id)
    if ev:
        ev.set()
    # เขียน flag file เพื่อ subprocess mode ด้วย
    (_pl_mod(__file__).parent / f"cam_stop_{cam_id}.flag").touch()
    print(f"[MAIN] stop_camera({cam_id}) called")


def start_camera_workers():
    """เริ่ม/hotload camera worker threads — เรียกได้จาก /system/start หรือ /cameras/reload
    ถ้ามี workers อยู่แล้ว จะ spawn เฉพาะกล้องใหม่ที่ยังไม่มี thread (hotload เหมือนกด R)
    ถ้ายังไม่มี workers เลย จะ start ทุกตัวใหม่"""
    global _camera_threads
    import threading as _threading

    configs = stream_server._load_cam_configs()
    if not configs:
        configs = getattr(cfg, "CAMERAS", [])
        configs = [c for c in configs if c.get("url") or c.get("index") is not None]
    if not configs:
        configs = [{
            "id":    "cam1",
            "name":  "CAM_MAIN",
            "url":   cfg.CAMERA_URL or None,
            "index": 1,
            "flip":  cfg.CAMERA_FLIP,
        }]
    if not stream_server._CAMERAS_JSON.exists() and configs:
        stream_server._save_cam_configs(configs)

    # filter เฉพาะกล้องที่เลือก (ถ้า FACE_CAM_IDS ถูกตั้ง)
    _face_cam_ids = os.environ.get("FACE_CAM_IDS", "")
    if _face_cam_ids:
        _selected = set(_face_cam_ids.split(","))
        configs = [c for c in configs if c.get("id") in _selected]
    configs = [
        {**c, "url": _resolve_url(c["url"])} if "url" in c else c
        for c in configs
    ]

    # กรอง alive threads ออกก่อน
    _camera_threads = [t for t in _camera_threads if t.is_alive()]
    running_ids = {t.name for t in _camera_threads}

    # clear _stop_event เสมอก่อน spawn threads ใหม่
    # (ถ้าไม่ทำ thread ใหม่จะ exit ทันทีถ้า event ยังถูก set ค้างจาก stop ก่อนหน้า)
    _stop_event.clear()

    new_cams = [c for c in configs if f"cam-{c['id']}" not in running_ids]
    if not new_cams:
        print("[MAIN] All cameras already running — nothing to hotload")
        return

    if _sel_cam.get("id") is None and configs:
        _sel_cam["id"] = configs[0]["id"]

    for cam_cfg in new_cams:
        cam_id = cam_cfg['id']
        ev = _t.Event()
        _cam_stop_events[cam_id] = ev
        t = _threading.Thread(
            target=run_camera, args=(cam_cfg, ev),
            name=f"cam-{cam_id}", daemon=True,
        )
        _camera_threads.append(t)
        t.start()
        print(f"[MAIN] Camera worker started: {cam_id}")
    print(f"[MAIN] Hotloaded {len(new_cams)} new cam(s): {[c['id'] for c in new_cams]}")


def start_cameras():
    """เริ่ม camera workers + display loop — ใช้ตอนรัน __main__"""
    import threading as _threading

    cameras = getattr(cfg, "CAMERAS", [])
    cameras = [c for c in cameras if c.get("url") or c.get("index") is not None]
    if not cameras:
        cameras = [{
            "id":    "cam1",
            "name":  "CAM_MAIN",
            "url":   cfg.CAMERA_URL or None,
            "index": 1,
            "flip":  cfg.CAMERA_FLIP,
        }]
    if not stream_server._CAMERAS_JSON.exists() and cameras:
        stream_server._save_cam_configs(cameras)
        print(f"[CM] สร้าง cameras.json จาก config ({len(cameras)} กล้อง)")
    cameras = [
        {**c, "url": _resolve_url(c["url"])} if "url" in c else c
        for c in cameras
    ]

    if True:
        # ─── Multi-cam mode ───────────────────────────────────────────────────
        stream_server.set_cv_window(False)
        print(f"[MAIN] Camera mode: {[c['id'] for c in cameras]}")

        cam_ids   = [c["id"]   for c in cameras]
        cam_names = {c["id"]: c["name"] for c in cameras}

        _sel_cam["id"] = cam_ids[0]

        threads = [
            _threading.Thread(
                target=run_camera, args=(cam_cfg,),
                name=f"cam-{cam_cfg['id']}", daemon=True,
            )
            for cam_cfg in cameras
        ]
        for t in threads:
            t.start()

        # ─── Main thread: single-window display loop ─────────────────────────
        BAR_H      = cfg.CAM_TAB_BAR_H
        WIN_NAME   = cfg.WINDOW_TITLE
        _ADD_BTN_W = cfg.CAM_ADD_BTN_W
        _DEL_BTN_W = cfg.CAM_DEL_BTN_W
        _fs        = {"on": False}

        # ─── UI state สำหรับ camera management ──────────────────────────────
        _mgmt = {
            "mode":    None,   # None | "add" | "del"
            "field":   0,      # field ที่ active ใน form
            "data":    {},     # ข้อมูลใน form
            "del_cam": None,   # cam_id ที่กำลังจะลบ
            "msg":     "",     # toast message
            "msg_ts":  0.0,
        }
        _del_btns_ref = [[]]
        _add_btn_ref  = [(0, 0)]

        # ─── Form field definitions ──────────────────────────────────────────
        _FIELDS_USB = [("Name",       "name"),
                       ("Type",       "type"),
                       ("USB Index",  "index"),
                       ("Flip",       "flip")]
        _FIELDS_IP  = [("Name",       "name"),
                       ("Type",       "type"),
                       ("URL (RTSP)", "url"),
                       ("Flip",       "flip")]

        def _form_init() -> dict:
            return {"name": "", "type": "usb", "index": "0", "url": "", "flip": False}

        def _open_add_form():
            _mgmt["mode"]  = "add"
            _mgmt["field"] = 0
            _mgmt["data"]  = _form_init()

        def _open_del_confirm(cid: str):
            _mgmt["mode"]    = "del"
            _mgmt["del_cam"] = cid

        # ─── Tab bar (with + and × buttons) ─────────────────────────────────
        def _draw_bar(frame_w: int, cur_active: str, pushed: set) -> tuple:
            bar        = np.full((BAR_H, frame_w, 3), (28, 28, 28), dtype=np.uint8)
            tab_area_w = frame_w - _ADD_BTN_W
            tab_w      = tab_area_w // max(len(cam_ids), 1)
            tabs, del_btns = [], []

            for i, cid in enumerate(cam_ids):
                x1 = i * tab_w
                x2 = min((i + 1) * tab_w, tab_area_w)
                is_active = (cid == cur_active)
                if is_active:
                    cv2.rectangle(bar, (x1, 0), (x2-1, BAR_H-1), (45, 45, 45), -1)
                cv2.rectangle(bar, (x1, BAR_H-3), (x2-1, BAR_H-1),
                              (0, 255, 255) if is_active else (60, 60, 60), -1)

                # ─ "×" delete button (ขวาสุดของ tab)
                dx1, dx2 = x2 - _DEL_BTN_W, x2
                cv2.putText(bar, "x", (dx1 + 5, BAR_H // 2 + 7),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.60,
                            (0, 50, 230) if is_active else (0, 35, 160), 2, cv2.LINE_AA)
                del_btns.append((dx1, dx2, cid))

                # ─ ชื่อ tab (พื้นที่ซ้ายของ "×")
                label    = cam_names.get(cid, cid)
                col      = (0, 255, 255) if is_active else (140, 140, 140)
                (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.44, 1)
                usable_w = (x2 - _DEL_BTN_W) - x1
                lx       = x1 + max(12, (usable_w - tw) // 2)
                cv2.putText(bar, label, (lx, (BAR_H + th) // 2 - 2),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.44, col, 1, cv2.LINE_AA)
                dot_col = (0, 220, 80) if cid in pushed else (70, 70, 70)
                cv2.circle(bar, (x1 + 10, BAR_H // 2), 4, dot_col, -1)
                tabs.append((x1, x2, cid))

            # ─ "+" add button (ขวาสุดของ bar)
            ax = frame_w - _ADD_BTN_W
            cv2.rectangle(bar, (ax+2, 3), (frame_w-3, BAR_H-4), (14, 36, 14), -1)
            cv2.rectangle(bar, (ax+2, 3), (frame_w-3, BAR_H-4), (35, 80, 35), 1)
            cv2.putText(bar, "+", (ax + 10, BAR_H // 2 + 7),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.75, (50, 200, 50), 1, cv2.LINE_AA)

            return bar, tabs, del_btns, (ax, frame_w)

        # ─── Overlay: Add Camera form ────────────────────────────────────────
        def _draw_add_form(img, data: dict, active_field: int):
            H, W = img.shape[:2]
            ov = img.copy()
            cv2.rectangle(ov, (0, 0), (W, H), (0, 0, 0), -1)
            cv2.addWeighted(ov, 0.55, img, 0.45, 0, img)

            FW, FH = cfg.CAM_ADD_FORM_W, cfg.CAM_ADD_FORM_H
            fx, fy = (W - FW) // 2, (H - FH) // 2
            cv2.rectangle(img, (fx+4, fy+4), (fx+FW+4, fy+FH+4), (0, 0, 0), -1)
            cv2.rectangle(img, (fx, fy), (fx+FW, fy+FH), (20, 20, 20), -1)
            cv2.rectangle(img, (fx, fy), (fx+FW, fy+FH), (55, 55, 55), 1)
            cv2.rectangle(img, (fx, fy), (fx+FW, fy+40), (14, 14, 14), -1)
            cv2.putText(img, "+ Add Camera",
                        (fx+16, fy+27), cv2.FONT_HERSHEY_SIMPLEX,
                        0.55, (0, 200, 200), 1, cv2.LINE_AA)

            fields = _FIELDS_IP if data.get("type") == "ip" else _FIELDS_USB
            for i, (label, fkey) in enumerate(fields):
                y      = fy + 68 + i * 52
                is_act = (i == active_field)
                lc     = (0, 200, 200) if is_act else (100, 100, 100)
                cv2.putText(img, label, (fx+14, y),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.40, lc, 1, cv2.LINE_AA)

                bx1, by1 = fx + 140, y - 22
                bx2, by2 = fx + FW - 14, y + 8
                cv2.rectangle(img, (bx1, by1), (bx2, by2),
                              (40, 40, 40) if is_act else (18, 18, 18), -1)
                cv2.rectangle(img, (bx1, by1), (bx2, by2),
                              (0, 170, 170) if is_act else (42, 42, 42), 1)

                # เคอเซอร์กะพริบ ~2 Hz
                _cur = "|" if (is_act and int(time.time() * 2) % 2 == 0) else ""

                if fkey == "type":
                    val  = "USB Webcam (index)" if data.get("type") == "usb" else "IP Camera (RTSP/HTTP)"
                    vc   = (160, 220, 160) if data.get("type") == "usb" else (160, 160, 220)
                    hint = "  [Space=toggle]"
                elif fkey == "url":
                    raw  = data.get(fkey, "")
                    val  = raw + _cur
                    vc   = (180, 220, 180) if raw.startswith("$") else (220, 220, 220)
                    hint = "  → auto-saved to .env"
                elif fkey == "flip":
                    val  = "ON (flip horizontal)" if data.get("flip") else "OFF"
                    vc   = (200, 200, 100) if data.get("flip") else (150, 150, 150)
                    hint = "  [Space=toggle]"
                else:
                    raw  = data.get(fkey, "")
                    val  = raw + _cur
                    vc   = (220, 220, 220)
                    hint = ""

                # trim ถ้าข้อความยาวเกิน
                max_px = bx2 - bx1 - 10
                fs = 0.40
                (tw, _), _ = cv2.getTextSize(val, cv2.FONT_HERSHEY_SIMPLEX, fs, 1)
                while tw > max_px and len(val) > 2:
                    val = "..." + val[4:]
                    (tw, _), _ = cv2.getTextSize(val, cv2.FONT_HERSHEY_SIMPLEX, fs, 1)

                cv2.putText(img, val, (bx1+6, y-4),
                            cv2.FONT_HERSHEY_SIMPLEX, fs, vc, 1, cv2.LINE_AA)
                if hint and is_act:
                    cv2.putText(img, hint, (bx2+4, y-4),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.30,
                                (70, 70, 70), 1, cv2.LINE_AA)

            cv2.putText(img,
                        "Tab/Down=Next  Up=Back  Space=Toggle  Enter=Save  Esc=Cancel",
                        (fx+14, fy+FH-12),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.31, (65, 65, 65), 1, cv2.LINE_AA)

        # ─── Overlay: Delete confirm ─────────────────────────────────────────
        def _draw_del_confirm(img, cam_id: str):
            H, W = img.shape[:2]
            ov = img.copy()
            cv2.rectangle(ov, (0, 0), (W, H), (0, 0, 0), -1)
            cv2.addWeighted(ov, 0.60, img, 0.40, 0, img)

            BW, BH = cfg.CAM_DEL_CONFIRM_W, cfg.CAM_DEL_CONFIRM_H
            bx, by = (W - BW) // 2, (H - BH) // 2
            cv2.rectangle(img, (bx+3, by+3), (bx+BW+3, by+BH+3), (0, 0, 0), -1)
            cv2.rectangle(img, (bx, by), (bx+BW, by+BH), (25, 10, 10), -1)
            cv2.rectangle(img, (bx, by), (bx+BW, by+BH), (100, 30, 30), 1)
            cv2.putText(img, "Delete Camera?",
                        (bx+16, by+36), cv2.FONT_HERSHEY_SIMPLEX,
                        0.60, (80, 80, 220), 1, cv2.LINE_AA)
            name = cam_names.get(cam_id, cam_id)
            cv2.putText(img, f"{cam_id}: {name}",
                        (bx+16, by+70), cv2.FONT_HERSHEY_SIMPLEX,
                        0.46, (200, 200, 200), 1, cv2.LINE_AA)
            cv2.putText(img, "Restart required to apply changes",
                        (bx+16, by+98), cv2.FONT_HERSHEY_SIMPLEX,
                        0.37, (120, 100, 50), 1, cv2.LINE_AA)
            cv2.putText(img, "[Y] / Enter = Confirm    [N] / Esc = Cancel",
                        (bx+16, by+132), cv2.FONT_HERSHEY_SIMPLEX,
                        0.41, (160, 160, 160), 1, cv2.LINE_AA)

        # ─── Toast message ───────────────────────────────────────────────────
        def _draw_toast(img, msg: str):
            H, W = img.shape[:2]
            col = (0, 160, 60) if msg.startswith("✓") else (0, 100, 200)
            (tw, th), _ = cv2.getTextSize(msg, cv2.FONT_HERSHEY_SIMPLEX, 0.45, 1)
            px, py = 14, 8
            rx1 = W - tw - px * 2 - 20
            ry1 = H - th - py * 2 - 10
            rx2, ry2 = W - 10, H - 10
            cv2.rectangle(img, (rx1-2, ry1-2), (rx2+2, ry2+2), (0, 0, 0), -1)
            cv2.rectangle(img, (rx1, ry1), (rx2, ry2), col, -1)
            cv2.putText(img, msg, (rx1 + px, ry2 - py - 2),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1, cv2.LINE_AA)

        # ─── Camera Management Actions ───────────────────────────────────────
        def _do_save_camera():
            data = _mgmt["data"]
            name = data.get("name", "").strip()
            if not name:
                _mgmt["field"] = 0
                return
            configs = stream_server._load_cam_configs()
            cam_id  = stream_server._next_cam_id(configs)
            new_cam: dict = {"id": cam_id, "name": name, "flip": bool(data.get("flip"))}
            if data.get("type") == "ip":
                url = data.get("url", "").strip()
                if url and not url.startswith("$"):
                    # URL ตรง → auto-save ลง .env แล้วเก็บ reference แทน
                    env_key = _cam_env_key(cam_id)
                    _env_set(env_key, url)
                    os.environ[env_key] = url   # ให้ process ปัจจุบันเห็นด้วย
                    new_cam["url"] = f"${env_key}"
                    print(f"[CM] URL saved to .env as {env_key}")
                else:
                    new_cam["url"] = url   # ว่าง หรือ $VAR_NAME → เก็บตรง
            else:
                try:
                    new_cam["index"] = int(data.get("index", 0))
                except ValueError:
                    new_cam["index"] = 0
            configs.append(new_cam)
            stream_server._save_cam_configs(configs)
            print(f"[CM] เพิ่มกล้อง {cam_id} ({name})")
            # Live update tab bar immediately
            cam_ids.append(cam_id)
            cam_names[cam_id] = name
            _mgmt["mode"]   = None
            _mgmt["msg"]    = f"✓ Added {cam_id} ({name}) — press R to activate"
            _mgmt["msg_ts"] = time.time()

        def _do_refresh_cameras():
            """Spawn threads for cameras added since startup (press R)"""
            configs = stream_server._load_cam_configs()
            configs = [
                {**c, "url": _resolve_url(c["url"])} if "url" in c else c
                for c in configs
            ]
            running = {t.name for t in threads if t.is_alive()}
            new_cams = [c for c in configs if f"cam-{c['id']}" not in running]
            if not new_cams:
                _mgmt["msg"]    = "All cameras already running"
                _mgmt["msg_ts"] = time.time()
                return
            for cam_cfg in new_cams:
                t = _threading.Thread(
                    target=run_camera,
                    args=(cam_cfg,),
                    name=f"cam-{cam_cfg['id']}",
                    daemon=True,
                )
                threads.append(t)
                t.start()
                print(f"[CM] Started thread for {cam_cfg['id']}")
            _mgmt["msg"]    = f"Reloaded: {len(new_cams)} new cam(s) started"
            _mgmt["msg_ts"] = time.time()

        def _do_delete_camera():
            cam_id = _mgmt.get("del_cam")
            if not cam_id:
                return
            if len(cam_ids) <= 1:
                _mgmt["mode"]    = None
                _mgmt["del_cam"] = None
                _mgmt["msg"]     = "! Cannot delete the last camera"
                _mgmt["msg_ts"]  = time.time()
                return
            configs = stream_server._load_cam_configs()
            # ลบ env var ถ้ากล้องนี้ใช้ $VAR_NAME
            deleted = next((c for c in configs if c.get("id") == cam_id), None)
            if deleted:
                url = deleted.get("url", "")
                if isinstance(url, str) and url.startswith("$"):
                    env_key = url[1:]
                    _env_del(env_key)
                    os.environ.pop(env_key, None)
                    print(f"[CM] Removed {env_key} from .env")
            new_configs = [c for c in configs if c.get("id") != cam_id]
            stream_server._save_cam_configs(new_configs)
            # Live update tab bar
            if cam_id in cam_ids:
                cam_ids.remove(cam_id)
                cam_names.pop(cam_id, None)
            with _disp_lock:
                if _sel_cam["id"] == cam_id and cam_ids:
                    _disp_slot["frame"] = None
                    _sel_cam["id"]      = cam_ids[0]
            print(f"[CM] ลบกล้อง {cam_id}")
            _mgmt["mode"]    = None
            _mgmt["del_cam"] = None
            _mgmt["msg"]     = f"✓ Deleted {cam_id} — restart to apply"
            _mgmt["msg_ts"]  = time.time()

        # ─── Keyboard handlers ───────────────────────────────────────────────
        _KEY_DOWN    = cfg.KEY_DOWN
        _KEY_UP      = cfg.KEY_UP
        _KEY_ENTER   = cfg.KEY_ENTER
        _KEY_BS      = cfg.KEY_BS
        _CAPSLOCK_KEY = cfg.KEY_CAPSLOCK
        _IGNORE_KEYS  = cfg.KEY_IGNORE

        _caps = {"lock": False}   # ─ track CapsLock state เอง

        def _handle_form_key(key: int):
            data   = _mgmt["data"]
            fields = _FIELDS_IP if data.get("type") == "ip" else _FIELDS_USB
            fi     = _mgmt["field"]
            _, fkey = fields[fi]

            # ── Modifier / special keys ────────────────────────────────────
            if key == 27:   # ESC → ยกเลิก
                _mgmt["mode"] = None
                return
            if key == _CAPSLOCK_KEY:
                _caps["lock"] = not _caps["lock"]
                return
            if key in _IGNORE_KEYS:
                return
            if key in _KEY_DOWN:
                _mgmt["field"] = (fi + 1) % len(fields)
                return
            if key in _KEY_UP:
                _mgmt["field"] = (fi - 1) % len(fields)
                return
            if key in _KEY_ENTER:
                if fi == len(fields) - 1:
                    _do_save_camera()
                else:
                    _mgmt["field"] = (fi + 1) % len(fields)
                return
            if fkey in ("type", "flip"):
                if key == ord(" "):
                    if fkey == "type":
                        data["type"] = "ip" if data.get("type") == "usb" else "usb"
                    else:
                        data["flip"] = not data.get("flip", False)
                return
            # ── Text fields: name / index / url ───────────────────────────
            if key in _KEY_BS:
                data[fkey] = data.get(fkey, "")[:-1]
            elif 32 <= key < 127:
                ch = chr(key)
                # CapsLock: convert lowercase → uppercase (OS บางตัวไม่ apply เอง)
                if _caps["lock"] and ch.isalpha() and ch.islower():
                    ch = ch.upper()
                data[fkey] = data.get(fkey, "") + ch

        def _handle_del_key(key: int):
            if key in _KEY_ENTER or key == ord("y") or key == ord("Y"):
                _do_delete_camera()
            elif key == 27 or key == ord("n") or key == ord("N"):
                _mgmt["mode"]    = None
                _mgmt["del_cam"] = None

        # ─── Mouse callback ──────────────────────────────────────────────────
        _sc       = {"x": 1.0, "y": 1.0}
        _tabs_ref = [[]]

        def _switch_cam(new_cid: str):
            """สลับกล้อง: clear slot ก่อน ป้องกัน frame เก่าค้างอยู่"""
            with _disp_lock:
                _disp_slot["frame"] = None
                _sel_cam["id"]      = new_cid
            print(f"[DISPLAY] สลับกล้อง → {new_cid} ({cam_names.get(new_cid, new_cid)})")

        def _on_mouse(event, x, y, flags, param):
            if event != cv2.EVENT_LBUTTONDOWN:
                return
            if _mgmt["mode"] is not None:
                return   # ignore clicks ขณะ overlay เปิดอยู่
            ox, oy = x / _sc["x"], y / _sc["y"]
            if oy >= BAR_H:
                return
            # ตรวจปุ่ม "+"
            ax1, ax2 = _add_btn_ref[0]
            if ax1 <= ox <= ax2:
                _open_add_form()
                return
            # ตรวจปุ่ม "×" ของแต่ละ tab
            for (dx1, dx2, cid) in _del_btns_ref[0]:
                if dx1 <= ox < dx2:
                    _open_del_confirm(cid)
                    return
            # สลับกล้อง
            for (tx1, tx2, cid) in _tabs_ref[0]:
                if tx1 <= ox < tx2:
                    _switch_cam(cid)
                    break

        cv2.namedWindow(WIN_NAME, cv2.WINDOW_NORMAL)
        cv2.resizeWindow(WIN_NAME, cfg.MAIN_WINDOW_W, cfg.MAIN_WINDOW_H)
        cv2.setMouseCallback(WIN_NAME, _on_mouse)

        _placeholder = np.zeros((480, 960, 3), dtype=np.uint8)
        cv2.putText(_placeholder, "Waiting for camera...",
                    (280, 240), cv2.FONT_HERSHEY_SIMPLEX, 0.8,
                    (80, 80, 80), 1, cv2.LINE_AA)
        _last_frame  = None
        _prev_active = _sel_cam["id"]

        def _toggle_fs():
            _fs["on"] = not _fs["on"]
            cv2.setWindowProperty(WIN_NAME, cv2.WND_PROP_FULLSCREEN,
                cv2.WINDOW_FULLSCREEN if _fs["on"] else cv2.WINDOW_NORMAL)

        _FS_KEYS = cfg.KEY_FS

        while any(t.is_alive() for t in threads):
            with _disp_lock:
                frame  = _disp_slot["frame"]
                frame  = frame.copy() if frame is not None else None
                active = _sel_cam["id"]
                pushed = set(_cam_has_pushed)

            if active != _prev_active:
                _last_frame  = None
                _prev_active = active

            if frame is not None:
                _last_frame = frame
            content = _last_frame if _last_frame is not None else _placeholder

            bar, tabs, del_btns, add_btn = _draw_bar(content.shape[1], active, pushed)
            _tabs_ref[0]     = tabs
            _del_btns_ref[0] = del_btns
            _add_btn_ref[0]  = add_btn
            combined = np.vstack([bar, content])

            # ── วาด overlay ─────────────────────────────────────────────────
            if _mgmt["mode"] == "add":
                _draw_add_form(combined, _mgmt["data"], _mgmt["field"])
            elif _mgmt["mode"] == "del" and _mgmt["del_cam"]:
                _draw_del_confirm(combined, _mgmt["del_cam"])

            # ── Toast message (หายไปใน 4 วิ) ────────────────────────────────
            if _mgmt["msg"]:
                if time.time() - _mgmt["msg_ts"] < 4.0:
                    _draw_toast(combined, _mgmt["msg"])
                else:
                    _mgmt["msg"] = ""

            if _fs["on"]:
                orig_h, orig_w = combined.shape[:2]
                combined = cv2.resize(combined, (SCREEN_W, SCREEN_H),
                                      interpolation=cv2.INTER_LINEAR)
                _sc["x"] = SCREEN_W / orig_w
                _sc["y"] = SCREEN_H / orig_h
            else:
                _sc["x"] = 1.0
                _sc["y"] = 1.0

            cv2.imshow(WIN_NAME, combined)

            key = cv2.waitKeyEx(1)
            if key == -1:
                pass
            elif _mgmt["mode"] == "add":
                _handle_form_key(key)
            elif _mgmt["mode"] == "del":
                _handle_del_key(key)
            elif key == ord("q") or key == 27:
                _stop_event.set()
                break
            elif key in _FS_KEYS:
                _toggle_fs()
            elif key == ord("r") or key == ord("R"):
                _do_refresh_cameras()
            else:
                for i, cid in enumerate(cam_ids):
                    if key == ord(str(i + 1)):
                        _switch_cam(cid)
                        break

        for t in threads:
            t.join(timeout=5)
        cv2.destroyAllWindows()


# ─── ลงทะเบียน lifecycle callbacks กับ stream_server ────────────────────────
# ให้ /system/start และ /system/stop ใน stream_server เรียก start/stop ได้
stream_server.register_lifecycle(start_camera_workers, stop_cameras)


if __name__ == "__main__":
    # ต้องเรียกก่อนทุกอย่าง — set LD_LIBRARY_PATH ให้ชี้ venv's CUDA/cuDNN libs
    # แล้ว re-exec ตัวเองเพื่อให้ ONNX Runtime + mediapipe ใช้ cuBLAS เดียวกัน
    _ensure_nvidia_libs()

    _headless_mode = bool(os.environ.get("FACE_HEADLESS") or os.environ.get("SKIP_STREAM_SERVER"))
    if not _headless_mode:
        # โหมดปกติ (python main.py): stream server + display loop ครบชุด
        stream_server.start(cfg.STREAM_PORT)
        start_cameras()
    else:
        # headless mode (spawn จาก stream_server เว็บ):
        # ไม่เปิด stream_server ซ้ำ, ไม่เปิด OpenCV window
        # camera workers POST frame/state ไป stream_server (in-memory) แทน
        import signal as _sig
        _sig.signal(_sig.SIGTERM, lambda *_: _stop_event.set())
        start_camera_workers()

        _base = _pl_mod(__file__).parent
        while not _stop_event.is_set():
            # reload flag — spawn กล้องใหม่หรือกล้องที่ยังไม่ได้รัน
            _rf = _base / "cam_reload.flag"
            if _rf.exists():
                try: _rf.unlink()
                except: pass
                print("[MAIN] cam_reload flag detected — hotloading cameras")
                start_camera_workers()

            # per-cam start flag — spawn กล้องตัวนั้นใหม่
            for _sf in list(_base.glob("cam_start_*.flag")):
                _cid = _sf.stem[len("cam_start_"):]
                try: _sf.unlink()
                except: pass
                print(f"[MAIN] cam_start flag detected: {_cid}")
                # clear per-cam stop event ก่อน spawn ใหม่
                _ev = _t.Event()
                _cam_stop_events[_cid] = _ev
                import threading as _thr
                _ct = _thr.Thread(
                    target=run_camera,
                    args=(next((c for c in stream_server._load_cam_configs()
                                if c["id"] == _cid), {"id": _cid, "name": _cid}), _ev),
                    name=f"cam-{_cid}", daemon=True,
                )
                # ลบ thread เก่าของกล้องนี้ก่อน (ถ้ามี)
                _camera_threads[:] = [t for t in _camera_threads
                                      if t.is_alive() or t.name != f"cam-{_cid}"]
                _camera_threads.append(_ct)
                _ct.start()

            _stop_event.wait(timeout=0.5)

        # รอ worker threads ให้ save_snapshots() เสร็จก่อน process ออก
        for _t in list(_camera_threads):
            if _t.is_alive():
                _t.join(timeout=8)