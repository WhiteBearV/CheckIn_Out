"""
liveness_lite.py — Anti-Spoofing แบบ stateless สำหรับ Snapshot Mode
=====================================================================
ทำงานบน single frame — ไม่ต้องการ video stream

ด่านที่ใช้:
  1. TextureCheck  — LBP + Laplacian + Chroma (single frame)
  2. FASCheck      — MiniFASNet ผ่าน DeepFace (single frame)
  3. FingerCheck   — MediaPipe Hands บน snapshot (static_image_mode=True)
"""

import cv2
import numpy as np
import mediapipe as mp
import config_pi5 as cfg


# ─────────────────────────────────────────────
# ด่าน 1: Texture (stateless)
# ─────────────────────────────────────────────
class TextureCheck:
    """ตรวจ micro-texture ผิวหนังบน single frame"""

    FACE_SIZE = 64

    def _lbp_variance(self, gray: np.ndarray) -> float:
        f = cv2.resize(gray, (self.FACE_SIZE, self.FACE_SIZE)).astype(np.int16)
        lbp = np.zeros_like(f, dtype=np.uint8)
        for i, (dy, dx) in enumerate([
            (-1,-1),(-1,0),(-1,1),(0,-1),(0,1),(1,-1),(1,0),(1,1)
        ]):
            shifted = np.roll(np.roll(f, dy, axis=0), dx, axis=1)
            lbp += ((shifted >= f).astype(np.uint8)) << i
        return float(np.std(lbp[1:-1, 1:-1].astype(np.float64)))

    def _laplacian_variance(self, gray: np.ndarray) -> float:
        face = cv2.resize(gray, (self.FACE_SIZE, self.FACE_SIZE))
        return float(np.var(cv2.Laplacian(face, cv2.CV_64F)))

    def _chroma_std(self, bgr: np.ndarray) -> float:
        face  = cv2.resize(bgr, (self.FACE_SIZE, self.FACE_SIZE))
        ycrcb = cv2.cvtColor(face, cv2.COLOR_BGR2YCrCb)
        cr = float(np.std(ycrcb[:, :, 1]))
        cb = float(np.std(ycrcb[:, :, 2]))
        return (cr + cb) / 2.0

    def check(self, face_crop_bgr: np.ndarray) -> tuple[bool, dict]:
        """
        Returns: (passed: bool, scores: dict)
        passed = True ถ้าผ่านอย่างน้อย 2/3 เกณฑ์
        """
        if face_crop_bgr is None or face_crop_bgr.shape[0] < 10:
            return False, {}
        gray = cv2.cvtColor(face_crop_bgr, cv2.COLOR_BGR2GRAY)
        lbp  = self._lbp_variance(gray)
        lap  = self._laplacian_variance(gray)
        chroma = self._chroma_std(face_crop_bgr)
        checks = [
            lbp    >= cfg.TEXTURE_LBP_MIN,
            lap    >= cfg.TEXTURE_LAP_MIN,
            chroma >= cfg.TEXTURE_CHROMA_MIN,
        ]
        passed = sum(checks) >= 2
        scores = {"lbp": round(lbp, 2), "lap": round(lap, 2), "chroma": round(chroma, 2)}
        return passed, scores


# ─────────────────────────────────────────────
# ด่าน 2: MiniFASNet (stateless)
# ─────────────────────────────────────────────
class FASCheck:
    """MiniFASNet ผ่าน DeepFace — lazy load ครั้งแรกเท่านั้น"""

    def __init__(self):
        self._deepface = None
        self._loaded   = False
        self._available = True

    def _ensure_loaded(self) -> bool:
        if self._loaded:
            return self._available
        self._loaded = True
        try:
            import os as _os
            _os.environ["CUDA_VISIBLE_DEVICES"] = "-1"   # force CPU สำหรับ DeepFace/torch

            try:
                import torch as _torch
                _orig_is_available = _torch.cuda.is_available
                _orig_torch_load   = _torch.load
                _torch.cuda.is_available = lambda: False
                def _cpu_load(*a, **kw):
                    kw.setdefault("map_location", "cpu")
                    return _orig_torch_load(*a, **kw)
                _torch.load = _cpu_load
                _patched = True
            except ImportError:
                _patched = False

            from deepface import DeepFace
            self._deepface = DeepFace

            # warm-up (download model ถ้ายังไม่มี)
            dummy = np.zeros((80, 80, 3), dtype=np.uint8)
            dummy[20:60, 20:60] = 128
            self._deepface.extract_faces(
                dummy, anti_spoofing=True,
                enforce_detection=False,
                detector_backend="skip",
            )
            print("[FAS] MiniFASNet โหลดสำเร็จ (CPU)")

            if _patched:
                _torch.cuda.is_available = _orig_is_available
                _torch.load = _orig_torch_load

            return True

        except ImportError:
            print("[FAS] WARNING: ไม่พบ deepface — pip install deepface tf-keras")
            self._available = False
            return False
        except Exception as e:
            print(f"[FAS] WARNING: โหลด model ไม่สำเร็จ: {e}")
            self._available = False
            return False

    def check(self, face_crop_bgr: np.ndarray) -> tuple[bool, float]:
        """
        Returns: (is_real: bool, score: float)
        ถ้า DeepFace ไม่พร้อม → คืน (True, -1.0) เพื่อไม่ block ระบบ
        """
        if not self._ensure_loaded():
            return True, -1.0
        if face_crop_bgr is None or face_crop_bgr.shape[0] < 30:
            return True, -1.0
        try:
            rgb = cv2.cvtColor(face_crop_bgr, cv2.COLOR_BGR2RGB)
            results = self._deepface.extract_faces(
                img_path=rgb,
                anti_spoofing=True,
                enforce_detection=False,
                detector_backend=cfg.FAS_DETECTOR_BACKEND,
            )
            if not results:
                return True, -1.0
            score   = results[0].get("antispoof_score", 0.0)
            is_real = results[0].get("is_real", score >= cfg.FAS_THRESHOLD)
            return bool(is_real), float(score)
        except Exception:
            return True, -1.0


# ─────────────────────────────────────────────
# ด่าน 3: Finger Challenge (snapshot-based)
# ─────────────────────────────────────────────
class FingerCheck:
    """ตรวจนับนิ้วจาก snapshot เดียว (static_image_mode=True)"""

    _mp_hands = mp.solutions.hands
    TIPS = [4, 8, 12, 16, 20]   # landmark index ปลายนิ้ว
    PIPS = [3, 6, 10, 14, 18]   # landmark index ข้อกลาง

    def __init__(self):
        self._hands = self._mp_hands.Hands(
            static_image_mode=True,    # snapshot — ไม่ใช้ tracking
            max_num_hands=1,
            min_detection_confidence=0.6,
        )

    def count_fingers(self, hand_lm, handedness: str = "Right") -> int:
        lm = hand_lm.landmark
        count = 0
        # นิ้วโป้ง (แนวนอน)
        tip, ip = lm[self.TIPS[0]], lm[self.PIPS[0]]
        count += int(tip.x < ip.x) if handedness == "Right" else int(tip.x > ip.x)
        # นิ้วชี้–ก้อย (แนวตั้ง)
        for i in range(1, 5):
            if lm[self.TIPS[i]].y < lm[self.PIPS[i]].y:
                count += 1
        return count

    def check(self, frame_bgr: np.ndarray, expected: int) -> tuple[bool, int]:
        """
        Args:
            frame_bgr: ภาพเต็ม frame (ไม่ใช่แค่ crop)
            expected:  จำนวนนิ้วที่คาดหวัง

        Returns: (passed: bool, detected_count: int)
        """
        rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        result = self._hands.process(rgb)
        if not result.multi_hand_landmarks:
            return False, 0

        # ใช้มือแรกที่เจอ
        hand_lm = result.multi_hand_landmarks[0]
        handedness = "Right"
        if result.multi_handedness:
            handedness = result.multi_handedness[0].classification[0].label

        detected = self.count_fingers(hand_lm, handedness)
        return detected == expected, detected

    def close(self):
        self._hands.close()


# ─────────────────────────────────────────────
# Pipeline รวม — ใช้ใน main_pi5.py
# ─────────────────────────────────────────────
class LivenessLite:
    """
    รัน Texture + FAS บน face crop
    ใช้ในรูปแบบ background thread (ใช้เวลา ~300-500ms บน Pi5)
    """

    def __init__(self):
        self.texture = TextureCheck()
        self.fas     = FASCheck()

    def verify(self, face_crop_bgr: np.ndarray) -> dict:
        """
        Returns:
            {
                "passed": bool,
                "texture_ok": bool,
                "fas_ok": bool,
                "fas_score": float,
                "texture_scores": dict,
                "fail_reason": str,
            }
        """
        texture_ok, tex_scores = self.texture.check(face_crop_bgr)
        fas_ok, fas_score      = self.fas.check(face_crop_bgr)

        fail_reason = ""
        if not texture_ok:
            fail_reason = "Texture fail"
        elif not fas_ok:
            fail_reason = f"FAS fail ({fas_score:.2f})"

        return {
            "passed":         texture_ok and fas_ok,
            "texture_ok":     texture_ok,
            "fas_ok":         fas_ok,
            "fas_score":      fas_score,
            "texture_scores": tex_scores,
            "fail_reason":    fail_reason,
        }
