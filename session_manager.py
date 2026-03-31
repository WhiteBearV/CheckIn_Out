"""
session_manager.py — จัดการ session ของพนักงาน
=================================================
ปรับใหม่: ใช้ employee_code (เลขบัตรประจำตัว) เป็น key
"""

from datetime import datetime
from attendance_db import get_employee_by_name, get_display_name, mark_attendance
from liveness_engine import LivenessEngine, LivenessState
import config as cfg


class PersonInfo:
    """ข้อมูลของคนหนึ่งคนในเซสชัน"""

    def __init__(self, name: str, now: datetime, snapshot=None):
        self.name          = name           # face_label (ชื่อโฟลเดอร์)
        self.employee_code = None           # เลขบัตรประจำตัว (จาก DB)
        self.display_name  = name           # ชื่อแสดงผล เช่น "นาย สมชาย ใจดี"
        self.title         = ""             # คำนำหน้า
        self.first_name    = ""
        self.last_name     = ""
        self.department    = ""             # แผนก (ถ้ามีในDB)
        self.first_seen       = now
        self.last_seen        = now
        self.last_detected_ts = now.timestamp()   # อัปเดตทุก detection (ใช้ตรวจ absence)
        self.snapshot         = snapshot.copy() if snapshot is not None and snapshot.size > 0 else None
        self.checked_in      = False
        self.checked_out     = False
        self.absence_reset   = False   # True เมื่อ absence reset → print log ครั้งเดียวตอน re-verify

    def update_last_detected(self, now_ts: float):
        """อัปเดตทุก detection — ใช้ตรวจ absence เท่านั้น"""
        self.last_detected_ts = now_ts

    def update_last_seen(self, now: datetime):
        """อัปเดตเฉพาะตอนผ่าน liveness — ใช้เป็นเวลา checkout"""
        self.last_seen        = now
        self.last_detected_ts = now.timestamp()

    def load_from_db(self, emp_row):
        """โหลดจาก DB row: (employee_code, title, first_name, last_name, face_label)"""
        if not emp_row:
            return
        self.employee_code = emp_row[0]
        self.title         = emp_row[1] or ""
        self.first_name    = emp_row[2] or ""
        self.last_name     = emp_row[3] or ""
        self.display_name  = get_display_name(emp_row)


class SessionManager:
    def __init__(self):
        self.persons: dict[str, PersonInfo]    = {}
        self.liveness: dict[str, LivenessState] = {}
        self.engine = LivenessEngine()

    def get_or_create(self, name: str, now: datetime, face_crop) -> tuple:
        now_ts = now.timestamp()
        if name not in self.persons:
            person = PersonInfo(name, now, face_crop)
            emp = get_employee_by_name(name)
            if emp:
                person.load_from_db(emp)
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
            # รองรับทั้งคนที่ยังไม่ได้ check-in และคนที่ checked-in แล้วแต่ fail หลัง absence reset
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

        if not person.employee_code:
            emp = get_employee_by_name(name)
            if emp:
                person.load_from_db(emp)
        if not person.employee_code:
            print(f"[WARN] ไม่พบ '{name}' ในฐานข้อมูล")
            return False

        try:
            mark_attendance(person.employee_code, "IN", camera_name,
                            check_time=person.first_seen)
            person.checked_in = True
            print(f"[IN] {person.display_name} ({person.employee_code})  "
                  f"time={person.first_seen.strftime('%H:%M:%S')}")
            return True
        except Exception as e:
            print(f"[IN ERROR] {name}: {e}")
            person.checked_in = True
            return False

    def confirm_presence(self, name: str, now: datetime):
        """เรียกเมื่อผ่าน liveness ซ้ำ (checked_in แล้ว) — อัปเดต last_seen เท่านั้น ไม่สร้าง record ใหม่"""
        if name not in self.persons:
            return
        p = self.persons[name]
        p.update_last_seen(now)
        if p.absence_reset:   # print เฉพาะครั้งแรกหลัง absence reset (ไม่สแปม)
            p.absence_reset = False
            print(f"[RE-VERIFY] {p.display_name} — ยืนยันตัวตนซ้ำ {now.strftime('%H:%M:%S')}")

    def do_checkout(self, camera_name: str, now: datetime) -> int:
        print(f"\n{'='*50}")
        print(f"[CHECKOUT] เวลา {now.strftime('%H:%M:%S')}")
        count = 0
        for name, person in self.persons.items():
            last = person.last_seen or now
            if not person.checked_in or person.checked_out:
                continue
            if not person.employee_code:
                emp = get_employee_by_name(name)
                if emp:
                    person.load_from_db(emp)
                else:
                    continue
            try:
                mark_attendance(person.employee_code, "OUT", camera_name,
                                check_time=last)
                person.checked_out = True
                count += 1
                print(f"  [{person.display_name}] OUT ({last.strftime('%H:%M:%S')})")
            except Exception as e:
                print(f"  [{name}] ERROR: {e}")
        print(f"[CHECKOUT] สำเร็จ {count} คน\n{'='*50}\n")
        return count