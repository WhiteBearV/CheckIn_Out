# คู่มือการนำโค้ด Face Attendance System ขึ้น Docker

> ตั้งแต่ติดตั้ง Docker จนถึงการใช้งานต่อเนื่อง

---

## ภาพรวม

ระบบนี้รันผ่าน Docker Compose โดยมี 2 container:

| Container | ทำหน้าที่ |
|---|---|
| `face_db` | PostgreSQL 15 — ฐานข้อมูลบันทึกการเข้างาน |
| `face_api` | FastAPI + InsightFace — ระบบจดจำใบหน้า + Web Dashboard |

| Port | ใช้งาน |
|---|---|
| `80` | Web Dashboard + API (`http://<IP>/`) |
| `5432` | PostgreSQL (ภายใน Docker network เท่านั้น) |

---

## ส่วนที่ 1 — ติดตั้ง Docker (ทำครั้งแรกเท่านั้น)

### Linux (Ubuntu / Debian)

```bash
# 1. ถอน docker เก่าออกก่อน (ถ้ามี)
sudo apt-get remove -y docker docker-engine docker.io containerd runc

# 2. ติดตั้ง dependency
sudo apt-get update
sudo apt-get install -y ca-certificates curl gnupg lsb-release

# 3. เพิ่ม Docker GPG key + repository
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
    | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
  https://download.docker.com/linux/ubuntu \
  $(lsb_release -cs) stable" \
  | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

# 4. ติดตั้ง Docker Engine + Compose
sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io \
                        docker-buildx-plugin docker-compose-plugin

# 5. ให้ user ปัจจุบันใช้ docker ได้โดยไม่ต้อง sudo
sudo usermod -aG docker $USER
newgrp docker

# 6. ตรวจสอบ
docker --version
docker compose version
```

### macOS

1. ดาวน์โหลด **Docker Desktop** จาก [docker.com/products/docker-desktop](https://www.docker.com/products/docker-desktop)
2. ติดตั้งตามปกติ (`.dmg` → ลาก Docker ไป Applications)
3. เปิด Docker Desktop รอจนไอคอน 🐳 ค้างอยู่ที่ menu bar
4. ตรวจสอบใน Terminal:

```bash
docker --version
docker compose version
```

### Windows

1. เปิดใช้งาน **WSL2** ก่อน — เปิด PowerShell (Admin) แล้วพิมพ์:
   ```powershell
   wsl --install
   ```
   จากนั้น Restart เครื่อง

2. ดาวน์โหลด **Docker Desktop** จาก [docker.com/products/docker-desktop](https://www.docker.com/products/docker-desktop)
3. ติดตั้ง เลือก **"Use WSL 2 based engine"**
4. เปิด Docker Desktop รอ daemon พร้อม
5. ตรวจสอบใน PowerShell / WSL Terminal:

```powershell
docker --version
docker compose version
```

---

## ส่วนที่ 2 — ดึงโค้ดจาก GitHub (ครั้งแรก)

### ติดตั้ง Git (ถ้ายังไม่มี)

```bash
# Ubuntu/Debian
sudo apt-get install -y git

# macOS
brew install git
```

### Clone โปรเจกต์

```bash
git clone https://github.com/<GitHub-Username>/CheckIn_Out.git
cd CheckIn_Out
```

> **`<GitHub-Username>`** = ชื่อ account GitHub เจ้าของ repository

### เลือก Branch

```bash
git checkout main          # branch หลัก (แนะนำ)
# หรือ
git checkout <ชื่อ-branch>  # เช่น deawVersion, maevVersion
```

### ตรวจสอบ

```bash
git status
git log --oneline -5
```

---

## ส่วนที่ 3 — ตั้งค่าก่อนรันครั้งแรก

### 3.1 สร้างไฟล์ `.env`

ไฟล์ `.env` เก็บค่า config เฉพาะเครื่อง/สภาพแวดล้อม ต้องสร้างเองเพราะ **ไม่ได้เก็บใน GitHub**

สร้างไฟล์ `.env` ที่ **root ของโปรเจกต์** (ระดับเดียวกับโฟลเดอร์ `docker/`):

```bash
nano .env
```

ใส่เนื้อหาดังนี้ (แก้ค่า `<...>` ตาม environment จริง):

```env
# ── Camera ────────────────────────────────────────────────────────────
# USB camera index (0, 1, ...) หรือ RTSP URL ของกล้อง IP
CAMERA_URL=0
CAMERA_FLIP=false

# ── API Security ──────────────────────────────────────────────────────
ADMIN_API_KEY=<ใส่-secret-key-ที่ต้องการ>
JWT_SECRET_KEY=<ใส่-jwt-secret-key-ยาว-ๆ>

# ── External Person API ───────────────────────────────────────────────
# MOCK_MODE=true  → ใช้ข้อมูลจำลอง (ไม่ต้องมี external API จริง)
# MOCK_MODE=false → เรียก external API จริง
MOCK_MODE=false
EXTERNAL_API_URL=https://<URL-ของ-External-API>/
EXTERNAL_API_KEY=<API-Key-ของ-External-API>

# ── Face Recognition ──────────────────────────────────────────────────
FAS_ENABLED=false
```

**ค่าที่ต้องแก้ตามระบบจริง:**

| ค่า | คำอธิบาย |
|---|---|
| `<ใส่-secret-key-ที่ต้องการ>` | รหัสสำหรับ Admin API เช่น `mysecretkey123` |
| `<ใส่-jwt-secret-key-ยาว-ๆ>` | ข้อความสุ่มยาวสำหรับ JWT เช่น `abc123xyz...` |
| `<URL-ของ-External-API>` | URL ของ API บุคลากร (ถ้าไม่มีให้ตั้ง `MOCK_MODE=true`) |
| `<API-Key-ของ-External-API>` | API Key ของระบบบุคลากร |

### 3.2 เตรียม Face Encodings

ก่อนรัน Docker ต้องมีไฟล์ `encodings.pkl` ที่สร้างจากรูปใบหน้าใน `known_faces/`

```bash
# ติดตั้ง dependency บน host (ครั้งแรกเท่านั้น)
pip install -r requirements.txt

# วางรูปใบหน้าใน known_faces/<ชื่อบุคคล>/รูป.jpg
# (1 โฟลเดอร์ต่อ 1 คน ใส่รูปได้หลายรูป)
ls known_faces/

# สร้าง encodings
python encode_faces_arcface.py

# ตรวจสอบว่าสร้างสำเร็จ
ls -lh encodings.pkl
```

โครงสร้าง `known_faces/` ที่ถูกต้อง:

```
known_faces/
├── ชื่อ_บุคคล_A/
│     ├── photo1.jpg
│     └── photo2.jpg
└── ชื่อ_บุคคล_B/
      └── photo1.jpg
```

### 3.3 ดาวน์โหลด InsightFace Models

Docker container mount `~/.insightface` จาก host → ต้อง download models ลง host ก่อน (ทำครั้งแรกเท่านั้น)

```bash
python -c "import insightface; insightface.app.FaceAnalysis('buffalo_l')"
```

Models จะถูก download ไปที่ `~/.insightface/models/buffalo_l/`  
ครั้งถัดไป Docker จะใช้ cache นี้เลย **ไม่ต้อง download ซ้ำ**

---

## ส่วนที่ 4 — รัน Docker ครั้งแรก (Build + Start)

> ทุกคำสั่งรันจาก **root ของโปรเจกต์** (โฟลเดอร์ `CheckIn_Out/`)

### 4.1 Build + เริ่มระบบ

```bash
docker compose -f docker/docker-compose.yml up -d --build
```

Docker จะทำตามลำดับนี้:

1. **Build image** `face_api` จาก `docker/Dockerfile`
   - ดาวน์โหลด `python:3.12-slim` (ครั้งแรกใช้เวลา 5–10 นาที)
   - ติดตั้ง system library (OpenCV, ffmpeg ฯลฯ)
   - ติดตั้ง `tensorflow-cpu` (~250 MB ใช้เวลา 5–15 นาที)
   - ติดตั้ง insightface, mediapipe, fastapi ฯลฯ
   - คัดลอกโค้ดเข้า image
2. สร้าง container `face_db` (PostgreSQL)
3. สร้าง container `face_api` (FastAPI)
4. รัน `face_db` ก่อน รอจน healthy แล้วค่อยรัน `face_api`

ดู progress ระหว่าง build (เปิดหน้าต่าง Terminal ใหม่):

```bash
docker compose -f docker/docker-compose.yml logs -f
```

### 4.2 ตรวจสอบหลังรัน

```bash
docker compose -f docker/docker-compose.yml ps
```

**ผลที่ถูกต้อง:**

```
NAME        STATUS              PORTS
face_db     Up (healthy)        5432/tcp
face_api    Up                  0.0.0.0:80->8000/tcp
```

```bash
# ดู log ตรวจสอบ error
docker compose -f docker/docker-compose.yml logs -f api
```

**ผลที่ถูกต้องใน log:**

```
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8000
```

### 4.3 เปิด Web Dashboard

| URL | ใช้งาน |
|---|---|
| `http://localhost/dashboard/` | Dashboard (รันบนเครื่องตัวเอง) |
| `http://<IP-เครื่อง>/dashboard/` | Dashboard (เข้าจากเครื่องอื่นใน LAN) |
| `http://localhost/docs` | API Docs (Swagger UI) |

หา IP เครื่องตัวเอง:

```bash
hostname -I          # Linux
ipconfig getifaddr en0  # macOS
```

---

## ส่วนที่ 5 — การใช้งานประจำวัน (ครั้งถัดๆ ไป)

### เริ่มระบบ (ไม่มีการแก้โค้ด)

```bash
docker compose -f docker/docker-compose.yml up -d
```

Container จะรีสตาร์ทจาก image เดิม เร็วกว่าครั้งแรกมาก (ไม่ต้อง install ซ้ำ)

### หยุดระบบ

```bash
docker compose -f docker/docker-compose.yml down
```

> ข้อมูลใน database จะยังอยู่ (เก็บใน Docker volume: `postgres_data`) ไม่หายแม้ down แล้ว up ใหม่

### ดึงโค้ดใหม่จาก GitHub แล้วรันต่อ

```bash
# 1. หยุดระบบก่อน
docker compose -f docker/docker-compose.yml down

# 2. ดึงโค้ดล่าสุด
git pull origin main          # หรือ branch ที่ใช้งาน

# 3. Build ใหม่ + เริ่มระบบ
docker compose -f docker/docker-compose.yml up -d --build
```

> **เมื่อไหรต้องใช้ `--build`**
> - แก้ไขโค้ด Python (`.py`)
> - เปลี่ยน `docker/Dockerfile`
> - เปลี่ยน `docker/requirements.*.txt`
>
> ถ้าเปลี่ยนแค่ `.env` หรือ `encodings.pkl` → ไม่ต้อง `--build`

### รีสตาร์ทเฉพาะ API (เร็ว ไม่ rebuild)

```bash
docker compose -f docker/docker-compose.yml restart api
```

### ดู Log

```bash
# ทุก service แบบ realtime
docker compose -f docker/docker-compose.yml logs -f

# เฉพาะ API
docker compose -f docker/docker-compose.yml logs -f api

# เฉพาะ Database
docker compose -f docker/docker-compose.yml logs -f db

# ย้อนหลัง 100 บรรทัด
docker compose -f docker/docker-compose.yml logs --tail=100 api
```

กด `Ctrl+C` เพื่อหยุดดู log (container ยังทำงานต่อ)

---

## ส่วนที่ 6 — Quick Reference

| สถานการณ์ | คำสั่ง |
|---|---|
| เริ่มระบบ (ปกติ) | `docker compose -f docker/docker-compose.yml up -d` |
| เริ่มระบบ (หลังแก้โค้ด/git pull) | `docker compose -f docker/docker-compose.yml up -d --build` |
| หยุดระบบ | `docker compose -f docker/docker-compose.yml down` |
| รีสตาร์ท API | `docker compose -f docker/docker-compose.yml restart api` |
| ดูสถานะ container | `docker compose -f docker/docker-compose.yml ps` |
| ดู log realtime | `docker compose -f docker/docker-compose.yml logs -f api` |
| เข้า shell ใน container | `docker exec -it face_api bash` |
| ดึงโค้ดใหม่ | `git pull origin main` |
| เช็ค branch ปัจจุบัน | `git branch` |
| สลับ branch | `git checkout <ชื่อ-branch>` |

---

## ส่วนที่ 7 — การจัดการ Database

### เข้าถึง Database โดยตรง

```bash
docker exec -it face_db psql -U face_user -d face_attendance
```

คำสั่ง PostgreSQL พื้นฐาน:

```sql
\dt                                                          -- แสดงตารางทั้งหมด
\d attendance                                                -- โครงสร้างตาราง attendance
SELECT * FROM attendance ORDER BY timestamp DESC LIMIT 10;  -- ดูข้อมูลล่าสุด 10 รายการ
\q                                                           -- ออกจาก psql
```

### Backup Database

```bash
docker exec face_db pg_dump -U face_user face_attendance \
    > backup_$(date +%Y%m%d_%H%M%S).sql
```

### Restore Database

```bash
# หยุด api ก่อน
docker compose -f docker/docker-compose.yml stop api

# restore
docker exec -i face_db psql -U face_user face_attendance < backup_YYYYMMDD_HHMMSS.sql

# เริ่ม api ใหม่
docker compose -f docker/docker-compose.yml start api
```

### ล้าง Database ทั้งหมด (เริ่มใหม่)

> ⚠️ **ข้อมูลจะหายถาวร** ทำเมื่อต้องการเริ่มต้นใหม่เท่านั้น

```bash
docker compose -f docker/docker-compose.yml down -v
docker compose -f docker/docker-compose.yml up -d --build
```

flag `-v` จะลบ Docker volume (`postgres_data`) ด้วย

---

## ส่วนที่ 8 — Update Face Encodings (เพิ่ม/แก้ข้อมูลใบหน้า)

```bash
# 1. เพิ่ม/แก้รูปใน known_faces/
# known_faces/<ชื่อบุคคล>/photo.jpg

# 2. Regenerate encodings บน host (ไม่ใช่ใน container)
python encode_faces_arcface.py

# 3. Restart API (ไม่ต้อง rebuild image)
docker compose -f docker/docker-compose.yml restart api
```

---

## ส่วนที่ 9 — แก้ปัญหาที่พบบ่อย

### Container ไม่ขึ้น / exit ทันที

```bash
docker compose -f docker/docker-compose.yml logs api
```

สาเหตุที่พบบ่อย:

| ปัญหา | วิธีแก้ |
|---|---|
| `.env` ไม่มีหรือค่าผิด | ตรวจสอบไฟล์ `.env` |
| `encodings.pkl` ไม่มี | รัน `python encode_faces_arcface.py` |
| port 80 ถูกใช้งานอยู่ | หยุด service ที่ใช้ port 80 หรือเปลี่ยน port ใน `docker-compose.yml` |

### Dashboard เปิดไม่ได้ / 502

```bash
# ตรวจสอบสถานะ container
docker compose -f docker/docker-compose.yml ps

# ดู log
docker compose -f docker/docker-compose.yml logs --tail=50 api
```

### InsightFace model ไม่พบ / download ซ้ำทุกครั้ง

```bash
# ตรวจสอบ
ls ~/.insightface/models/

# Download ใหม่บน host
python -c "import insightface; insightface.app.FaceAnalysis('buffalo_l')"
```

### Permission denied บน Linux

```bash
sudo usermod -aG docker $USER
newgrp docker
```

### Build ช้า / ต้องการ rebuild ใหม่สมบูรณ์

```bash
# ล้าง layer cache แล้ว build ใหม่ทั้งหมด
docker compose -f docker/docker-compose.yml build --no-cache
```

> Build ครั้งแรกใช้เวลา 10–30 นาที (ขึ้นอยู่กับ internet)  
> ครั้งถัดไป Docker ใช้ layer cache → เร็วกว่ามาก (1–5 นาที)

---

## ส่วนที่ 10 — โครงสร้างโฟลเดอร์สำคัญ

```
CheckIn_Out/                     ← root โปรเจกต์
├── docker/
│     ├── docker-compose.yml     ← config container ทั้งหมด
│     ├── Dockerfile              ← วิธี build image face_api
│     ├── requirements.api.txt
│     └── requirements.main.txt
├── .env                         ← ค่า config เฉพาะเครื่อง (สร้างเอง ไม่อยู่ใน GitHub)
├── encodings.pkl                ← ข้อมูลใบหน้า (สร้างจาก encode_faces_arcface.py)
├── known_faces/                 ← รูปใบหน้าสำหรับ encode
├── PicSAVE/                     ← รูป snapshot เวลา check-in/out
├── api.py                       ← FastAPI backend หลัก
├── main.py                      ← Face recognition loop
└── encode_faces_arcface.py      ← สร้าง encodings.pkl
```

โครงสร้างไฟล์ภาพใน `PicSAVE/`:

```
PicSAVE/YYYY/MM/DD/HH-MM-SS_<per_id>_IN.jpg    ← full frame ตอน check-in
PicSAVE/YYYY/MM/DD/HH-MM-SS_<per_id>_FACE.jpg  ← face crop ตอน check-in
PicSAVE/YYYY/MM/DD/HH-MM-SS_<per_id>_OUT.jpg   ← รูปล่าสุดก่อน check-out
```

---

## สรุป Flow ตั้งแต่ต้นจนใช้งานได้

### ครั้งแรก (ทำทีเดียว)

```
1. ติดตั้ง Docker              → ดูส่วนที่ 1
2. git clone <repo-url>
3. cd CheckIn_Out
4. สร้าง .env                  → ดูส่วนที่ 3.1
5. วางรูปใบหน้าใน known_faces/
6. python encode_faces_arcface.py
7. python -c "import insightface; ..."   (download models)
8. docker compose -f docker/docker-compose.yml up -d --build
9. เปิด http://localhost/dashboard/
```

### ครั้งถัดไป (ใช้ทุกวัน)

```
1. cd CheckIn_Out
2. git pull origin main                  (ถ้ามี update)
3. docker compose -f docker/docker-compose.yml up -d        (ปกติ)
   docker compose -f docker/docker-compose.yml up -d --build (ถ้า pull มา)
4. เปิด http://localhost/dashboard/
5. เมื่อเลิกใช้: docker compose -f docker/docker-compose.yml down
```
