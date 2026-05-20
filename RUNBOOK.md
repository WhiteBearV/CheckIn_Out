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
11. [Production — nginx + HTTPS](#11-production--nginx--https)
12. [DB Schema Migrations](#12-db-schema-migrations)
13. [Network Requirements (สำหรับทีม Network)](#13-network-requirements-สำหรับทีม-network)

---

## 1. ภาพรวมระบบ

### 1.1 System Requirements

| Component | Minimum | Recommended | หมายเหตุ |
|---|---|---|---|
| **OS** | Ubuntu 22.04 LTS | Ubuntu 24.04 LTS | Debian 12+ ก็ใช้ได้ |
| **Python** | 3.10 | 3.12 | ต้องมี `python3-venv` |
| **PostgreSQL** | 14 | 16 | สำหรับ JSONB + indexes |
| **Node.js** | 18 LTS | 20 LTS | สำหรับ build frontend (ใช้ครั้งเดียว) |
| **CPU** | 4 cores | 8 cores | x86_64 |
| **RAM** | 8 GB | 16 GB+ | InsightFace ใช้ ~2 GB/cam |
| **GPU** | (CPU mode ได้) | NVIDIA + CUDA 11/12 | เร็วกว่า CPU 5-10x |
| **Disk** | 20 GB | 100 GB+ SSD | PicSAVE เก็บ 365 วัน → โต ~10-50 GB/ปี |
| **Network** | 100 Mbps | 1 Gbps | RTSP cam 1080p ใช้ ~4 Mbps/ตัว |

### 1.2 Architecture

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

### 1.3 Dependencies ที่ต้อง apt install ก่อน

```bash
sudo apt update && sudo apt install -y \
    python3 python3-venv python3-pip \
    postgresql postgresql-contrib \
    nginx certbot python3-certbot-nginx \
    nodejs npm \
    ffmpeg libsm6 libxext6 libgl1 \
    git curl
```

> **GPU mode:** ติดตั้ง NVIDIA driver + CUDA toolkit แยกตาม OS — ดู https://developer.nvidia.com/cuda-downloads

---

## 2. เริ่ม / หยุด ระบบ

### วิธีปกติ (ผ่าน Web UI)
1. เปิด browser → `http://localhost:8001` หรือ IP เครื่อง
2. Login ด้วย admin
3. กดปุ่ม **START** เพื่อเริ่มระบบ / **STOP** เพื่อหยุด

### วิธี systemd (production)

> ติดตั้ง systemd services ครั้งแรกด้วย `sudo bash deploy/install_service.sh` (ดู [ม.11.0](#110-ติดตั้ง-systemd-services-ก่อนทำอย่างอื่น))

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

### 11.0 ติดตั้ง systemd services (ก่อนทำอย่างอื่น)

ใช้ `install_service.sh` ติดตั้ง systemd units ครบทั้ง 5 ตัวในคำสั่งเดียว:
- `facereg-stream.service` — main entrypoint (FastAPI + spawn main.py/api.py)
- `facereg-backup.service` + `.timer` — backup DB ทุกคืน 03:00
- `facereg-cleanup.service` + `.timer` — ลบรูปเก่าทุกคืน 02:00
- `journald-facereg.conf` — log rotation (1 GB / 30 วัน)

```bash
# วิธีปกติ — auto-detect path ของ repo + user ปัจจุบัน
sudo bash deploy/install_service.sh
```

Script จะ:
1. ตรวจว่ามี `venv/bin/python` พร้อม → ถ้าไม่มีจะ error บอกให้สร้าง venv ก่อน
2. ตรวจว่า user มีอยู่จริงใน system
3. ใช้ `sed` substitute hardcoded path (`/home/maeb/internship_work/FaceReg`) + user (`maeb`) ในไฟล์ `.service` ทุกตัว → ใช้ค่าจริงตอน install
4. Copy ไป `/etc/systemd/system/` + `chmod 644`
5. `systemctl daemon-reload` + `enable --now`
6. Print สรุปการใช้งาน

#### Override path / user (สำหรับ custom location)

ถ้าติดตั้งที่ path อื่น หรือต้องการให้ service รันด้วย user เฉพาะ:

```bash
# ตัวอย่าง: deploy ที่ /opt/facereg ใช้ user facereg
sudo FACEREG_DIR=/opt/facereg FACEREG_USER=facereg \
     bash deploy/install_service.sh
```

**Env vars ที่ override ได้:**

| Variable | Default | คำอธิบาย |
|---|---|---|
| `FACEREG_DIR` | auto-detect (script's parent) | path เต็มของ repo บน server |
| `FACEREG_USER` | `$SUDO_USER` | user ที่ service จะรันด้วย (group = primary group ของ user) |

#### หลัง install เสร็จ

```bash
# 1. ตรวจสถานะ
sudo systemctl status facereg-stream
systemctl list-timers --no-pager | grep facereg

# 2. ตั้ง env vars สำคัญ (อ่าน .env.example ก่อน)
sudo systemctl edit facereg-stream
# เพิ่ม:
#   [Service]
#   Environment=INTERNAL_PUSH_TOKEN=<random_64_hex>
#   Environment=JWT_SECRET=<random_64_hex>
#   Environment=CORS_ORIGINS=https://your-domain.com
#   Environment=TELEGRAM_BOT_TOKEN=<optional>

# 3. apply changes
sudo systemctl daemon-reload
sudo systemctl restart facereg-stream

# 4. ดู log ทันที
journalctl -u facereg-stream -f
```

#### Uninstall (ถ้าต้องการลบ)
```bash
sudo systemctl disable --now facereg-stream facereg-backup.timer facereg-cleanup.timer
sudo rm /etc/systemd/system/facereg-{stream,backup,cleanup}.{service,timer}
sudo rm /etc/systemd/journald.conf.d/facereg.conf
sudo systemctl daemon-reload
sudo systemctl restart systemd-journald
```

---

### 11.1 ติดตั้ง nginx + ใช้ config ที่เตรียมไว้

⚠ **สำคัญ:** `nginx-facereg.conf` มี `root /home/maeb/internship_work/FaceReg/front_end/dist;` hardcoded
ต้อง substitute เป็น path จริงของ repo บน server ก่อน

```bash
sudo apt install nginx

# 1. substitute path ให้ตรงกับ repo บน server
FACEREG_DIR="/path/to/FaceReg"   # ← แก้ตรงนี้ให้ตรงกับของจริง
sudo sed "s|/home/maeb/internship_work/FaceReg|$FACEREG_DIR|g" \
     deploy/nginx-facereg.conf > /tmp/facereg.conf

# 2. copy ไป sites-available
sudo mv /tmp/facereg.conf /etc/nginx/sites-available/facereg
sudo ln -sf /etc/nginx/sites-available/facereg /etc/nginx/sites-enabled/facereg
sudo rm -f /etc/nginx/sites-enabled/default

# 3. ทดสอบ config + โหลดใหม่
sudo nginx -t && sudo systemctl reload nginx
```

### 11.2 เปิด HTTPS ด้วย Let's Encrypt (ถ้ามี domain และเชื่อมต่อ internet)
```bash
sudo apt install certbot python3-certbot-nginx
sudo certbot --nginx -d <your-domain>
# certbot จะแก้ nginx config ให้อัตโนมัติ + ตั้ง cron ต่ออายุ cert
```

### 11.3 เปลี่ยน CORS_ORIGINS หลังติดตั้ง nginx
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

---

## 13. Network Requirements (สำหรับทีม Network)

**Section นี้สำหรับทีม Network/IT** ที่จะ deploy ระบบ — บอกว่าระบบต้องการ network connectivity แบบไหน

### 13.1 IP Camera Reachability

FaceReg server ต้องเชื่อมต่อ **RTSP stream** ของกล้องได้ตรง ๆ:

| Protocol | Port | Direction | หมายเหตุ |
|---|---|---|---|
| RTSP (TCP) | **554** | server → camera | ระบบใช้ TCP transport (เสถียรกว่า UDP) |
| ICMP (ping) | — | server → camera | ใช้ debug reachability |

**Code:** `camera.py` set `OPENCV_FFMPEG_CAPTURE_OPTIONS=rtsp_transport;tcp` อัตโนมัติ

### 13.2 กรณีกล้องอยู่คนละ subnet/VLAN

ระบบ **ไม่จัดการ routing เอง** — ทีม Network ต้องจัดทางใดทางหนึ่ง:

| วิธี | เหมาะกับ | ข้อควรระวัง |
|---|---|---|
| **Inter-VLAN routing + firewall rule** | กล้อง+server อาคารเดียวกัน VLAN ต่าง | ต้อง allow `server → camera_ip:554/tcp` |
| **Site-to-site VPN** | กล้องคนละสาขา | latency ต้อง < 100ms, bandwidth ต้องพอ |
| **Tailscale/WireGuard subnet router** | dev/PoC, ไม่มี VPN องค์กร | ต้องมี node อยู่ใน camera network 24/7 |
| **Dedicated NIC** บน server | physical camera VLAN trunk | ตั้ง static route แยก subnet |

### 13.3 Bandwidth Requirements

| Resolution | Codec | Bandwidth/cam |
|---|---|---|
| 720p @ 15fps | H.264 | ~1-2 Mbps |
| 1080p @ 15fps | H.264 | ~3-4 Mbps |
| 1080p @ 30fps | H.264 | ~6-8 Mbps |
| 4K @ 15fps | H.265 | ~8-12 Mbps |

**คำนวณรวม:** N กล้อง × bandwidth/cam = bandwidth ขั้นต่ำที่ link ระหว่าง server กับ camera network ต้องรองรับ

### 13.4 Pre-deploy Network Test

**ทีม Network ทำก่อน install FaceReg** (ทดสอบจาก server จริง):

```bash
# 1. ping ถึงกล้องหรือไม่
ping -c 5 <camera_ip>

# 2. port 554 เปิดหรือไม่
nc -zv <camera_ip> 554

# 3. RTSP stream ดึงได้จริงหรือไม่ (ต้องมี ffplay หรือ vlc)
ffplay -rtsp_transport tcp "rtsp://<user>:<pass>@<camera_ip>:554/<path>"

# 4. วัด latency / packet loss นาน 1 นาที
ping -c 60 <camera_ip> | tail -3
```

**Pass criteria:**
- ping loss < 1%
- latency < 50ms (LAN) / < 150ms (WAN)
- RTSP stream เปิดได้และเล่นต่อเนื่อง > 30 วินาที โดยไม่ขาด

### 13.5 อื่น ๆ ที่ network team อาจต้องเปิด

| Service | Port | Direction | กรณี |
|---|---|---|---|
| HTTP | 80 | client → server | nginx redirect → 443 |
| HTTPS | 443 | client → server | Web UI หลัก (production) |
| HTTP (dev) | 8001 | client → server | stream_server (dev only) |
| HTTP (dev) | 8000 | client → server | api.py (dev only) |
| PostgreSQL | 5432 | server → DB | ถ้า PG อยู่คนละเครื่อง |
| Telegram API | 443 | server → api.telegram.org | system notify (optional) |
| NTP | 123 | server → NTP server | sync system clock |

### 13.6 DNS / Static IP

- **Server IP:** แนะนำ static (กล้องบางตัว whitelist client IP)
- **กล้อง IP:** static หรือ DHCP reservation (อย่าให้เปลี่ยน — cameras.json hardcode IP)
- **Domain:** ถ้าใช้ HTTPS ต้องมี domain + DNS A record ชี้ public IP

### 13.7 Troubleshoot reference

ถ้าผู้ดูแลรายงาน "กล้องเปิดไม่ได้" และเป็นกล้อง IP:

```bash
# ดู log
grep "CAM ERROR\|CAM\]" /var/log/facereg/*.log | tail -20

# common patterns:
# "Stream timeout triggered after 30000.000 ms"  → network unreachable / port block
# "Connection refused"                            → port 554 ปิด / กล้องไม่รัน RTSP
# "401 Unauthorized"                              → username/password กล้องผิด
# "Connection reset by peer"                      → กล้อง reboot / VPN drop
```

ดู `8.1 ระบบไม่เริ่ม / กล้องไม่ขึ้น` สำหรับ troubleshoot ทั่วไป

---

*อัปเดตล่าสุด: 2026-05-21 (เพิ่ม Network Requirements section 13)*
