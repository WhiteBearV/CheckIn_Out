"""
main_pi5.py — Face Attendance (Pi5 Snapshot Mode)
==================================================
แทนที่จะ process ทุก frame → grab snapshot ทุก 1.5 วินาที
ลด CPU load ~90% เหมาะสำหรับ Raspberry Pi 5

State Machine:
  IDLE → (snap, detect, identify) → LIVENESS
  LIVENESS → (Texture + FAS ใน thread) → CHALLENGE หรือ FAILED
  CHALLENGE → (รอ user ชูนิ้ว → snap → MediaPipe) → SUCCESS หรือ FAILED
  SUCCESS / FAILED → (แสดง 3 วิ) → IDLE

รัน:
  python main_pi5.py           ← USB camera index 0
  python main_pi5.py 1         ← USB camera index 1
  CAMERA_URL=rtsp://... python main_pi5.py
"""

import os
import sys
import time
import random
import pickle
import threading
from datetime import datetime

import cv2
import numpy as np
from numpy.linalg import norm

# ─── เพิ่ม parent dir เข้า path เพื่อ import camera / api_client ──
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config_pi5 as cfg
from camera import ThreadedCamera
from liveness_lite import LivenessLite, FingerCheck
import ui_pi5 as ui

# ─── ถ้ามี session_manager / api_client ใน parent ───────────────
try:
    from session_manager import SessionManager
    _HAS_SESSION = True
except ImportError:
    _HAS_SESSION = False
    print("[WARN] ไม่พบ session_manager — ใช้ checkin stub")


# ─── States ─────────────────────────────────────────────────────
IDLE       = "IDLE"
LIVENESS   = "LIVENESS"
CHALLENGE  = "CHALLENGE"
SUCCESS    = "SUCCESS"
FAILED     = "FAILED"


# ─── Face Matching (cosine) ──────────────────────────────────────
def identify_face(embedding: np.ndarray, known_norms: np.ndarray,
                  known_names: list) -> str:
    if known_norms is None or len(known_norms) == 0:
        return "Unknown"
    emb_norm = embedding / (norm(embedding) + 1e-10)
    sims     = known_norms @ emb_norm
    best_idx = int(np.argmax(sims))
    if sims[best_idx] >= cfg.FACE_TOLERANCE:
        return known_names[best_idx]
    return "Unknown"


# ─── Load InsightFace ────────────────────────────────────────────
def load_insightface():
    import onnxruntime as ort
    from insightface.app import FaceAnalysis

    # Pi5: ใช้ CPU เท่านั้น — กำหนด thread count
    sess_opts = ort.SessionOptions()
    sess_opts.intra_op_num_threads = cfg.ONNX_THREADS
    sess_opts.inter_op_num_threads = 1

    app = FaceAnalysis(
        name=cfg.INSIGHTFACE_MODEL,
        providers=["CPUExecutionProvider"],
        allowed_modules=["detection", "recognition"],
    )
    app.prepare(ctx_id=-1, det_size=cfg.DET_SIZE)
    print(f"[ARCFACE] {cfg.INSIGHTFACE_MODEL}  det_size={cfg.DET_SIZE}  threads={cfg.ONNX_THREADS}")
    return app


# ─── Main ────────────────────────────────────────────────────────
def run(camera_index: int = 0, camera_name: str = "PI_CAM"):

    # ── โหลด encodings ──
    enc_path = os.path.join(os.path.dirname(__file__), cfg.ENCODINGS_FILE)
    if not os.path.exists(enc_path):
        raise FileNotFoundError(
            f"ไม่พบ {enc_path}\n"
            f"รัน encode_faces_arcface.py ก่อน"
        )
    with open(enc_path, "rb") as f:
        data = pickle.load(f)
    known_names = data["names"]
    _raw        = np.array(data["encodings"], dtype=np.float32)
    known_norms = _raw / (np.linalg.norm(_raw, axis=1, keepdims=True) + 1e-10)
    print(f"[DB] โหลด {len(known_names)} คน")

    # ── InsightFace ──
    app = load_insightface()

    # ── Camera ──
    cam_src = cfg.CAMERA_URL if cfg.CAMERA_URL else camera_index
    cam = ThreadedCamera(cam_src)
    print(f"[CAM] {cam.width}x{cam.height}")

    # ── Anti-Spoof ──
    liveness_engine = LivenessLite()
    finger_check    = FingerCheck()

    # ── Session ──
    session = SessionManager() if _HAS_SESSION else None

    # ── Window ──
    win = "Face Attendance — Pi5"
    cv2.namedWindow(win, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(win, 800, 480)

    # ════════════════════════════════════════════
    # ตัวแปร State Machine
    # ════════════════════════════════════════════
    state            = IDLE
    current_name     = ""
    current_display  = ""
    face_box_draw    = None       # (x1, y1, x2, y2) สำหรับวาด box

    # LIVENESS thread
    liveness_result  = None       # dict จาก LivenessLite.verify()
    liveness_done    = threading.Event()

    # CHALLENGE
    challenge_fingers  = 1
    challenge_start_ts = 0.0

    # SUCCESS/FAILED
    result_start_ts  = 0.0
    result_detail    = ""

    # Snapshot timer
    last_snap_ts     = 0.0

    # FPS
    fps_counter = 0
    fps_timer   = time.time()
    display_fps = 0.0

    print("=== Pi5 Snapshot Mode พร้อมใช้งาน ===")
    print(f"[CONFIG] Snapshot interval = {cfg.SNAPSHOT_INTERVAL_SEC}s")
    print(f"[CONFIG] Challenge wait    = {cfg.CHALLENGE_WAIT_SEC}s")
    print("กด Q หรือ ESC เพื่อออก")

    # ════════════════════════════════════════════
    # MAIN LOOP
    # ════════════════════════════════════════════
    while True:
        ret, frame = cam.read()
        if not ret or frame is None:
            time.sleep(0.05)
            continue
        if cfg.CAMERA_FLIP:
            frame = cv2.flip(frame, 1)

        now_ts = time.time()
        h, w   = frame.shape[:2]

        # ── FPS ──
        fps_counter += 1
        if now_ts - fps_timer >= 1.0:
            display_fps = fps_counter / (now_ts - fps_timer)
            fps_counter, fps_timer = 0, now_ts

        # ────────────────────────────────────────
        # STATE: IDLE
        # ────────────────────────────────────────
        if state == IDLE:
            ui.draw_idle(frame, display_fps)

            if now_ts - last_snap_ts >= cfg.SNAPSHOT_INTERVAL_SEC:
                last_snap_ts = now_ts
                snap = frame.copy()
                faces = app.get(snap)

                if faces:
                    face = faces[0]
                    x1, y1, x2, y2 = face.bbox.astype(int)
                    face_box_draw = (x1, y1, x2, y2)

                    # ตรวจว่าหน้าอยู่กลางภาพพอสมควร (in-oval approximation)
                    fcx = (x1 + x2) / 2.0
                    fcy = (y1 + y2) / 2.0
                    oval_cx, oval_cy = w // 2, int(h * 0.47)
                    oval_ew, oval_eh = int(h * 0.29), int(h * 0.34)
                    in_oval = (
                        ((fcx - oval_cx) / oval_ew) ** 2 +
                        ((fcy - oval_cy) / oval_eh) ** 2
                    ) <= 1.4

                    if not in_oval:
                        # วาด box แนะนำให้เข้าวงรี
                        ui.draw_face_box(frame, x1, y1, x2, y2, cfg.Color.UNKNOWN, "Move into oval")
                    else:
                        name = identify_face(face.embedding, known_norms, known_names)
                        if name != "Unknown":
                            # เตรียม face crop
                            pad  = 15
                            crop = snap[max(0, y1-pad):min(h, y2+pad),
                                        max(0, x1-pad):min(w, x2+pad)]

                            current_name    = name
                            current_display = name   # จะอัปเดตจาก API ถ้ามี session
                            if session:
                                now = datetime.fromtimestamp(now_ts)
                                person, _ = session.get_or_create(name, now, crop)
                                current_display = person.display_name

                            # ── เริ่ม liveness ใน background thread ──
                            liveness_result = None
                            liveness_done.clear()
                            face_snap = crop.copy()

                            def _run_liveness(fc):
                                nonlocal liveness_result
                                liveness_result = liveness_engine.verify(fc)
                                liveness_done.set()

                            threading.Thread(target=_run_liveness,
                                             args=(face_snap,), daemon=True).start()

                            state = LIVENESS
                            print(f"[DETECT] เจอ {current_display} → เริ่ม liveness")

        # ────────────────────────────────────────
        # STATE: LIVENESS
        # ────────────────────────────────────────
        elif state == LIVENESS:
            ui.draw_liveness(frame, current_display,
                             "กรุณารอสักครู่..." if not liveness_done.is_set() else "")
            if face_box_draw:
                ui.draw_face_box(frame, *face_box_draw, cfg.Color.LIVENESS, current_display)

            # ── timeout ──
            if now_ts - last_snap_ts > cfg.LIVENESS_TIMEOUT_SEC:
                state        = FAILED
                result_detail = "Timeout"
                result_start_ts = now_ts
                print(f"[LIVENESS] timeout → FAILED")

            # ── ได้ผลจาก thread ──
            elif liveness_done.is_set() and liveness_result is not None:
                r = liveness_result
                print(f"[LIVENESS] texture={r['texture_ok']}  "
                      f"fas={r['fas_ok']} ({r['fas_score']:.2f})")
                if r["passed"]:
                    challenge_fingers  = random.choice(cfg.CHALLENGE_FINGERS)
                    challenge_start_ts = now_ts
                    state = CHALLENGE
                    print(f"[CHALLENGE] ให้ชูนิ้ว {challenge_fingers}")
                else:
                    result_detail   = r["fail_reason"]
                    result_start_ts = now_ts
                    state = FAILED
                    print(f"[LIVENESS] FAILED: {result_detail}")

        # ────────────────────────────────────────
        # STATE: CHALLENGE
        # ────────────────────────────────────────
        elif state == CHALLENGE:
            elapsed   = now_ts - challenge_start_ts
            countdown = max(0.0, cfg.CHALLENGE_WAIT_SEC - elapsed)
            ui.draw_challenge(frame, challenge_fingers, countdown)

            if elapsed >= cfg.CHALLENGE_WAIT_SEC:
                # grab snapshot และตรวจนิ้ว
                passed, detected = finger_check.check(frame.copy(), challenge_fingers)
                print(f"[CHALLENGE] คาดหวัง={challenge_fingers}  เจอ={detected}  → {'PASS' if passed else 'FAIL'}")
                result_start_ts = now_ts
                if passed:
                    state = SUCCESS
                    # ── checkin ──
                    if session:
                        now_dt = datetime.fromtimestamp(now_ts)
                        session.try_checkin(current_name, camera_name)
                    print(f"[IN] {current_display} ✓")
                else:
                    result_detail = f"นิ้วไม่ตรง (เจอ {detected} นิ้ว)"
                    state = FAILED

        # ────────────────────────────────────────
        # STATE: SUCCESS / FAILED
        # ────────────────────────────────────────
        elif state in (SUCCESS, FAILED):
            elapsed   = now_ts - result_start_ts
            countdown = max(0.0, cfg.RESULT_DISPLAY_SEC - elapsed)
            ui.draw_result(
                frame,
                success  = (state == SUCCESS),
                name     = current_display,
                detail   = result_detail,
                countdown= countdown,
            )
            if elapsed >= cfg.RESULT_DISPLAY_SEC:
                state         = IDLE
                last_snap_ts  = now_ts   # reset timer → ไม่ snap ทันทีหลังกลับ IDLE
                face_box_draw = None
                result_detail = ""

        # ── HUD ──
        ui.draw_hud(frame, display_fps, state)

        cv2.imshow(win, frame)
        key = cv2.waitKey(1) & 0xFF
        if key in (ord("q"), 27):
            break
        elif key == ord("f"):
            prop = cv2.getWindowProperty(win, cv2.WND_PROP_FULLSCREEN)
            if prop == cv2.WINDOW_FULLSCREEN:
                cv2.setWindowProperty(win, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_NORMAL)
            else:
                cv2.setWindowProperty(win, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)

    # ── Cleanup ──
    if session:
        session.save_snapshots(save_root="../PicSAVE")
    finger_check.close()
    cam.release()
    cv2.destroyAllWindows()
    print("[EXIT] ปิดระบบเรียบร้อย")


# ════════════════════════════════════════════
if __name__ == "__main__":
    idx = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    run(camera_index=idx, camera_name="PI_CAM")
