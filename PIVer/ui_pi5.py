"""
ui_pi5.py — UI สำหรับ Pi5 Snapshot Mode
=========================================
วาด overlay บน preview frame ตาม state ปัจจุบัน
ไม่มี panel ขวา / landmark / screen debug เพื่อประหยัด CPU
"""

import cv2
import numpy as np
import config_pi5 as cfg
from config_pi5 import Color as C

# ─── Thai font (ใช้ PIL เหมือน main version) ──
_font_cache   = {}
_font_path    = None
_font_searched = False


def _find_thai_font():
    global _font_path, _font_searched
    if _font_searched:
        return _font_path
    _font_searched = True
    import glob, os
    for pattern in [
        "/usr/share/fonts/truetype/thai/*.ttf",
        "/usr/share/fonts/truetype/tlwg/*.ttf",
        "/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf",
        "/usr/share/fonts/truetype/noto/NotoSansThai*.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "fonts/*.ttf", "*.ttf",
    ]:
        for path in sorted(glob.glob(pattern)):
            if os.path.isfile(path):
                _font_path = path
                return _font_path
    return None


def _get_font(size: int):
    if size in _font_cache:
        return _font_cache[size]
    path = _find_thai_font()
    if not path:
        return None
    try:
        from PIL import ImageFont
        font = ImageFont.truetype(path, size)
        _font_cache[size] = font
        return font
    except Exception:
        return None


def draw_text(img, text: str, pos: tuple, size: int = 18,
              color=C.TEXT, bold: bool = False):
    """วาดข้อความภาษาไทยผ่าน PIL (fallback → cv2 putText)"""
    font = _get_font(size)
    if font:
        try:
            from PIL import ImageDraw, Image
            pil  = Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
            draw = ImageDraw.Draw(pil)
            draw.text(pos, text, font=font, fill=(color[2], color[1], color[0]))
            img[:] = cv2.cvtColor(np.array(pil), cv2.COLOR_RGB2BGR)
            return
        except Exception:
            pass
    cv2.putText(img, text, pos, cv2.FONT_HERSHEY_SIMPLEX,
                size / 36.0, color, 1 + int(bold), cv2.LINE_AA)


# ─── Oval Guide ──────────────────────────────
def draw_oval_guide(frame: np.ndarray, color=C.OVAL_DEFAULT, thickness: int = 2):
    """วาดวงรีนำทาง"""
    h, w = frame.shape[:2]
    cx = w // 2
    cy = int(h * 0.47)
    ew = int(h * 0.29)
    eh = int(h * 0.34)
    cv2.ellipse(frame, (cx, cy), (ew, eh), 0, 0, 360, color, thickness)
    return cx, cy, ew, eh


def _dim_outside_oval(frame: np.ndarray, cx, cy, ew, eh, factor=0.4):
    """ทำให้พื้นที่นอกวงรีมืดลง"""
    mask = np.zeros(frame.shape[:2], dtype=np.uint8)
    cv2.ellipse(mask, (cx, cy), (ew, eh), 0, 0, 360, 255, -1)
    dark = (frame * factor).astype(np.uint8)
    frame[mask == 0] = dark[mask == 0]


# ─── State Overlays ──────────────────────────
def draw_idle(frame: np.ndarray, fps: float = 0.0):
    """State: IDLE — รอหน้า"""
    h, w = frame.shape[:2]
    cx, cy, ew, eh = draw_oval_guide(frame, C.OVAL_DEFAULT)
    _dim_outside_oval(frame, cx, cy, ew, eh)
    draw_text(frame, "วางหน้าในวงรี", (w // 2 - 90, cy + eh + 14), size=20, color=C.TEXT)
    if cfg.SHOW_FPS and fps > 0:
        draw_text(frame, f"FPS {fps:.1f}", (8, h - 10), size=14, color=C.TEXT_DIM)


def draw_liveness(frame: np.ndarray, name: str, progress_text: str = ""):
    """State: LIVENESS — กำลังตรวจสอบ"""
    h, w = frame.shape[:2]
    cx, cy, ew, eh = draw_oval_guide(frame, C.LIVENESS, thickness=3)
    _dim_outside_oval(frame, cx, cy, ew, eh, factor=0.35)
    draw_text(frame, f"กำลังตรวจสอบ: {name}", (20, 30), size=20, color=C.LIVENESS)
    if progress_text:
        draw_text(frame, progress_text, (w // 2 - 80, cy + eh + 14), size=18, color=C.LIVENESS)


def draw_challenge(frame: np.ndarray, expected_fingers: int, countdown: float):
    """State: CHALLENGE — ให้ชูนิ้ว"""
    h, w = frame.shape[:2]
    cx, cy, ew, eh = draw_oval_guide(frame, C.CHALLENGE, thickness=3)
    _dim_outside_oval(frame, cx, cy, ew, eh, factor=0.3)

    # Card กลางบน
    card_w, card_h = 320, 90
    card_x = w // 2 - card_w // 2
    card_y = cy - eh - card_h - 10
    cv2.rectangle(frame, (card_x, card_y), (card_x + card_w, card_y + card_h),
                  (30, 30, 30), -1)
    cv2.rectangle(frame, (card_x, card_y), (card_x + card_w, card_y + card_h),
                  C.CHALLENGE, 2)
    draw_text(frame, f"กรุณาชูนิ้ว  {expected_fingers}  นิ้ว",
              (card_x + 20, card_y + 12), size=22, color=C.CHALLENGE)
    draw_text(frame, f"ถ่ายภาพใน {countdown:.1f} วินาที",
              (card_x + 30, card_y + 52), size=16, color=C.TEXT)


def draw_result(frame: np.ndarray, success: bool, name: str,
                detail: str = "", countdown: float = 0.0):
    """State: SUCCESS / FAILED — แสดงผล"""
    h, w = frame.shape[:2]
    color  = C.OK if success else C.FAIL
    label  = "ลงเวลาสำเร็จ" if success else "ยืนยันตัวตนไม่สำเร็จ"
    emoji_text = f"✓  {name}" if success else f"✗  {detail or 'ล้มเหลว'}"

    # overlay สีอ่อน
    overlay = frame.copy()
    cv2.rectangle(overlay, (0, 0), (w, h), color, -1)
    cv2.addWeighted(overlay, 0.18, frame, 0.82, 0, frame)

    cx, cy, ew, eh = draw_oval_guide(frame, color, thickness=4)

    # Card กลาง
    card_w, card_h = 360, 100
    card_x = w // 2 - card_w // 2
    card_y = cy + eh + 15
    cv2.rectangle(frame, (card_x, card_y), (card_x + card_w, card_y + card_h),
                  (20, 20, 20), -1)
    cv2.rectangle(frame, (card_x, card_y), (card_x + card_w, card_y + card_h),
                  color, 2)
    draw_text(frame, label, (card_x + 20, card_y + 10), size=22, color=color)
    draw_text(frame, emoji_text, (card_x + 20, card_y + 50), size=18, color=C.TEXT)
    if countdown > 0:
        draw_text(frame, f"กลับสู่หน้าหลักใน {countdown:.0f}s",
                  (card_x + 30, card_y + 76), size=13, color=C.TEXT_DIM)


def draw_face_box(frame: np.ndarray, x1, y1, x2, y2, color, label: str = ""):
    """กรอบหน้าพร้อม label"""
    cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
    if label:
        (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.45, 1)
        cv2.rectangle(frame, (x1, y1 - th - 8), (x1 + tw + 6, y1), color, -1)
        cv2.putText(frame, label, (x1 + 3, y1 - 4),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 0), 1, cv2.LINE_AA)


def draw_hud(frame: np.ndarray, fps: float, state: str):
    """มุมขวาบน: FPS + state"""
    h, w = frame.shape[:2]
    state_color = {
        "IDLE":       C.TEXT_DIM,
        "LIVENESS":   C.LIVENESS,
        "CHALLENGE":  C.CHALLENGE,
        "SUCCESS":    C.OK,
        "FAILED":     C.FAIL,
    }.get(state, C.TEXT_DIM)
    if cfg.SHOW_FPS:
        draw_text(frame, f"{fps:.0f} FPS", (w - 80, 12), size=14, color=C.TEXT_DIM)
    draw_text(frame, state, (w - 120, 30), size=14, color=state_color)
