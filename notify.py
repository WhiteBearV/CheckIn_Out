"""
notify.py — ส่งแจ้งเตือนผ่าน Telegram Bot
ตัวแปรที่ต้องตั้งใน .env:
  TELEGRAM_BOT_TOKEN=<token>
  TELEGRAM_CHAT_ID=<chat_id>
"""

import os
import threading
import requests
from datetime import datetime

def _send(text: str, blocking: bool = False):
    """ส่งข้อความไป Telegram
    blocking=False (default) — spawn daemon thread ไม่บล็อก
    blocking=True — รอจนส่งเสร็จ (ใช้ตอน process กำลังจะตาย)
    """
    token   = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
    if not token or not chat_id:
        return

    def _do():
        try:
            requests.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"},
                timeout=5,
            )
        except Exception as e:
            print(f"[NOTIFY] ส่งไม่สำเร็จ: {e}")

    if blocking:
        _do()
    else:
        threading.Thread(target=_do, daemon=True).start()


def _now() -> str:
    return datetime.now().strftime("%d/%m/%Y %H:%M:%S")


# ─── Events ──────────────────────────────────────────────────────────────────

def server_startup():
    """แจ้งเตือนเมื่อ stream_server เริ่มทำงาน (npm run dev / systemd start)"""
    _send(f"🚀 <b>Server เริ่มทำงานแล้ว</b>\n🕐 {_now()}")


def server_shutdown():
    """แจ้งเตือนเมื่อ stream_server หยุดทำงาน — ส่ง blocking เพราะ process กำลังจะตาย"""
    token   = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
    if not token or not chat_id:
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id,
                  "text": f"🛑 <b>Server หยุดทำงานแล้ว</b>\n🕐 {_now()}",
                  "parse_mode": "HTML"},
            timeout=5,
        )
    except Exception as e:
        print(f"[NOTIFY] server_shutdown ส่งไม่สำเร็จ: {e}")


def attendance(status: str, per_id: str, name: str = None,
               organize_th: str = None, camera_name: str = None,
               check_time=None):
    """แจ้งเตือนเมื่อมีการ check-in / check-out"""
    icon   = "🟢" if status == "IN" else "🔴"
    action = "เข้างาน" if status == "IN" else "ออกงาน"
    parts  = [f"{icon} <b>{action}</b>"]

    display_name = name or per_id
    parts.append(f"👤 {display_name}")
    if organize_th:
        parts.append(f"🏢 {organize_th}")
    if camera_name:
        parts.append(f"📷 {camera_name}")

    if check_time:
        ts = check_time.strftime("%d/%m/%Y %H:%M:%S") if hasattr(check_time, 'strftime') else str(check_time)
    else:
        ts = _now()
    parts.append(f"🕐 {ts}")

    _send("\n".join(parts))


def system_start(started_by: str = ""):
    """แจ้งเตือนเมื่อระบบเริ่มทำงาน"""
    msg = f"✅ <b>ระบบเริ่มทำงานแล้ว</b>"
    if started_by:
        msg += f"\n👤 สั่งโดย: {started_by}"
    msg += f"\n🕐 {_now()}"
    _send(msg)


def system_stop(stopped_by: str = "", reason: str = "manual"):
    """แจ้งเตือนเมื่อระบบหยุดทำงาน
    reason='manual'     → ผู้ใช้กด Stop (async)
    reason='no_cameras' → ระบบหยุดอัตโนมัติ (blocking — กันข้อความหาย)
    """
    if reason == "no_cameras":
        msg = f"⛔ <b>ระบบหยุดอัตโนมัติ</b>\n📷 ไม่มีกล้องรันอยู่"
    else:
        msg = f"⛔ <b>ระบบหยุดทำงานแล้ว</b>"
        if stopped_by:
            msg += f"\n👤 สั่งโดย: {stopped_by}"
    msg += f"\n🕐 {_now()}"
    _send(msg, blocking=(reason == "no_cameras"))


def pg_down():
    """แจ้งเตือนเมื่อ PostgreSQL เชื่อมไม่ได้"""
    _send(f"⚠️ <b>PostgreSQL ไม่ตอบสนอง</b>\nระบบทำงาน offline mode\n🕐 {_now()}")


def pg_recovered():
    """แจ้งเตือนเมื่อ PostgreSQL กลับมา"""
    _send(f"✅ <b>PostgreSQL กลับมาแล้ว</b>\nกำลัง sync ข้อมูลที่ค้างไว้\n🕐 {_now()}")
