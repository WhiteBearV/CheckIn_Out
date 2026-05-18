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


_ensure_nvidia_libs()

import cv2
import pickle
import numpy as np
import mediapipe as mp
from datetime import datetime, timedelta
from numpy.linalg import norm

import config as cfg
from camera import ThreadedCamera
from session_manager import SessionManager
import ui_renderer as ui

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
    return 1920, 1080   # fallback

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


# ─── Live State Writer (สำหรับ Dashboard) ───────────────────────────────────
# เขียน live_state.json ทุก 1 วินาที เพื่อให้ Dashboard อ่านได้แบบ real-time
# ไม่กระทบ performance เพราะ throttle ด้วย _LIVE_WRITE_INTERVAL
import json as _json

_LIVE_WRITE_INTERVAL = 1.0    # เขียนทุก N วินาที
_LIVE_DIR = os.path.join(os.path.dirname(__file__), "live")
os.makedirs(_LIVE_DIR, exist_ok=True)
# override ด้วย env FACE_LIVE_STATE_PATH เมื่อ start จาก api.py (multi-camera)
_LIVE_STATE_PATH = (
    os.environ.get("FACE_LIVE_STATE_PATH")
    or os.path.join(_LIVE_DIR, "live_state.json")
)

# ─── Boot Status Writer (สำหรับ Dashboard loading screen) ───────────────────
# เขียน boot_status.json ระหว่าง startup เพื่อให้ Dashboard แสดงหน้าโหลด
# ลบไฟล์เมื่อเข้า main loop แล้ว
_BOOT_PATH = (
    os.environ.get("FACE_BOOT_PATH")
    or os.path.join(_LIVE_DIR, "boot_status.json")
)

def _write_boot(msg: str):
    try:
        with open(_BOOT_PATH, "w", encoding="utf-8") as _f:
            _json.dump({"msg": msg, "ts": datetime.now().timestamp()}, _f)
    except Exception:
        pass

def _clear_boot():
    try:
        os.remove(_BOOT_PATH)
    except Exception:
        pass

# ─── Live Frame Writer (สำหรับ Dashboard Camera Stream) ─────────────────────
# เขียน live_frame.jpg ทุก ~67ms (15fps) เพื่อให้ Dashboard แสดง stream
# ใช้ atomic rename เพื่อป้องกัน race condition กับ api.py
# override ด้วย env FACE_LIVE_FRAME_PATH เมื่อ start จาก api.py (multi-camera)
_LIVE_FRAME_PATH = (
    os.environ.get("FACE_LIVE_FRAME_PATH")
    or os.path.join(_LIVE_DIR, "live_frame.jpg")
)
_LIVE_FRAME_INTERVAL = 1.0 / 15   # ~15fps
_LIVE_FRAME_JPEG_Q   = int(os.environ.get("FACE_STREAM_JPEG_QUALITY", 70))

def _write_live_frame(frame_bgr, path=None):
    """เขียน frame พร้อม overlay ทั้งหมดเป็น JPEG สำหรับ Dashboard stream"""
    p = path or _LIVE_FRAME_PATH
    tmp = p + ".tmp"
    try:
        ok, buf = cv2.imencode('.jpg', frame_bgr, [cv2.IMWRITE_JPEG_QUALITY, _LIVE_FRAME_JPEG_Q])
        if ok:
            with open(tmp, 'wb') as _fh:
                _fh.write(buf.tobytes())
            os.replace(tmp, p)
    except Exception:
        pass

def _write_live_state(now_ts: float, session, active: bool, path=None, in_frame_names: set = None):
    """
    เขียน session state ปัจจุบันลง live_state.json
    ─────────────────────────────────────────────────────────────────
    Dashboard อ่านผ่าน GET /session/live ทุก 2 วินาที
    ถ้า main.py หยุด → Dashboard ตรวจจาก ts ว่า stale (> 5 วิ)
    """
    persons_data = []
    for name, person in session.persons.items():
        lv = session.liveness.get(name)

        # แปลง liveness state → สถานะที่อ่านง่าย (เหมือน GUI label)
        if lv and lv.confirmed:
            liveness     = "confirmed"
            liveness_msg = "ผ่านการตรวจสอบ"
        elif lv and lv.failed:
            liveness     = "failed"
            liveness_msg = f"ล้มเหลว ({lv.fail_reason or '?'})"
        elif lv and lv.challenge_phase == "active":
            cn           = lv.challenge_number
            dn           = len(lv.challenge_done)
            liveness     = "challenge"
            liveness_msg = f"โชว์ {cn} นิ้ว (ขั้น {dn+1}/{cfg.CHALLENGE_COUNT})"
        else:
            # pending — แสดงด่านที่กำลัง block อยู่
            if lv:
                dp = lv.depth_pass_count
                if dp < cfg.DEPTH_FRAMES_REQUIRED:
                    liveness_msg = f"กำลังสแกน ({dp}/{cfg.DEPTH_FRAMES_REQUIRED})"
                elif cfg.BLINK_ENABLED and not lv.blink_ok:
                    liveness_msg = f"กรุณากะพริบตา ({lv.blink_count}/{cfg.BLINK_MIN})"
                elif not lv.motion_ok:
                    liveness_msg = "กรุณาขยับเล็กน้อย"
                elif not lv.texture_ok:
                    liveness_msg = "กำลังตรวจ texture..."
                elif not lv.fas_ok:
                    liveness_msg = "กำลังตรวจ AI..."
                else:
                    liveness_msg = "กำลังตรวจสอบ..."
            else:
                liveness_msg = "รอตรวจสอบ"
            liveness = "pending"

        if person.checked_out:
            _status = "OUT"
        elif person.checked_in:
            _status = "IN"
        else:
            _status = "PENDING"

        persons_data.append({
            "per_id":       person.per_id,
            "name":         person.display_name  or person.per_id,
            "display_name": person.display_name  or person.per_id,
            "prename_th":   person.prename_th    or "",
            "per_name":     person.per_name      or "",
            "per_surname":  person.per_surname   or "",
            "organize_th":  person.organize_th   or "",
            "posname_th":   person.posname_th    or "",
            "status":       _status,
            "in_time":      person.first_seen.isoformat() if person.first_seen else None,
            "out_time":     person.last_seen.isoformat()  if person.checked_out and person.last_seen else None,
            "checked_in":   person.checked_in,
            "checked_out":  person.checked_out,
            "first_seen":   person.first_seen.isoformat() if person.first_seen else None,
            "last_seen":    person.last_seen.isoformat()  if person.last_seen  else None,
            "liveness":     liveness,
            "liveness_msg": liveness_msg,
            "in_frame":     (name in in_frame_names) if in_frame_names is not None else False,
        })

    try:
        p = path or _LIVE_STATE_PATH
        with open(p, "w", encoding="utf-8") as _f:
            _json.dump({"ts": now_ts, "active": active, "persons": persons_data},
                       _f, ensure_ascii=False)
    except Exception as _e:
        pass   # ไม่ให้ crash หลัก loop


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


def run_camera(camera_index: int = 1, camera_name: str = "CAM_MAIN",
               camera_source=None, live_frame_path: str = None, live_state_path: str = None):
    """Main loop
    camera_source   — ถ้ากำหนด จะใช้แทน cfg.CAMERA_URL / camera_index
    live_frame_path — ถ้ากำหนด จะเขียน frame ไปที่ path นี้แทน _LIVE_FRAME_PATH
    live_state_path — ถ้ากำหนด จะเขียน state ไปที่ path นี้แทน _LIVE_STATE_PATH
    """

    # ─── โหลด face encodings (ArcFace 512d) ───
    _write_boot("กำลังโหลดฐานข้อมูลใบหน้า...")
    if not os.path.exists(cfg.ENCODINGS_FILE):
        _clear_boot()
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
    _write_boot("กำลังโหลด AI Model (InsightFace)...")
    from insightface.app import FaceAnalysis
    import onnxruntime as ort

    # Auto-detect — ใช้เฉพาะ provider ที่พร้อมจริง (ไม่ error อีก)
    # Auto-detect GPU — กรอง TensorRT ออก (ต้องลง TensorRT แยก)
    available = ort.get_available_providers()
    use_providers = [p for p in available if p not in ("TensorrtExecutionProvider", "CoreMLExecutionProvider")]
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
    _write_boot("กำลังเปิดกล้อง...")
    # ลำดับการใช้ source: parameter > env CAMERA_URL > camera_index
    cam_src = camera_source if camera_source is not None else (cfg.CAMERA_URL if cfg.CAMERA_URL else camera_index)
    # แปลง "0", "1" (string จาก env CAMERA_URL) เป็น int เพื่อให้ OpenCV เปิด USB ได้
    if isinstance(cam_src, str) and cam_src.isdigit():
        cam_src = int(cam_src)
    print(f"[CAM] {camera_name} → {cam_src}")
    cam = ThreadedCamera(cam_src)

    # ─── MediaPipe Hands ───
    _write_boot("กำลังติดตั้งระบบตรวจจับ...")
    hands = mp.solutions.hands.Hands(
        static_image_mode=False,
        max_num_hands=1,
        min_detection_confidence=0.6,
        min_tracking_confidence=0.5,
    )

    # ─── Session Manager ───
    session = SessionManager()

    # ─── แสดงข้อมูลเริ่มต้น ───
    print("=== ระบบตรวจใบหน้า (ArcFace + Multi-Layer Anti-Spoof) ===")
    print(f"[CAM]       {cam.width}x{cam.height}")
    print(f"[DEPTH]     {cfg.DEPTH_FRAMES_REQUIRED}/{cfg.DEPTH_FRAMES_WINDOW}")
    print(f"[TEXTURE]   {'ON' if cfg.TEXTURE_ENABLED else 'OFF'}")
    print(f"[SCREEN]    {'ON' if cfg.SCREEN_DETECT_ENABLED else 'OFF'}")
    if cfg.CHALLENGE_ENABLED:
        print(f"[CHALLENGE] x{cfg.CHALLENGE_COUNT}  timeout={cfg.CHALLENGE_TIMEOUT}s")
    print(f"[FAS]       {'ON' if cfg.FAS_ENABLED else 'OFF'}")

    # ─── Headless mode (สำหรับ Dashboard) ───
    # ตั้ง env var FACE_HEADLESS=1 เพื่อปิด GUI (ใช้เมื่อ start จาก api.py)
    # รัน python main.py ตรงๆ = GUI ปกติ
    import time as _time_gui
    _HEADLESS = os.environ.get("FACE_HEADLESS", "").lower() in ("1", "true", "yes")
    if _HEADLESS:
        print("[HEADLESS] GUI ปิด — ส่ง frame ผ่าน live_frame.jpg เท่านั้น")

    # ─── Always Active mode (สำหรับ Dashboard) ───
    # ตั้ง env var FACE_ALWAYS_ACTIVE=1 เพื่อข้าม Active Windows scheduler
    # รันตลอด 24 ชม. จนกว่าจะหยุดเอง — reset session รายวันตอนเที่ยงคืน
    _ALWAYS_ACTIVE = os.environ.get("FACE_ALWAYS_ACTIVE", "").lower() in ("1", "true", "yes")
    if _ALWAYS_ACTIVE:
        print("[ALWAYS_ACTIVE] ข้าม Active Windows — รันตลอดจนกว่าจะหยุดเอง")

    # ─── Dashboard Child Mode ───
    # เมื่อ spawn จาก api.py (FACE_CAMERA_CHILD=1) ให้ทำ face recognition ตลอดเวลา
    # ไม่สนใจ ACTIVE_WINDOWS — Dashboard ควบคุม start/stop เอง
    _DASHBOARD_CHILD = os.environ.get("FACE_CAMERA_CHILD", "").lower() in ("1", "true", "yes")

    # ─── หน้าต่าง ───
    win_name = "Face Attendance System"
    if not _HEADLESS:
        cv2.namedWindow(win_name, cv2.WINDOW_NORMAL)   # NORMAL เสมอ เพื่อให้ toggle ได้
    is_fullscreen  = cfg.FULLSCREEN
    _window_ready  = False   # True หลัง imshow ครั้งแรก

    def _apply_fullscreen():
        if _HEADLESS: return
        cv2.setWindowProperty(win_name, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)
        cv2.moveWindow(win_name, 0, 0)
        cv2.resizeWindow(win_name, SCREEN_W, SCREEN_H)

    def _apply_windowed():
        if _HEADLESS: return
        cv2.setWindowProperty(win_name, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_NORMAL)
        cv2.resizeWindow(win_name, 1280, 720)
        cv2.moveWindow(win_name, 100, 100)

    def _toggle_fullscreen():
        nonlocal is_fullscreen
        is_fullscreen = not is_fullscreen
        if is_fullscreen:
            _apply_fullscreen()
        else:
            _apply_windowed()

    def _imshow(display):
        """imshow + apply fullscreen หลัง frame แรก — ข้ามทั้งหมดถ้า headless"""
        if _HEADLESS:
            return
        nonlocal _window_ready
        if is_fullscreen and (display.shape[1] != SCREEN_W or display.shape[0] != SCREEN_H):
            display = cv2.resize(display, (SCREEN_W, SCREEN_H), interpolation=cv2.INTER_LINEAR)
        cv2.imshow(win_name, display)
        if not _window_ready:
            _window_ready = True
            cv2.waitKey(1)   # ให้ window manager map หน้าต่างก่อน
            if is_fullscreen:
                _apply_fullscreen()

    def _waitkey(ms: int) -> int:
        """cv2.waitKey ใน normal mode — time.sleep + return -1 ใน headless mode"""
        if _HEADLESS:
            _time_gui.sleep(ms / 1000.0)
            return -1
        return cv2.waitKey(ms)

    # ─── ตัวแปร loop ───
    start_ts           = datetime.now().timestamp()
    checkout_done      = False
    _last_state_write  = 0.0   # timestamp ล่าสุดที่เขียน live_state.json
    _last_frame_write  = 0.0   # timestamp ล่าสุดที่เขียน live_frame.jpg
    _current_date      = datetime.now().date()   # สำหรับ daily reset ใน always-active mode
    frame_count   = 0
    _was_active: bool | None = None   # None = iteration แรก (ยังไม่รู้ว่า active หรือเปล่า)
    last_faces    = []     # cache ผลลัพธ์ insightface
    fps_counter  = 0
    fps_timer    = start_ts
    display_fps  = 0.0
    last_face_ts = start_ts

    # ─── Screen Debug EMA (TEST_MODE) ───
    # smoothing กันกระพริบ — ค่าตัวเลขใช้ EMA, ค่า bool ใช้ latest
    _EMA_A = 0.20   # alpha: ต่ำ = smooth กว่า (ตอบสนองช้ากว่า)
    _screen_ema: dict = {}   # EMA ของ float values
    _screen_debug_display: dict = {}   # ส่งเข้า build_panel

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
    _clear_boot()   # โหลดเสร็จแล้ว — ลบ boot status ให้ Dashboard หยุดแสดง loading
    while True:
        ret, frame = cam.read()
        if not ret or frame is None:
            continue
        if cfg.CAMERA_FLIP:
            frame = cv2.flip(frame, 1)

        now    = datetime.now()
        now_ts = now.timestamp()
        frame_count += 1

        # ─── FPS ───
        fps_counter += 1
        if now_ts - fps_timer >= 1.0:
            display_fps = fps_counter / (now_ts - fps_timer)
            fps_counter, fps_timer = 0, now_ts

        # ─── Checkout (TEST_MODE เท่านั้น — ALWAYS_ACTIVE จัดการเองใน transition) ───
        if not _ALWAYS_ACTIVE:
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
        # ลำดับความสำคัญ:
        #   1. ALWAYS_ACTIVE (รวมถึงเมื่อ Dashboard spawn ด้วย FACE_ALWAYS_ACTIVE=1)
        #      → respect ACTIVE_WINDOWS: สลับ face/CCTV mode + auto-checkout
        #   2. DASHBOARD_CHILD เท่านั้น (ไม่มี ALWAYS_ACTIVE)
        #      → face recognition ตลอดเวลา ไม่สนใจตาราง
        #   3. Normal mode → ใช้ Active Windows ตาม config
        if _ALWAYS_ACTIVE:
            # ── Always Active: ใช้ ACTIVE_WINDOWS แบ่ง face mode / CCTV mode ──
            # ทำงานแม้ถูก spawn จาก Dashboard (FACE_CAMERA_CHILD=1 ป้องกันแค่ recursive spawn)
            _in_face_window = _in_active_window(now.time(), cfg.ACTIVE_WINDOWS)

            # reset วันใหม่ตอนเที่ยงคืน (อัพเดต _current_date เท่านั้น)
            if now.date() != _current_date:
                _current_date = now.date()
                print(f"[DAILY RESET] วันใหม่ {now.strftime('%Y-%m-%d')}")

            if _in_face_window and _was_active is False:
                # CCTV → Face recognition: reset session
                session       = SessionManager()
                last_faces    = []
                last_face_ts  = now_ts
                checkout_done = False
                print(f"[CCTV→FACE] เริ่มโหมด Face Recognition {now.strftime('%H:%M')}")

            if not _in_face_window and _was_active is True:
                # Face → CCTV mode: checkout คนที่ยังอยู่
                if not checkout_done:
                    checkout_done = True
                    session.do_checkout(camera_name, now)
                    session.save_snapshots()
                print(f"[FACE→CCTV] เข้าโหมด CCTV {now.strftime('%H:%M')}")

            _active = _in_face_window
        elif _DASHBOARD_CHILD:
            # spawn จาก api.py โดยไม่มี ALWAYS_ACTIVE → face recognition ตลอดเวลา
            if now.date() != _current_date:
                _current_date = now.date()
                session       = SessionManager()
                last_faces    = []
                last_face_ts  = now_ts
                checkout_done = False
                print(f"[DAILY RESET] วันใหม่ {now.strftime('%Y-%m-%d')}")
            _active = True
        else:
            # ── ใช้ Active Windows ตาม config ──
            _active = _in_active_window(now.time(), cfg.ACTIVE_WINDOWS)

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
            if _ALWAYS_ACTIVE:
                # ── CCTV mode: สตรีม raw frame ไม่มี face processing ──
                cctv_frame = frame.copy()
                cv2.putText(
                    cctv_frame,
                    now.strftime('%H:%M:%S'),
                    (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.9,
                    (180, 180, 180), 1, cv2.LINE_AA,
                )
                cctv_panel = np.zeros((cctv_frame.shape[0], cfg.PANEL_WIDTH, 3), dtype=np.uint8)
                _imshow(np.hstack([cctv_frame, cctv_panel]))
                if now_ts - _last_frame_write >= _LIVE_FRAME_INTERVAL:
                    _last_frame_write = now_ts
                    _write_live_frame(cctv_frame, path=live_frame_path)
                # เขียน live_state ด้วย active=False ให้ Dashboard รู้ว่าอยู่ใน CCTV mode
                if now_ts - _last_state_write >= _LIVE_WRITE_INTERVAL:
                    _last_state_write = now_ts
                    _write_live_state(now_ts, session, False, path=live_state_path)
                key = _waitkey(33) & 0xFF   # ~30fps
            else:
                # ── Idle mode: แสดงหน้าจอรอ ลด CPU/GPU ──
                next_dt = _next_window_start(now, cfg.ACTIVE_WINDOWS)
                ui.draw_idle_screen(frame, now, next_dt)
                idle_panel = np.zeros((frame.shape[0], cfg.PANEL_WIDTH, 3), dtype=np.uint8)
                _imshow(np.hstack([frame, idle_panel]))
                if now_ts - _last_frame_write >= _LIVE_FRAME_INTERVAL:
                    _last_frame_write = now_ts
                    _write_live_frame(frame, path=live_frame_path)
                key = _waitkey(500) & 0xFF   # ตรวจ key ทุก 500ms → ลด CPU
            if key == ord("q") or key == 27:
                break
            elif key == ord("f"):
                _toggle_fullscreen()
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

            _face_with_names.append((face_box, name))

            # ── Face crop ──
            pad = 15
            crop = orig_frame[max(0, top-pad):min(fh, bottom+pad),
                              max(0, left-pad):min(fw, right+pad)]

            if name == "Unknown":
                ui.draw_face_box(frame, left, top, right, bottom,
                                 cfg.Color.UNKNOWN, "Unknown")
                continue

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
                person.snapshot      = orig_frame.copy()
                person.snapshot_face = crop.copy()   # face crop สำหรับ Dashboard fullscreen
            elif liveness.confirmed and person.checked_in and not person.checked_out:
                # ผ่าน liveness ซ้ำหลัง absence → อัปเดต last_seen (ไม่สร้าง record ใหม่)
                is_reverify = person.absence_reset  # True เฉพาะ frame แรกที่ผ่านหลัง absence
                session.confirm_presence(name, now)
                if is_reverify:
                    person.snapshot_out = orig_frame.copy()

            if session.try_checkin(name, camera_name):
                session.save_snapshots()   # บันทึกรูปลง PicSAVE ทันทีหลัง check-in

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

        # ─── เขียน live frame สำหรับ Dashboard stream ────────────────────────────
        if now_ts - _last_frame_write >= _LIVE_FRAME_INTERVAL:
            _last_frame_write = now_ts
            _write_live_frame(frame, path=live_frame_path)

        panel = ui.build_panel(session.persons, session.liveness, frame.shape[0],
                               screen_debug=_screen_debug_display if cfg.TEST_MODE else None)
        _imshow(np.hstack([frame, panel]))

        # ─── เขียน live state สำหรับ Dashboard (throttle 1 วิ) ────────────────
        if now_ts - _last_state_write >= _LIVE_WRITE_INTERVAL:
            _last_state_write = now_ts
            _current_names = {n for _, n in _face_with_names}
            _write_live_state(now_ts, session, _active, path=live_state_path,
                              in_frame_names=_current_names)

        key = _waitkey(1) & 0xFF
        if key == ord("q") or key == 27:
            break
        elif key == ord("f"):
            _toggle_fullscreen()

    session.save_snapshots()
    hands.close()
    cam.release()
    if not _HEADLESS:
        cv2.destroyAllWindows()


if __name__ == "__main__":
    import time as _time

    _cameras_list = getattr(cfg, "CAMERAS_LIST", None)

    # ── Child process (spawned by multi-camera mode) หรือ Single-Camera ──
    # - FACE_CAMERA_CHILD=1 → หมายถึงถูก spawn จาก multi-camera __main__ ด้านล่าง
    # - api.py ก็ตั้ง FACE_CAMERA_CHILD=1 เพื่อป้องกัน recursive spawn
    if os.environ.get("FACE_CAMERA_CHILD") or not _cameras_list or len(_cameras_list) < 2:
        cam_name = os.environ.get("FACE_CAM_NAME", "CAM_MAIN")
        while True:
            try:
                run_camera(camera_index=1, camera_name=cam_name)
                break  # ออกตั้งใจ (q / ESC / TEST_MODE)
            except KeyboardInterrupt:
                print("\n[STOP] หยุดโดย Ctrl+C")
                break
            except Exception as _err:
                print(f"\n[CRASH] เกิดข้อผิดพลาด: {_err}")
                print("[RESTART] รีสตาร์ทใน 3 วินาที...")
                _time.sleep(3)

    else:
        # ── Multi-Camera Mode ─────────────────────────────────────────────────
        # เมื่อรัน python main.py → เปิดกล้องทุกตัวพร้อมกัน (subprocess แยกต่อกล้อง)
        import subprocess as _sp
        _base = os.path.dirname(os.path.abspath(__file__))
        _procs: list[tuple[str, "_sp.Popen"]] = []

        print(f"[MULTI-CAM] เปิด {len(_cameras_list)} กล้องพร้อมกัน")
        for _cam in _cameras_list:
            _env = os.environ.copy()
            _env["FACE_CAMERA_CHILD"]    = "1"               # ป้องกัน recursive spawn
            _env["FACE_HEADLESS"]        = "1"               # ไม่แสดง GUI (stream ผ่านไฟล์)
            _env["FACE_ALWAYS_ACTIVE"]   = "1"               # รัน 24/7 ไม่หยุดตาม Active Windows
            _env["CAMERA_URL"]           = str(_cam["source"])
            _env["FACE_CAM_NAME"]        = _cam.get("name", _cam["id"])
            _live_dir = os.path.join(_base, "live")
            os.makedirs(_live_dir, exist_ok=True)
            _env["FACE_LIVE_FRAME_PATH"] = os.path.join(_live_dir, f"live_frame_{_cam['id']}.jpg")
            _env["FACE_LIVE_STATE_PATH"] = os.path.join(_live_dir, f"live_state_{_cam['id']}.json")
            print(f"[MULTI-CAM]  {_cam['id']} → {_cam['source']}")
            _p = _sp.Popen([sys.executable, os.path.abspath(__file__)], cwd=_base, env=_env)
            _procs.append((_cam["id"], _p))

        print("[MULTI-CAM] กด Ctrl+C เพื่อหยุดทุกกล้อง")
        try:
            for _, _p in _procs:
                _p.wait()
        except KeyboardInterrupt:
            print("\n[STOP] หยุดทุกกล้อง...")
            for _, _p in _procs:
                _p.terminate()
            for _, _p in _procs:
                try:
                    _p.wait(timeout=5)
                except Exception:
                    _p.kill()