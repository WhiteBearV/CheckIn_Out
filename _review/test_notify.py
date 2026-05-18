from dotenv import load_dotenv
load_dotenv()
import notify
import time

print("=== ทดสอบ Telegram Notify ===\n")

print("1. check-in...")
notify.attendance("IN", "1234567890", name="สมชาย ใจดี",
                  organize_th="ฝ่ายพัฒนาซอฟต์แวร์", camera_name="CAM_MAIN")
time.sleep(1)

print("2. check-out...")
notify.attendance("OUT", "1234567890", name="สมชาย ใจดี",
                  organize_th="ฝ่ายพัฒนาซอฟต์แวร์", camera_name="CAM_MAIN")
time.sleep(1)

print("3. system start...")
notify.system_start(started_by="admin")
time.sleep(1)

print("4. system stop...")
notify.system_stop(stopped_by="admin")
time.sleep(1)

print("5. PG down...")
notify.pg_down()
time.sleep(1)

print("6. PG recovered...")
notify.pg_recovered()
time.sleep(2)

print("\nส่งครบ 6 events ✅ — ตรวจสอบใน Telegram ได้เลย")
