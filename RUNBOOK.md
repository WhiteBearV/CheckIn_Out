# FaceReg — RUNBOOK

คู่มือปฏิบัติการสำหรับดูแลระบบ Face Attendance

---

## สารบัญ
1. [ภาพรวมระบบ](#1-ภาพรวมระบบ)
2. [เริ่ม / หยุด ระบบ](#2-เริ่ม--หยุด-ระบบ)
3. [ตรวจสอบสถานะ](#3-ตรวจสอบสถานะ)
4. [จัดการผู้ใช้](#4-จัดการผู้ใช้)
5. [จัดการกล้อง](#5-จัดการกล้อง)
6. [Backup & Restore](#6-backup--restore)
7. [Log และ Monitoring](#7-log-และ-monitoring)
8. [แก้ปัญหาที่พบบ่อย](#8-แก้ปัญหาที่พบบ่อย)
9. [Scheduled Tasks](#9-scheduled-tasks)
10. [Port Reference](#10-port-reference)

---

## 1. ภาพรวมระบบ

```
┌─────────────────────────────────────────────────────┐
│  Web Browser  →  React UI (port 5173 dev / dist)    │
│       ↕                                             │
│  stream_server.py  (port 8001)  ← systemd watchdog  │
│       ↕ subprocess                                  │
│  main.py  (face recognition + camera loop)          │
│  api.py   (attendance REST API, port 8000)          │
│       ↕                                             │
│  PostgreSQL (face_attendance DB)                    │
│  SQLite offline_queue.db  (offline buffer)          │
└─────────────────────────────────────────────────────┘
```

**Services:**
| Service | หน้าที่ |
|---|---|
| `facereg-stream` | stream_server.py — entrypoint หลัก |
| `facereg-cleanup.timer` | ลบรูปเก่า ทุกคืน 02:00 |
| `facereg-backup.timer` | backup PostgreSQL ทุกคืน 03:00 |

---

## 2. เริ่ม / หยุด ระบบ

### วิธีปกติ (ผ่าน Web UI)
1. เปิด browser → `http://localhost:8001` หรือ IP เครื่อง
2. Login ด้วย admin
3. กดปุ่ม **START** เพื่อเริ่มระบบ / **STOP** เพื่อหยุด

### วิธี systemd (production)
```bash
# ดูสถานะ
sudo systemctl status facereg-stream

# เริ่ม / หยุด / restart
sudo systemctl start   facereg-stream
sudo systemctl stop    facereg-stream
sudo systemctl restart facereg-stream
```

### Development mode
```bash
cd /home/maeb/internship_work/FaceReg/front_end
npm run dev -- --host     # เปิดทั้ง stream_server + api + vite พร้อมกัน
```

---

## 3. ตรวจสอบสถานะ

### Health endpoints (ไม่ต้อง login)
```bash
curl http://localhost:8001/healthz        # liveness — ตอบ "ok"
curl http://localhost:8001/readyz         # readiness — JSON { ready, checks }
```

### Watchdog & system status
```bash
curl -H "Authorization: Bearer <token>" http://localhost:8001/system/watchdog
curl -H "Authorization: Bearer <token>" http://localhost:8001/system/offline
```

### ตรวจ offline queue
```bash
curl -H "Authorization: Bearer <token>" http://localhost:8001/system/offline
# ดู pending_count — ถ้า > 0 แปลว่ามี record รอ sync กับ PG
```

---

## 4. จัดการผู้ใช้

### ผ่าน Web UI
ไปที่ **จัดการผู้ใช้** ใน sidebar (เฉพาะ admin)
- เพิ่มผู้ใช้ใหม่ / รีเซ็ต password / ลบผู้ใช้

### ผ่าน command line
```bash
cd /home/maeb/internship_work/FaceReg

# เพิ่ม user
venv/bin/python manage_users.py add <username> <password> <admin|viewer>

# ลบ user
venv/bin/python manage_users.py delete <username>

# ดู user ทั้งหมด
venv/bin/python manage_users.py list

# รีเซ็ต password
venv/bin/python manage_users.py reset-password <username> <new_password>
```

### Default credentials (ต้องเปลี่ยนก่อน production)
| Username | Password เริ่มต้น | Role |
|---|---|---|
| admin | Admin12345 | admin |
| viewer | User12345 | viewer |

---

## 5. จัดการกล้อง

### ผ่าน Web UI
ไปที่ **กล้องสด** → กดไอคอนจัดการกล้อง หรือเปิด `http://localhost:8001/admin`

### ผ่าน cameras.json
```bash
# แก้ไฟล์โดยตรง
nano /home/maeb/internship_work/FaceReg/cameras.json

# reload กล้องโดยไม่ต้อง restart ระบบ
curl -X POST -H "Authorization: Bearer <token>" http://localhost:8001/cameras/reload
```

### รูปแบบ cameras.json
```json
[
  { "id": "cam1", "name": "ชื่อกล้อง", "index": 0, "flip": false },
  { "id": "cam2", "name": "IP Camera", "url": "rtsp://user:pass@192.168.x.x/...", "flip": false }
]
```

---

## 6. Backup & Restore

### Backup อัตโนมัติ
- รันทุกคืน **03:00** ผ่าน `facereg-backup.timer`
- เก็บที่ `backups/` แยกตาม daily / weekly / yearly

```bash
# ดู backup ที่มีอยู่
ls -lh /home/maeb/internship_work/FaceReg/backups/

# สั่ง backup ทันที
venv/bin/python backup_db.py
```

### Restore จาก backup
```bash
# แตกไฟล์ backup ที่ต้องการ
gunzip -c backups/2026-05-18_10-13-38_daily.sql.gz > restore.sql

# restore เข้า PostgreSQL
PGPASSWORD=1234 psql -h localhost -U face_user -d face_attendance -f restore.sql

# ลบไฟล์ชั่วคราว
rm restore.sql
```

---

## 7. Log และ Monitoring

### ดู log สด
```bash
# stream_server + main.py + api.py
journalctl -u facereg-stream -f

# cleanup timer
journalctl -u facereg-cleanup -f

# backup timer
journalctl -u facereg-backup -f

# ดู log ย้อนหลัง 200 บรรทัด
journalctl -u facereg-stream -n 200
```

### Audit log (ผ่าน API)
```bash
curl -H "Authorization: Bearer <token>" \
  "http://localhost:8001/audit/logs?limit=50"
```

### ขนาด journal
```bash
journalctl --disk-usage
# journal จะถูก rotate อัตโนมัติเมื่อเกิน 1 GB (config: /etc/systemd/journald.conf.d/facereg.conf)
```

---

## 8. แก้ปัญหาที่พบบ่อย

### ระบบไม่เริ่ม / กล้องไม่ขึ้น
```bash
# ตรวจ log
journalctl -u facereg-stream -n 50

# ตรวจว่า port ถูกใช้งานอยู่หรือเปล่า
ss -tlnp | grep -E "8001|8000"

# restart
sudo systemctl restart facereg-stream
```

### PostgreSQL เชื่อมไม่ได้
```bash
# ตรวจสถานะ PG
sudo systemctl status postgresql

# ทดสอบ connect
PGPASSWORD=1234 psql -h localhost -U face_user -d face_attendance -c "SELECT 1"

# ระบบจะ fallback ไป offline_queue อัตโนมัติ ดู pending_count ที่ /system/offline
```

### offline_queue มี pending record ค้าง
```bash
# ดูสถานะ queue
curl -H "Authorization: Bearer <token>" http://localhost:8001/system/offline

# sync worker จะ drain อัตโนมัติทุก 30 วินาที เมื่อ PG กลับมา
# ถ้าค้างนานเกินไป restart stream_server
sudo systemctl restart facereg-stream
```

### หน้า Web โหลดช้า / stream กระตุก
```bash
# ตรวจ CPU/RAM
htop

# ล้าง snapshot cache
curl -X POST -H "Authorization: Bearer <token>" http://localhost:8001/cache/clear
```

### ลืม admin password
```bash
cd /home/maeb/internship_work/FaceReg
venv/bin/python manage_users.py reset-password admin <new_password>
```

---

## 9. Scheduled Tasks

| Timer | เวลา | หน้าที่ |
|---|---|---|
| `facereg-cleanup.timer` | ทุกคืน 02:00 | ลบ PicSAVE >1 ปี, live_snap >7 วัน |
| `facereg-backup.timer` | ทุกคืน 03:00 | backup PostgreSQL (daily/weekly/yearly) |

```bash
# ดู timers ทั้งหมด
systemctl list-timers --no-pager

# รัน cleanup ทันที
venv/bin/python cleanup.py

# รัน backup ทันที
venv/bin/python backup_db.py
```

---

## 10. Port Reference

| Port | Service | หมายเหตุ |
|---|---|---|
| 8001 | stream_server.py | MJPEG stream, state API, auth, admin |
| 8000 | api.py | Attendance REST API |
| 5173 | Vite dev server | Development เท่านั้น |
| 5432 | PostgreSQL | DB หลัก |

---

---

## 11. Production — nginx + HTTPS

ใช้ nginx เป็น reverse proxy เปิดจาก internet หรือ local network (แนะนำสำหรับ production)

### ติดตั้ง nginx + ใช้ config ที่เตรียมไว้
```bash
sudo apt install nginx

# copy config
sudo cp deploy/nginx-facereg.conf /etc/nginx/sites-available/facereg
sudo ln -s /etc/nginx/sites-available/facereg /etc/nginx/sites-enabled/facereg
sudo rm -f /etc/nginx/sites-enabled/default

# ทดสอบ config + โหลดใหม่
sudo nginx -t && sudo systemctl reload nginx
```

### เปิด HTTPS ด้วย Let's Encrypt (ถ้ามี domain และเชื่อมต่อ internet)
```bash
sudo apt install certbot python3-certbot-nginx
sudo certbot --nginx -d <your-domain>
# certbot จะแก้ nginx config ให้อัตโนมัติ + ตั้ง cron ต่ออายุ cert
```

### เปลี่ยน CORS_ORIGINS หลังติดตั้ง nginx
```bash
# แก้ใน /etc/systemd/system/facereg-stream.service
# เพิ่ม: Environment=CORS_ORIGINS=http://192.168.1.x,https://your-domain.com
sudo systemctl daemon-reload && sudo systemctl restart facereg-stream
```

---

## 12. DB Schema Migrations

Schema ทั้งหมดรวมอยู่ใน `migrations/setup_db.sql` ไฟล์เดียว

```bash
# 1. สร้าง DB และ user
sudo -u postgres psql -c "CREATE USER face_user WITH PASSWORD '1234';"
sudo -u postgres psql -c "CREATE DATABASE face_attendance OWNER face_user;"

# 2. สร้าง schema + GRANT (ต้องรันด้วย postgres superuser)
sudo -u postgres psql -d face_attendance -f migrations/setup_db.sql
```

*อัปเดตล่าสุด: 2026-05-18*
