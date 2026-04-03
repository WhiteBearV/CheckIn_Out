"""
config_pi5.py — ค่าตั้งสำหรับ Raspberry Pi 5 (Snapshot Mode)
=============================================================
เบากว่า config.py หลักมาก:
  - buffalo_sc (MobileNet) แทน buffalo_l (ResNet50)
  - DET_SIZE เล็กลง
  - ปิดด่านที่ต้องการ video stream (Depth/Motion/Blink/Screen)
  - Snapshot ทุก 1.5 วินาที แทนการประมวลผลทุก frame
"""
import os
from dotenv import load_dotenv
from datetime import time as dtime

load_dotenv()

# ─── ArcFace / Recognition ──────────────────────
ENCODINGS_FILE  = "../encodings.pkl"   # ใช้ไฟล์เดียวกับ main version
FACE_TOLERANCE  = 0.35
INSIGHTFACE_MODEL = "buffalo_sc"       # MobileNet — เบากว่า buffalo_l มาก
DET_SIZE        = (160, 160)           # เล็กพอสำหรับ Pi5 CPU
ONNX_THREADS    = 4                    # ใช้ครบทั้ง 4 cores ของ Pi5

# ─── Camera ────────────────────────────────────
CAMERA_URL      = os.environ.get("CAMERA_URL", "")
USB_CAM_WIDTH   = 640
USB_CAM_HEIGHT  = 480
CAMERA_FLIP     = False

# ─── Snapshot Mode ─────────────────────────────
SNAPSHOT_INTERVAL_SEC  = 1.5    # grab snapshot ทุก N วินาที (idle → ตรวจหน้า)
CHALLENGE_WAIT_SEC     = 3.0    # รอ user จัดนิ้ว หลังแสดง prompt
RESULT_DISPLAY_SEC     = 3.0    # แสดงผล SUCCESS/FAILED ก่อนกลับ IDLE
LIVENESS_TIMEOUT_SEC   = 15.0   # รวม timeout ทั้ง verify + challenge

# ─── Anti-Spoofing: เปิดเฉพาะที่ทำงานบน single frame ─
TEXTURE_ENABLED   = True
TEXTURE_LBP_MIN   = 3.5
TEXTURE_LAP_MIN   = 15.0
TEXTURE_CHROMA_MIN = 6.0

FAS_ENABLED       = True
FAS_THRESHOLD     = 0.50         # ลดจาก 0.90 → รองรับ CPU inference ที่ score อาจต่างกว่า GPU
FAS_DETECTOR_BACKEND = "skip"

CHALLENGE_ENABLED  = True
CHALLENGE_FINGERS  = list(range(1, 6))   # สุ่มจาก 1-5 นิ้ว

# ─── ปิดด่านที่ต้องการ video stream ─────────────
BLINK_ENABLED          = False
DEPTH_ENABLED          = False
MOTION_ENABLED         = False
SCREEN_DETECT_ENABLED  = False

# ─── Session / Attendance ───────────────────────
ABSENCE_TIMEOUT_SEC    = 60      # Pi5: ใช้ค่าสูงกว่าเพราะ snapshot ไม่ได้ detect ต่อเนื่อง
CHECKOUT_TIME          = dtime(22, 0)
ACTIVE_WINDOWS = [
    (dtime(5, 0), dtime(22, 0)),
]

# ─── UI ────────────────────────────────────────
PANEL_WIDTH     = 220
FULLSCREEN      = False          # Pi5: ไม่บังคับ fullscreen ตั้งแต่ต้น
SHOW_FPS        = True

# ─── สี (BGR) ───────────────────────────────────
def _hex(h):
    h = h.lstrip("#")
    return (int(h[4:6], 16), int(h[2:4], 16), int(h[0:2], 16))

class Color:
    UNKNOWN       = _hex("#FF3333")
    LIVENESS      = _hex("#FFD700")
    LIVENESS_FAIL = _hex("#FF6600")
    CHECKED_IN    = _hex("#00DC00")
    CHALLENGE     = _hex("#FF00FF")
    OK            = _hex("#00FF99")
    FAIL          = _hex("#FF4444")
    PANEL_BG      = _hex("#1C1C1C")
    TEXT          = _hex("#FFFFFF")
    TEXT_DIM      = _hex("#969696")
    OVAL_DEFAULT  = (210, 210, 210)
