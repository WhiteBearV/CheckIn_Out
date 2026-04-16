# รายงานภาพรวมโครงการ — ระบบลงเวลาด้วยการจดจำใบหน้า
## Face Attendance System (CheckIn-Out Pro)

---

## 1. ภาพรวมโครงการ

ระบบลงเวลาอัตโนมัติด้วยการจดจำใบหน้า (Face Attendance System) พัฒนาขึ้นเพื่อทดแทนระบบลงเวลาแบบดั้งเดิม โดยใช้กล้องตรวจจับและยืนยันตัวตนของบุคลากรแบบอัตโนมัติ รองรับการลงเวลา เข้า-ออก (Check-In / Check-Out) พร้อมระบบป้องกันการปลอมแปลง (Anti-Spoofing) หลายชั้นเพื่อความปลอดภัย

ระบบพัฒนาบน Linux (Ubuntu) และมี Windows Version รองรับ รวมถึง Raspberry Pi 5 (Lightweight Version)

---

## 2. สถาปัตยกรรมระบบ (System Architecture)

```
┌─────────────────────────────────────────────────────────┐
│                      HARDWARE                           │
│   กล้อง USB (Laptop)     กล้อง IP Camera (RTSP)        │
└───────────────┬────────────────────┬────────────────────┘
                │                    │
┌───────────────▼────────────────────▼────────────────────┐
│               CORE ENGINE (main.py)                     │
│  ┌──────────┐  ┌──────────────┐  ┌───────────────────┐  │
│  │InsightFace│  │Liveness Engine│  │ Session Manager   │  │
│  │(ArcFace) │  │  (6 ด่าน)    │  │ (Check-In/Out)    │  │
│  └──────────┘  └──────────────┘  └───────────────────┘  │
│  ┌──────────┐  ┌──────────────┐  ┌───────────────────┐  │
│  │ThreadedCam│  │  UI Renderer  │  │   Config System   │  │
│  └──────────┘  └──────────────┘  └───────────────────┘  │
└───────────────────────────┬─────────────────────────────┘
                            │  live_frame_{id}.jpg
                            │  live_state_{id}.json
┌───────────────────────────▼─────────────────────────────┐
│                 FastAPI Backend (api.py)                 │
│     REST API + MJPEG Stream + Process Management        │
└───────────────────────────┬─────────────────────────────┘
                            │  HTTP / WebSocket
┌───────────────────────────▼─────────────────────────────┐
│             Web Dashboard (Vue 3 + Vite)                │
│  Camera View | Dashboard | Live Detection | Reports     │
└─────────────────────────────────────────────────────────┘
                            │
┌───────────────────────────▼─────────────────────────────┐
│              PostgreSQL Database                        │
│                attendance_logs table                    │
└─────────────────────────────────────────────────────────┘
                            │
┌───────────────────────────▼─────────────────────────────┐
│             External Personnel API                      │
│     ดึงข้อมูลพนักงาน (ชื่อ/ตำแหน่ง/หน่วยงาน)           │
└─────────────────────────────────────────────────────────┘
```

---

## 3. Technology Stack

| ชั้น | เทคโนโลยี | หน้าที่ |
|------|-----------|---------|
| **Face Recognition** | InsightFace (buffalo_l) + ArcFace 512d | จดจำใบหน้า |
| **Inference Runtime** | ONNX Runtime (GPU/CPU) | ประมวลผล AI model |
| **Anti-Spoofing** | MediaPipe Hands + MiniFASNet | ป้องกันการปลอมแปลง |
| **Computer Vision** | OpenCV (cv2) + NumPy | ประมวลผลภาพ |
| **Camera** | ThreadedCamera (USB + RTSP) | อ่านเฟรมจากกล้อง |
| **Backend API** | FastAPI + Uvicorn | REST API + MJPEG Stream |
| **Database** | PostgreSQL + psycopg3 | บันทึกข้อมูลการลงเวลา |
| **External API** | requests (HTTP) | ดึงข้อมูลพนักงาน |
| **Frontend** | Vue 3 + Vite + TailwindCSS | Web Dashboard |
| **OS** | Linux (Ubuntu) / Windows | รองรับทั้งสอง |

---

## 4. ไฟล์หลักของระบบ

| ไฟล์ | บรรทัด | หน้าที่ |
|------|--------|---------|
| `main.py` | 774 | Main loop — ตรวจจับ, จดจำ, ตรวจ liveness, บันทึก |
| `liveness_engine.py` | 1,025 | Anti-Spoofing pipeline 6 ด่าน |
| `api.py` | 993 | FastAPI backend — REST API + Camera stream |
| `config.py` | 257 | ตั้งค่าทั้งหมดในที่เดียว |
| `ui_renderer.py` | 653 | วาด UI ทั้งหมด (OpenCV overlay) |
| `session_manager.py` | 228 | จัดการ session / check-in / check-out |
| `camera.py` | — | ThreadedCamera (USB + RTSP auto-reconnect) |
| `api_client.py` | — | ดึงข้อมูลพนักงาน + บันทึก attendance |
| `encode_faces_arcface.py` | — | สร้าง face encodings จากรูปใน known_faces/ |

---

## 5. คุณสมบัติหลักของระบบ

### 5.1 การจดจำใบหน้า (Face Recognition)
- ใช้ **InsightFace buffalo_l** + **ArcFace 512 dimensions** (ความแม่นยำสูง)
- เปรียบเทียบด้วย **Cosine Similarity** แบบ Vectorized (เร็ว, รองรับหลายคนพร้อมกัน)
- ประมวลผลบน **GPU** ผ่าน ONNX Runtime (fallback CPU อัตโนมัติ)
- ตรวจจับขนาด 320×320 pixels (ปรับได้ถึง 640×640 สำหรับความแม่นยำสูงขึ้น)

### 5.2 ระบบป้องกันการปลอมแปลง (Anti-Spoofing) — 6 ด่าน

```
ด่าน 1: Landmark Depth    — ตรวจความลึก 3D จาก 68-point landmarks
ด่าน 2: Micro-Motion      — ตรวจการขยับเล็กน้อยข้ามเฟรม
ด่าน 2.5: Blink Detection — Eye Aspect Ratio (EAR) ตรวจกะพริบตา
ด่าน 3: Texture Analysis  — LBP + Laplacian + Chroma (ผิวหน้าจริง vs จอ)
ด่าน 4: Screen Detector   — Canny Edge + FFT ตรวจขอบจอ/กรอบมือถือ
ด่าน 5: Finger Challenge  — MediaPipe Hands สุ่มชูนิ้ว 2 ชุด (ป้องกันวิดีโอ)
ด่าน 6: MiniFASNet (FAS)  — AI Deep Learning ตรวจ spoof โดยตรง
```

**ผลลัพธ์**: ป้องกันได้ทั้งรูปภาพ, วิดีโอ, หน้าจอมือถือ, และหน้ากาก 3D

### 5.3 Multi-Camera Support
- รองรับ **กล้อง USB** (Laptop webcam, external camera)
- รองรับ **IP Camera ผ่าน RTSP** (กล้องวงจรปิด LAN)
- รัน `python main.py` เดียว → กล้องทุกตัวทำงานพร้อมกัน (subprocess แยก)
- แต่ละกล้องมี session อิสระ, บันทึก snapshot และข้อมูล liveness แยกกัน

### 5.4 การบันทึกข้อมูล
- บันทึก **Check-In** และ **Check-Out** ลง PostgreSQL
- ตรวจซ้ำอัตโนมัติ (ไม่บันทึกซ้ำถ้า IN/OUT วันนี้แล้ว)
- บันทึก **Snapshot รูปภาพ** ตอน check-in และ face crop (PicSAVE/)
- ดึงข้อมูลพนักงาน (ชื่อ/ตำแหน่ง/หน่วยงาน) จาก **External API** แบบ Real-time

### 5.5 ตารางเวลา (Active Windows)
- ระบบรัน 24/7 แต่ประมวลผลใบหน้าเฉพาะ **ช่วงเวลาทำงาน** (05:00–22:00)
- นอกช่วง → Idle mode: ลด CPU/GPU, แสดงภาพ CCTV ธรรมดา
- **Daily Reset** อัตโนมัติตอนเที่ยงคืน

---

## 6. Web Dashboard

Dashboard เป็น **Single Page Application** (Vue 3 + Vite + TailwindCSS) เสิร์ฟโดย FastAPI

### หน้าที่มี:

#### หน้า Dashboard (DashboardView)
- **StatCards**: จำนวน Check-In / Check-Out / ยังอยู่ในวันนี้
- **HourlyChart**: กราฟแสดงการลงเวลาแยกตามชั่วโมง
- **OrgBreakdown**: สัดส่วนการลงเวลาแยกตามหน่วยงาน
- **PersonCards**: การ์ดแสดงรายชื่อพนักงานพร้อมรูปและสถานะ
- **AttendanceFeed**: รายการลงเวลาล่าสุดแบบ Real-time
- **Live Detection**: สถานะ liveness แบบ Real-time จาก main.py

#### หน้ากล้อง (CameraView)
- แสดง **MJPEG Stream** พร้อม Face Recognition Overlay จากทุกกล้อง
- สถานะ **LIVE / กำลังเริ่มต้น / ออฟไลน์** แบบ Real-time
- **Fullscreen mode** (กด F) — แสดงรายชื่อวันนี้แบบ Kiosk
- สถิติ Check-In / Check-Out แบบ Real-time ใน Fullscreen

### Data Flow (Real-time):
```
main.py → live_frame_{id}.jpg (15fps) → /cameras/{id}/face-stream → Dashboard
main.py → live_state_{id}.json (1fps) → /session/live → LiveDetection component
```

---

## 7. REST API Endpoints (FastAPI)

| Method | Endpoint | หน้าที่ |
|--------|----------|---------|
| `GET` | `/attendance/today` | รายการลงเวลาวันนี้ |
| `POST` | `/attendance` | บันทึก IN/OUT |
| `GET` | `/attendance/{per_id}` | ประวัติลงเวลาของพนักงาน |
| `GET` | `/session/live` | สถานะ Real-time จาก main.py (ทุกกล้อง) |
| `GET` | `/cameras` | รายการกล้องทั้งหมด |
| `GET` | `/cameras/{id}/face-stream` | MJPEG stream พร้อม overlay |
| `POST` | `/cameras/{id}/face/start` | Start main.py สำหรับกล้องนั้น |
| `POST` | `/cameras/{id}/face/stop` | Stop main.py สำหรับกล้องนั้น |
| `GET` | `/cameras/{id}/face/status` | สถานะ process + frame age |
| `GET` | `/person-photo/{per_id}` | รูป snapshot ล่าสุดของพนักงาน |

---

## 8. Profile System (การสลับค่าตั้ง)

```bash
python main.py               # ใช้ค่า default ใน config.py
python main.py cam_main      # โหลด profiles/cam_main.py (กล้องหลัก)
python main.py cam_usb       # โหลด profiles/cam_usb.py (USB camera)
python main.py test          # โหลด profiles/test.py (โหมดทดสอบ)
FACE_PROFILE=cam_usb python main.py
```

ค่าใน profile จะ **override** ค่าใน config.py เฉพาะ key ที่กำหนด

---

## 9. การทำงานของระบบ (Flow)

```
1. ผู้ใช้เดินเข้ามาหน้ากล้อง
2. InsightFace ตรวจจับใบหน้า (detection)
3. ArcFace สร้าง 512d embedding → เปรียบเทียบกับ encodings.pkl
4. ระบุตัวตน: ชื่อ/per_id (หรือ "Unknown")
5. Liveness Pipeline ด่าน 1–6 ประเมินตามลำดับ
6. ถ้าผ่าน Anti-Spoofing ทั้งหมด → "confirmed"
7. Session Manager → Check-In หรือ Check-Out
8. api_client.py → ดึงข้อมูลพนักงานจาก External API
9. บันทึกลง PostgreSQL + บันทึกรูป Snapshot
10. แสดงผลบน OpenCV UI + ส่ง Live Stream ไป Dashboard
```

---

## 10. ประวัติการพัฒนา (Version History)

| Version | ไฮไลท์ |
|---------|--------|
| v3–v5 | เริ่มต้นด้วย face_recognition (dlib 128d) + SQLite |
| v6 | เปลี่ยนเป็น InsightFace (ArcFace 512d) + ONNX GPU |
| v7 | เพิ่ม Anti-Spoofing หลายชั้น (Depth, Motion, Texture) |
| v8 | Hardening: Blink Detection + Absence Re-Verification |
| v9 | External API Integration + PostgreSQL + Snapshot |
| v9 (Pi) | Lightweight version สำหรับ Raspberry Pi 5 |
| v10 | MiniFASNet (AI-based FAS) + FFT Screen Detector |
| Dashboard V1 | Vue 3 Web Dashboard + FastAPI + MJPEG Stream |
| Dashboard V2–V3 | Chart, PersonCard, LiveDetection, OrgBreakdown |
| Current | Multi-Camera Support (USB + IP Camera พร้อมกัน) |

---

## 11. โครงสร้างไฟล์ (Directory Structure)

```
CheckIn_Out/
├── main.py                  ← Main loop (รัน python main.py)
├── config.py                ← ตั้งค่าทั้งหมด (แก้ที่เดียว)
├── api.py                   ← FastAPI backend
├── api_client.py            ← ดึงข้อมูลพนักงาน + บันทึก attendance
├── camera.py                ← ThreadedCamera (USB + RTSP)
├── liveness_engine.py       ← Anti-Spoofing 6 ด่าน
├── session_manager.py       ← Session / Check-In / Check-Out
├── ui_renderer.py           ← วาด UI (OpenCV)
├── encode_faces_arcface.py  ← สร้าง encodings.pkl
├── db.py                    ← PostgreSQL connection
├── profiles/                ← Profile configs (สลับได้)
│   ├── cam_main.py
│   ├── cam_usb.py
│   └── test.py
├── known_faces/             ← รูปใบหน้าสำหรับ encode
│   └── {per_id}/            ← โฟลเดอร์ชื่อ = เลขบัตร 13 หลัก
├── PicSAVE/                 ← รูป Snapshot บันทึกเมื่อ Check-In
├── dashboard/               ← Vue 3 Web Dashboard
│   ├── src/
│   │   ├── views/
│   │   │   ├── DashboardView.vue   ← หน้าหลัก
│   │   │   └── CameraView.vue      ← หน้ากล้อง + Live Stream
│   │   ├── components/
│   │   │   ├── PersonCard.vue
│   │   │   ├── LiveDetection.vue
│   │   │   ├── HourlyChart.vue
│   │   │   ├── OrgBreakdown.vue
│   │   │   └── AttendanceFeed.vue
│   │   ├── composables/
│   │   │   ├── useAttendance.js
│   │   │   └── useLiveSession.js
│   │   └── api/attendance.js
│   └── dist/ (build output → static/)
├── static/                  ← Dashboard build output (เสิร์ฟโดย FastAPI)
└── Win_Ver/                 ← Windows Version
```

---

## 12. วิธีรันระบบ

```bash
# 1. เริ่ม FastAPI server (backend + dashboard)
uvicorn api:app --host 0.0.0.0 --port 8000

# 2. เปิด Dashboard ที่
http://localhost:8000/dashboard/

# 3. รัน Face Recognition (ทุกกล้องพร้อมกัน)
python main.py

# หรือรันแบบระบุ profile
python main.py cam_main

# 4. encode ใบหน้าใหม่ (เมื่อเพิ่มพนักงาน)
python encode_faces_arcface.py
```

---

## 13. จุดเด่นของระบบ

1. **ความแม่นยำสูง** — ArcFace 512d ความแม่นยำระดับ production
2. **Anti-Spoofing แบบ Multi-Layer** — 6 ด่าน ป้องกันได้หลายรูปแบบ
3. **Multi-Camera** — รองรับกล้องหลายตัวพร้อมกัน (USB + IP Camera)
4. **Real-time Dashboard** — แสดงผลแบบ Real-time ผ่าน Web Browser
5. **Headless Mode** — รัน background ได้ ส่ง stream ผ่าน MJPEG ไป Dashboard
6. **Profile System** — สลับค่าตั้งได้ง่ายโดยไม่แก้ code หลัก
7. **External API Integration** — เชื่อมต่อฐานข้อมูลพนักงานภายนอก
8. **Auto-Reconnect** — กล้อง IP Camera reconnect อัตโนมัติเมื่อสัญญาณหาย
9. **Daily Reset** — รีเซ็ต session อัตโนมัติรายวัน

---

## 14. ข้อจำกัดและแนวทางพัฒนาต่อ

| ข้อจำกัด | แนวทางแก้ไข |
|----------|-------------|
| ต้องรัน main.py แยกต่างหาก | พัฒนาเป็น systemd service / auto-start |
| Anti-Spoofing อาจช้าในสภาพแสงน้อย | ปรับ threshold หรือเพิ่ม IR camera |
| Dashboard ยังไม่มี authentication | เพิ่ม login / JWT |
| Encoding ต้องทำ manual | พัฒนาหน้า Register พนักงานผ่าน Dashboard |

---

*รายงานนี้จัดทำสำหรับการ present โครงการ Face Attendance System*
*อัพเดตล่าสุด: เมษายน 2569 (2026)*
