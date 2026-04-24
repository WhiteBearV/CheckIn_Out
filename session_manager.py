"""
session_manager.py — จัดการ session ของพนักงาน
=================================================
face_label = per_id (เลข 13 หลัก = ชื่อโฟลเดอร์ใน known_faces/)
ข้อมูลพนักงาน (ชื่อ/หน่วยงาน) ดึงจาก external API ผ่าน api_client
"""

import os
import time
import cv2
from datetime import datetime
from api_client import fetch_person_by_pid, get_display_name, mark_attendance, mask_pid
from liveness_engine import LivenessEngine, LivenessState
import config as cfg


class PersonInfo:
    """ข้อมูลของคนหนึ่งคนในเซสชัน"""

    def __init__(self, per_id: str, now: datetime, snapshot=None):
        self.per_id        = per_id         # เลข 13 หลัก (= face_label = ชื่อโฟลเดอร์)
        self.name          = per_id         # alias — ใช้เป็น key ใน session dict
        self.display_name  = per_id         # ชื่อแสดงผล เช่น "ร.ต. วีรภัทร สวัดดี"
        self.api_name      = ""             # ชื่อเต็มจาก API เช่น "ร้อยตรี วีรภัทร สวัดดี"
        self.prename_th    = ""             # คำนำหน้าเต็ม
        self.per_name      = ""             # ชื่อ
        self.per_surname   = ""             # นามสกุล
        self.posname_th    = ""             # ตำแหน่ง
        self.organize_th   = ""             # หน่วยงาน
        self.organize_id   = ""             # รหัสหน่วยงาน
        self.first_seen       = now
        self.last_seen        = now
        self.last_detected_ts = now.timestamp()
        self.snapshot         = snapshot.copy() if snapshot is not None and snapshot.size > 0 else None
        self.snapshot_out     = None  # อัปเดตทุกครั้งที่เจอหลัง check-in → รูปล่าสุด
        self.checked_in      = False
        self.checked_out     = False
        self.absence_reset   = False   # True เมื่อ absence reset → print log ครั้งเดียวตอน re-verify
        self.is_out_cam      = False   # True เมื่อ DB ตอบว่า IN แล้ว (มาจากกล้องอื่น) → กล้องนี้คือฝั่ง OUT
        # N-cam safe: save ไฟล์ตาม "ผลจริงที่ DB ยอมรับ" — กล้องที่ชนะ race เท่านั้นที่เซฟ
        self.in_success      = False   # True เมื่อ try_checkin ที่กล้องนี้ mark IN สำเร็จใน DB
        self.out_success     = False   # True เมื่อ do_checkout ที่กล้องนี้ mark OUT สำเร็จใน DB

    def update_last_detected(self, now_ts: float):
        """อัปเดตทุก detection — ใช้ตรวจ absence เท่านั้น"""
        self.last_detected_ts = now_ts

    def update_last_seen(self, now: datetime):
        """อัปเดตเฉพาะตอนผ่าน liveness — ใช้เป็นเวลา checkout"""
        self.last_seen        = now
        self.last_detected_ts = now.timestamp()

    def load_from_api(self, person_dict: dict):
        """โหลดจาก dict ที่ได้จาก fetch_person_by_pid()"""
        if not person_dict:
            return
        self.display_name = get_display_name(person_dict)
        self.api_name     = person_dict.get("name", "")
        self.prename_th   = person_dict.get("prename_th", "")
        self.per_name     = person_dict.get("per_name", "")
        self.per_surname  = person_dict.get("per_surname", "")
        self.posname_th   = person_dict.get("posname_th", "")
        self.organize_th  = person_dict.get("organize_th", "")
        self.organize_id  = person_dict.get("organize_id", "")


class SessionManager:
    def __init__(self):
        self.persons: dict[str, PersonInfo]    = {}
        self.liveness: dict[str, LivenessState] = {}
        self.engine = LivenessEngine()

    def get_or_create(self, name: str, now: datetime, face_crop) -> tuple:
        now_ts = now.timestamp()
        if name not in self.persons:
            person = PersonInfo(name, now, face_crop)
            data = fetch_person_by_pid(name)
            if data:
                person.load_from_api(data)
            self.persons[name] = person
        else:
            person = self.persons[name]
            person.update_last_detected(now.timestamp())   # ทุก detection
            # last_seen อัปเดตเฉพาะตอน confirmed → ป้องกัน proxy update ก่อนผ่าน liveness
            lv = self.liveness.get(name)
            if lv and lv.confirmed:
                person.last_seen = now

        if name in self.liveness:
            lv = self.liveness[name]
            if lv.failed and not self.persons[name].checked_in:
                if now_ts - lv.start_ts > cfg.LIVENESS_TIMEOUT + cfg.LIVENESS_RETRY_AFTER:
                    print(f"[RETRY] {name}")
                    del self.liveness[name]
                    self.persons[name].first_seen = now

        if name not in self.liveness:
            self.liveness[name] = self.engine.create_state(now_ts)

        return self.persons[name], self.liveness[name]

    def cleanup_expired(self, now_ts: float):
        for name in list(self.liveness.keys()):
            lv     = self.liveness[name]
            person = self.persons.get(name)

            # ── reset liveness ที่ failed ──
            if (lv.failed
                    and now_ts - lv.start_ts > cfg.LIVENESS_TIMEOUT + cfg.LIVENESS_RETRY_AFTER):
                tag = "RETRY" if not person or not person.checked_in else "RE-VERIFY RETRY"
                print(f"[{tag}] {name} — reset liveness")
                self.liveness[name] = self.engine.create_state(now_ts)

            # ── absence reset: checked-in แต่ไม่เจอใบหน้านานเกิน ABSENCE_TIMEOUT_SEC ──
            elif (person and person.checked_in and not person.checked_out
                  and lv.confirmed
                  and now_ts - person.last_detected_ts > cfg.ABSENCE_TIMEOUT_SEC):
                print(f"[ABSENCE] {person.display_name} — ไม่พบใบหน้า {cfg.ABSENCE_TIMEOUT_SEC}s → ต้องสแกนใหม่")
                self.liveness[name]  = self.engine.create_state(now_ts)
                person.absence_reset = True

    def try_checkin(self, name: str, camera_name: str) -> bool:
        person = self.persons.get(name)
        lv     = self.liveness.get(name)
        if not person or not lv:
            return False
        if not lv.confirmed or person.checked_in:
            return False

        try:
            ok, reason = mark_attendance(
                person.per_id, "IN", camera_name,
                check_time=person.first_seen,
                name=person.api_name,
                prename_th=person.prename_th,
                per_name=person.per_name,
                per_surname=person.per_surname,
                posname_th=person.posname_th,
                organize_th=person.organize_th,
                organize_id=person.organize_id,
            )
            person.checked_in = True
            if ok:
                person.in_success = True   # ← กล้องนี้คือ "กล้อง IN จริง" (ชนะ race)
                print(f"[IN] {person.display_name} ({person.per_id})  "
                      f"time={person.first_seen.strftime('%H:%M:%S')}")
            elif "IN แล้ว" in reason:
                # DB ปฏิเสธเพราะ IN จากกล้องอื่นแล้ว → กล้องนี้เป็นฝั่ง OUT
                # ย้าย snapshot → snapshot_out ให้ save_snapshots เซฟเป็น _OUT.jpg
                person.is_out_cam   = True
                person.snapshot_out = person.snapshot
                person.snapshot     = None
                print(f"[SEEN-AGAIN] {person.display_name} ที่ {camera_name} — "
                      f"IN แล้วจากกล้องอื่น (กล้องนี้เป็นฝั่ง OUT)")
            else:
                # network/server error — เก็บเป็น IN ไว้ก่อน (เผื่อ retry ได้ในรอบหน้า)
                print(f"[IN FAIL] {person.display_name} — {reason or 'unknown'}")
            return True
        except Exception as e:
            print(f"[IN ERROR] {name}: {e}")
            person.checked_in = True
            return False

    def confirm_presence(self, name: str, now: datetime):
        """เรียกเมื่อผ่าน liveness ซ้ำ (checked_in แล้ว) — อัปเดต last_seen เท่านั้น"""
        if name not in self.persons:
            return
        p = self.persons[name]
        p.update_last_seen(now)
        if p.absence_reset:   # print เฉพาะครั้งแรกหลัง absence reset (ไม่สแปม)
            p.absence_reset = False
            print(f"[RE-VERIFY] {p.display_name} — ยืนยันตัวตนซ้ำ {now.strftime('%H:%M:%S')}")

    def do_checkout(self, camera_name: str, now: datetime) -> int:
        print(f"\n{'='*50}")
        print(f"[CHECKOUT] เวลา {now.strftime('%H:%M:%S')} @ {camera_name}")
        count = 0
        now_ts = now.timestamp()
        for name, person in self.persons.items():
            last = person.last_seen or now
            if not person.checked_in or person.checked_out:
                continue

            # N-cam race-resolver: หน่วงตามเวลาที่กล้องนี้ "ไม่ได้เจอ" คนนี้
            #   กล้องที่เจอล่าสุด (stale 0) → sleep 0  → ชนะ race DB
            #   กล้องที่ไม่เจอมานาน     → sleep สูง → แพ้ race → DB ปฏิเสธ
            # ผลคือ DB ได้เวลา OUT จากกล้องที่เจอคนนี้ล่าสุดจริง ๆ
            # ตัวหาร 1800 (ครึ่ง ชม.): 1h→2s, 5h→10s, 10h→20s, 17h (กะเต็ม)→34s
            # cap 60s เพียงพอแยก race ในกรณี IN เช้า-OUT เย็น (9 ชม.ห่าง = 18s diff)
            stale_sec = max(0.0, now_ts - person.last_detected_ts)
            delay     = min(stale_sec / 1800.0, 60.0)
            if delay > 0.05:
                time.sleep(delay)
            try:
                ok, reason = mark_attendance(
                    person.per_id, "OUT", camera_name,
                    check_time=last,
                    name=person.api_name,
                    prename_th=person.prename_th,
                    per_name=person.per_name,
                    per_surname=person.per_surname,
                    posname_th=person.posname_th,
                    organize_th=person.organize_th,
                    organize_id=person.organize_id,
                )
                person.checked_out = True
                if ok:
                    person.out_success = True  # ← กล้องนี้ชนะ race → เป็น "กล้อง OUT จริง"
                    count += 1
                    print(f"  [{person.display_name}] OUT ({last.strftime('%H:%M:%S')})")
                else:
                    # DB ปฏิเสธ (กล้องอื่น OUT ไปแล้ว หรือ error) → ไม่ save _OUT.jpg จากกล้องนี้
                    print(f"  [{person.display_name}] OUT skipped: {reason or 'already OUT elsewhere'}")
            except Exception as e:
                print(f"  [{name}] ERROR: {e}")
        print(f"[CHECKOUT] สำเร็จ {count} คน\n{'='*50}\n")
        return count

    def save_snapshots(self, save_root: str = None) -> int:
        """
        บันทึก snapshot ของทุกคนลง PicSAVE/YYYY/MM/DD/
          - HH-MM-SS_{masked_pid}_IN.jpg   รูปตอน check-in
          - HH-MM-SS_{masked_pid}_OUT.jpg  รูปล่าสุดที่เจอ (มีเฉพาะถ้าเจอหลัง check-in)
        ชื่อไฟล์ใช้ mask_pid (4 ตัวท้าย) เพื่อไม่รั่วเลข 13 หลักทางชื่อไฟล์
        ใช้วันที่ check-in (first_seen) เป็นชื่อโฟลเดอร์เสมอ
        """
        if save_root is None:
            save_root = cfg.SNAPSHOT_SAVE_ROOT
        saved = 0
        for person in self.persons.values():
            if not person.checked_in:
                continue
            in_dt  = person.first_seen or datetime.now()
            out_dt = person.last_seen  or in_dt

            folder = os.path.join(
                save_root,
                in_dt.strftime("%Y"),
                in_dt.strftime("%m"),
                in_dt.strftime("%d"),
            )
            os.makedirs(folder, exist_ok=True)

            mpid = mask_pid(person.per_id)

            # N-cam safe: save เฉพาะกล้องที่ชนะ race DB เท่านั้น
            #   _IN.jpg  → เฉพาะกล้องที่ in_success (try_checkin สำเร็จ)
            #   _OUT.jpg → เฉพาะกล้องที่ out_success (do_checkout สำเร็จ)
            # กล้องกลาง (ไม่ได้ทั้ง IN ทั้ง OUT) ไม่เซฟอะไรเลย

            # รูป IN
            if (person.in_success
                    and person.snapshot is not None and person.snapshot.size > 0):
                path = os.path.join(folder, f"{in_dt.strftime('%H-%M-%S')}_{mpid}_IN.jpg")
                cv2.imwrite(path, person.snapshot)
                print(f"[SAVE] {path}")
                saved += 1

            # รูป OUT
            if (person.out_success
                    and person.snapshot_out is not None and person.snapshot_out.size > 0):
                path = os.path.join(folder, f"{out_dt.strftime('%H-%M-%S')}_{mpid}_OUT.jpg")
                cv2.imwrite(path, person.snapshot_out)
                print(f"[SAVE] {path}")
                saved += 1

        print(f"[SAVE] บันทึกรูปทั้งหมด {saved} รูป → {save_root}/")
        return saved
