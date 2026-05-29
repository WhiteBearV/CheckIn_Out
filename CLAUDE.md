# FaceReg — Face Attendance System

## ผู้ใช้
- นักศึกษาฝึกงาน พัฒนาระบบ Face Attendance ด้วย Python/OpenCV/InsightFace
- ผ่านมาแล้วหลาย version (v3–v10) — มีประสบการณ์กับ codebase นี้พอสมควร
- พูดคุยภาษาไทยเป็นหลัก — ตอบกลับภาษาไทยเสมอ

## Stack
- **Face recognition:** InsightFace (buffalo_l, ArcFace 512d) + ONNX Runtime (GPU)
- **Camera:** ThreadedCamera รองรับทั้ง USB index และ IP camera (RTSP)
- **Anti-spoofing:** MediaPipe Hands (finger challenge) + MiniFASNet
- **Database:** SQLite ผ่าน attendance_db.py / db.py
- **UI (OpenCV):** วาด overlay, panel ขวา, HUD — multi-cam tab bar + camera management GUI
- **Web UI:** React + Vite + TailwindCSS + React Query (front_end/)
- **Stream Server:** FastAPI (stream_server.py) port 8001 — MJPEG + snapshot + state API
- **Attendance API:** FastAPI (api.py) port 8000

## ไฟล์หลัก — Backend
| ไฟล์ | หน้าที่ |
|---|---|
| `main.py` | Main loop — detect, identify, liveness check, multi-cam worker threads |
| `config.py` | ตั้งค่าทั้งหมดในที่เดียว (แก้ที่นี่ที่เดียว) |
| `stream_server.py` | FastAPI server — MJPEG stream, snapshot, state, system start/stop, camera config CRUD |
| `session_manager.py` | จัดการ session / check-in / check-out / save_snapshots() |
| `liveness_engine.py` | Anti-spoofing pipeline ทุกด่าน |
| `ui_renderer.py` | วาด UI ทุกอย่าง (face box, oval guide, panel, HUD) |
| `camera.py` | ThreadedCamera |
| `attendance_db.py` | บันทึก/ดึงข้อมูลการลงเวลา |
| `api.py` | Attendance REST API (port 8000) |
| `encode_faces_arcface.py` | สร้าง encodings.pkl จากรูปใน known_faces/ |
| `cameras.json` | รายการกล้องทั้งหมด (แก้ผ่าน Web UI หรือ /admin page) |
| `profiles/` | Config profiles สลับได้ด้วย argument |
| `Win_Ver/` | Windows version — **แก้เฉพาะเมื่อสั่งเท่านั้น** |

## ไฟล์หลัก — Frontend (front_end/src/)
| ไฟล์ | หน้าที่ |
|---|---|
| `pages/LiveCam.jsx` | หน้ากล้อง live — grid/discord mode, system controls, camera manager |
| `pages/Dashboard.jsx` | หน้าสถิติ — stat cards, attendance table, dept chart, face snapshots |
| `components/Sidebar.jsx` | Sidebar ขยาย/ย่อได้ (drag handle, localStorage persist) |
| `components/StatCard.jsx` | Stat card ใช้ CSS variable per-instance |
| `index.css` | Design System ครบ — tokens, layout, sidebar, stat cards, LiveCam classes |
| `App.jsx` | Router + theme toggle (light/dark) |

## Stream Server — Endpoints หลัก
```
GET  /stream/{cam_id}          → MJPEG video stream
GET  /snapshot/{cam_id}        → ภาพเดี่ยว JPEG (snapshot polling)
GET  /state/{cam_id}           → JSON state (persons, faces, guide overlay)
GET  /snap/{cam_id}/{name}     → face crop thumbnail
GET  /snapfull/{cam_id}/{name} → full frame snapshot (ใช้ใน Dashboard)
GET  /cameras/config           → รายการกล้องทั้งหมด
POST /cameras/config           → เพิ่มกล้อง
PUT  /cameras/config/{cam_id}  → แก้ไขกล้อง
DELETE /cameras/config/{cam_id}→ ลบกล้อง
POST /cameras/reload           → hotload กล้องใหม่ (เหมือนกด R ที่หลังบ้าน)
POST /system/start             → เริ่มระบบ (spawn main.py subprocess)
POST /system/stop              → หยุดระบบ (SIGTERM → save_snapshots → cleanup)
GET  /system/status            → { face: bool, api: bool }
GET  /system/watchdog          → สถานะ watchdog + restart history
POST /cache/clear              → ล้าง snapshot cache (เฉพาะตอน Stop)
GET  /admin                    → Camera Manager GUI (HTML page)
```

## Watchdog / Auto-restart (production)
2-layer watchdog:
- **systemd** (`deploy/facereg-stream.service`) — restart `stream_server.py` ถ้า crash
- **Internal watchdog** (in `stream_server.py`) — respawn `main.py` / `api.py` subprocess ถ้าตายขณะ user สั่ง Start ค้างไว้ (`_user_intent_started=True`)
- Rate limit: 5 restarts ใน 60 วิ → disable แล้วต้องกด Start ใหม่
- ติดตั้ง: `sudo bash deploy/install_service.sh`
- Log: `journalctl -u facereg-stream -f`

## โหมดการรัน
```bash
# โหมดปกติ — stream server + display loop ครบชุด
python main.py

# โหมด headless (spawn จาก web UI Start button)
FACE_HEADLESS=1 python main.py   # เขียน frame/state ลง disk แทน in-memory

# standalone stream server — เปิด browser กด START
python stream_server.py
```

**headless mode:** main.py กับ stream_server.py คนละ process สื่อสารผ่านไฟล์:
- `live_frame_{cam_id}.jpg` — frame ล่าสุด (ลบเมื่อ Stop)
- `live_state_{cam_id}.json` — detection state (ลบเมื่อ Stop)
- `live_snap_{cam_id}_{name}.jpg` — face crop thumbnail (ยังไม่ลบเมื่อ Stop)
- `live_snapfull_{cam_id}_{name}.jpg` — full frame snapshot (ยังไม่ลบเมื่อ Stop)

## Anti-Spoofing Pipeline
1. **Landmark Depth** — ตรวจความลึก 3D จาก 68-point landmarks
2. **Micro-Motion** — ตรวจการขยับเล็กน้อย
3. **Blink Detection** — EAR จาก 68-point landmarks
4. **Texture** — LBP + Laplacian + Chroma
5. **Screen Border** — ปิดอยู่ (false positive จากกล้อง wide-angle fisheye)
6. **Finger Challenge** — MediaPipe Hands ให้ชูนิ้ว 2 ชุดต่างกัน
7. **MiniFASNet (FAS)** — AI model ตรวจ spoof

## IP Camera
- RTSP: `rtsp://admin:@dmin123456@192.168.1.13:554/unicast/c1/s0/live`
- `CAMERA_FLIP = False`

## Profile System
```bash
python main.py cam_main    # โหลด profiles/cam_main.py
python main.py test        # โหลด profiles/test.py
FACE_PROFILE=cam_usb python main.py
```

## PicSAVE — บันทึกรูปถาวร
- บันทึกที่ `PicSAVE/YYYY/MM/DD/HH-MM-SS_{per_id}_IN.jpg` และ `_OUT.jpg`
- เรียกโดย `session.save_snapshots()` ท้าย `run_camera()` loop
- ใน headless mode: ต้อง join(_camera_threads) ก่อน process exit เพื่อให้ save ทัน
