# FaceReg — Face Attendance System

ระบบลงเวลาเข้า-ออกด้วยการสแกนใบหน้า รองรับ multi-camera (USB + IP/RTSP), anti-spoofing, offline mode, audit log

## ⚡ Quick Start (Development)

```bash
# 1. clone + venv
git clone <repo>
cd FaceReg
python3 -m venv venv
venv/bin/pip install -r requirements.txt

# 2. ตั้งค่า (ดู rai ละเอียดที่ "Configuration" ด้านล่าง)
cp .env.example .env                          # แก้ค่าใน .env
cp db_config.example.json db_config.json      # แก้ password DB

# 3. setup PostgreSQL (ครั้งแรก)
sudo -u postgres psql -c "CREATE USER face_user WITH PASSWORD '<password>';"
sudo -u postgres psql -c "CREATE DATABASE face_attendance OWNER face_user;"
sudo -u postgres psql -d face_attendance -f migrations/setup_db.sql

# 4. build frontend
cd front_end && npm install && npm run build && cd ..

# 5. encode รูปต้นแบบ (วางรูปใน known_faces/<per_id>/*.jpg ก่อน)
venv/bin/python encode_faces_arcface.py

# 6. รัน (dev mode)
cd front_end && npm run dev      # จะ spawn stream_server + api.py + vite ให้ครบ
```

เปิด `http://localhost:5173` → login ด้วย default credentials (เปลี่ยนก่อน production):
- admin: `admin / Admin12345`
- viewer: `viewer / User12345`

---

## 📚 เอกสาร

| ไฟล์ | สำหรับใคร | เนื้อหา |
|---|---|---|
| **[RUNBOOK.md](RUNBOOK.md)** | Ops / Deploy / Network team | คู่มือปฏิบัติการ 13 sections (start/stop, backup, troubleshoot, nginx, network requirements) |
| [.env.example](.env.example) | Deploy team | Template env vars พร้อม comment |
| [db_config.example.json](db_config.example.json) | Deploy team | Template PG config |
| [deploy/](deploy/) | Deploy team | systemd services, timers, nginx config, install script |
| [migrations/setup_db.sql](migrations/setup_db.sql) | DBA | สร้าง schema PG ทั้งหมด |
| [CLAUDE.md](CLAUDE.md) | Dev team | Context สำหรับ AI assistant (Claude Code อ่านอัตโนมัติ — ต้องอยู่ root) |

---

## 🚀 Production Deploy (Summary)

อ่านละเอียดที่ [RUNBOOK.md ม.11](RUNBOOK.md#11-production--nginx--https)

```bash
# 1. setup .env + db_config.json + migrations + frontend build (เหมือน dev)

# 2. ติดตั้ง systemd services อัตโนมัติ
sudo bash deploy/install_service.sh
# script จะ auto-detect path + user ปัจจุบัน
# override: sudo FACEREG_DIR=/opt/facereg FACEREG_USER=facereg bash deploy/install_service.sh

# 3. ติดตั้ง nginx (อ่าน comment ใน deploy/nginx-facereg.conf)
# 4. (optional) เปิด HTTPS ด้วย certbot
sudo certbot --nginx -d your-domain.com

# 5. เปลี่ยน default password ผ่าน Web UI หรือ
venv/bin/python manage_users.py reset-password admin
venv/bin/python manage_users.py reset-password viewer
```

---

## 🛠 Stack

- **Face recognition:** InsightFace (buffalo_l ArcFace 512d) + ONNX Runtime (CUDA)
- **Anti-spoofing:** MediaPipe Hands (finger challenge) + MiniFASNet + landmark depth/blink
- **Backend:** FastAPI (stream_server :8001 + api :8000) + PostgreSQL
- **Frontend:** React + Vite + TailwindCSS + React Query
- **Offline:** SQLite WAL queue (sync ทันทีเมื่อ PG กลับมา)
- **Watchdog:** 2-layer (systemd + internal subprocess respawn)

---

## 🔐 Security

- JWT authentication ทุก endpoint (admin/viewer roles)
- Rate limit `/auth/login` (5/min), `/auth/change-password` (10/min)
- Force change password ครั้งแรก (`must_change_password` flag)
- Audit log (login, password change, camera CRUD, system start/stop)
- Internal push token guard endpoint `/push/*`
- CORS origin whitelist

---

## 📞 Support

- **Bug report / issue:** เปิด issue ใน repo นี้
- **Ops/deploy ไม่เข้าใจ:** ดู [RUNBOOK.md ม.8](RUNBOOK.md#8-แก้ปัญหาที่พบบ่อย) (troubleshoot)
- **Network team ติด VLAN/firewall:** ดู [RUNBOOK.md ม.13](RUNBOOK.md#13-network-requirements-สำหรับทีม-network)

---

*FaceReg v16+ — Phase 1-4 complete + monotonic watchdog fix (2026-05-21)*
