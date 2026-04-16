"""
stream_server.py — MJPEG streaming + JSON state API (Multi-Camera)
====================================================
Endpoints (per-camera):
  GET  /cameras              → list camera IDs ที่ active
  GET  /stream/{cam_id}      → MJPEG video stream
  GET  /snapshot/{cam_id}    → ภาพเดี่ยว JPEG
  GET  /state/{cam_id}       → JSON state สำหรับ canvas overlay
  GET  /snap/{cam_id}/{name} → thumbnail หน้าคนใน panel

Camera Management (GUI):
  GET    /cameras/config             → รายการกล้องทั้งหมดจาก cameras.json
  POST   /cameras/config             → เพิ่มกล้องใหม่
  PUT    /cameras/config/{cam_id}    → แก้ไข config กล้อง
  DELETE /cameras/config/{cam_id}    → ลบกล้อง

Legacy single-cam endpoints (→ cam1, backward compat):
  GET  /stream               → /stream/cam1
  GET  /snapshot             → /snapshot/cam1
  GET  /state                → /state/cam1
  GET  /snap/{name}          → /snap/cam1/{name}
  GET  /status               → ตรวจว่า stream พร้อม
  GET  /window               → ดูสถานะหน้าต่าง OpenCV
  POST /window               → toggle หน้าต่าง OpenCV

วิธีใช้:
  import stream_server
  stream_server.start()
  stream_server.push_frame(cam_id, frame)
  stream_server.push_state(cam_id, state_dict)
  stream_server.push_snapshot(cam_id, name, crop)
  stream_server.get_cv_window()
"""

import asyncio
import json
import threading
from pathlib import Path
from typing import Optional

import cv2
from fastapi import FastAPI, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, Response
from pydantic import BaseModel
import uvicorn

# ─── cameras.json path ────────────────────────────────────────────────────────
_CAMERAS_JSON = Path(__file__).parent / "cameras.json"


# ─── Camera config helpers ────────────────────────────────────────────────────

def _load_cam_configs() -> list:
    """โหลด camera configs จาก cameras.json (ถ้ามี) หรือ fallback ไป config.CAMERAS"""
    if _CAMERAS_JSON.exists():
        try:
            with open(_CAMERAS_JSON, encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"[CAM_MGR] cameras.json อ่านไม่ได้: {e}")
    import config as _c
    return list(getattr(_c, "CAMERAS", []))


def _save_cam_configs(configs: list):
    """บันทึก camera configs ไปยัง cameras.json"""
    with open(_CAMERAS_JSON, "w", encoding="utf-8") as f:
        json.dump(configs, f, ensure_ascii=False, indent=2)


def _mask_url(url: str) -> str:
    """ซ่อน credentials ใน URL จริง — $VAR_NAME แสดงตรงๆ ได้เลย"""
    if not url or url.startswith("$"):
        return url
    import re
    return re.sub(r'(://)[^@/]+@', r'\1***@', url)


def _next_cam_id(configs: list) -> str:
    """หา ID ถัดไป เช่น cam4 ถ้ามี cam1-cam3 แล้ว"""
    nums = []
    for c in configs:
        cid = c.get("id", "")
        if cid.startswith("cam"):
            try:
                nums.append(int(cid[3:]))
            except ValueError:
                pass
    return f"cam{max(nums, default=0) + 1}"


class CameraConfigRequest(BaseModel):
    name: str
    cam_type: str = "usb"       # "usb" หรือ "ip"
    url: Optional[str] = ""
    index: Optional[int] = 0
    flip: bool = False

# ─── Per-camera buffers ───────────────────────────────────────────────────────
_lock        = threading.Lock()
_cam_frames: dict[str, bytes | None]         = {}   # cam_id → latest JPEG
_cam_counts: dict[str, int]                  = {}   # cam_id → frame counter
_cam_states: dict[str, dict]                 = {}   # cam_id → latest state
_cam_snaps:  dict[str, dict[str, bytes]]     = {}   # cam_id → {name: jpeg}

# ─── OpenCV window flag ───────────────────────────────────────────────────────
import config as _cfg
_cv_window: bool = _cfg.CV_WINDOW
del _cfg

_DEFAULT_CAM  = "cam1"
_active_cam   = _DEFAULT_CAM   # กล้องที่ legacy endpoints (/stream, /state, /snap) ชี้อยู่


# ─── Public API (เรียกจาก main.py) ───────────────────────────────────────────

def push_frame(cam_id: str, frame, quality: int = 70):
    """Push raw camera frame สำหรับ cam_id — thread-safe"""
    ok, buf = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, quality])
    if not ok:
        return
    with _lock:
        _cam_frames[cam_id] = buf.tobytes()
        _cam_counts[cam_id] = _cam_counts.get(cam_id, 0) + 1


def push_state(cam_id: str, state: dict):
    """Push detection state สำหรับ frontend canvas overlay"""
    with _lock:
        _cam_states[cam_id] = state


def push_snapshot(cam_id: str, name: str, crop, quality: int = 80):
    """Push face crop thumbnail สำหรับ /snap/{cam_id}/{name}"""
    if crop is None or crop.size == 0:
        return
    ok, buf = cv2.imencode('.jpg', crop, [cv2.IMWRITE_JPEG_QUALITY, quality])
    if ok:
        with _lock:
            if cam_id not in _cam_snaps:
                _cam_snaps[cam_id] = {}
            _cam_snaps[cam_id][name] = buf.tobytes()


def get_cv_window() -> bool:
    """main.py เรียกเพื่อตรวจว่าควรแสดง cv2.imshow ไหม"""
    return _cv_window


def set_cv_window(val: bool):
    """ตั้งค่า cv_window flag (เรียกจาก main ก่อน spawn threads)"""
    global _cv_window
    _cv_window = val


def set_active_cam(cam_id: str):
    """เปลี่ยนกล้อง default สำหรับ legacy endpoints"""
    global _active_cam
    _active_cam = cam_id


# ─── FastAPI app ──────────────────────────────────────────────────────────────
app = FastAPI(title="FaceReg", docs_url=None)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["*"],
)


async def _mjpeg_gen(cam_id: str):
    prev_count = -1
    while True:
        with _lock:
            jpeg  = _cam_frames.get(cam_id)
            count = _cam_counts.get(cam_id, 0)
        if jpeg and count != prev_count:
            prev_count = count
            yield (
                b'--frame\r\n'
                b'Content-Type: image/jpeg\r\n\r\n'
                + jpeg +
                b'\r\n'
            )
        else:
            await asyncio.sleep(0.01)


# ─── Per-camera endpoints ─────────────────────────────────────────────────────

@app.get('/cameras')
async def cameras_list():
    """List camera IDs ที่ push frame มาแล้ว"""
    with _lock:
        ids = list(_cam_frames.keys())
    return {"cameras": ids, "active": _active_cam}


@app.post('/cameras/{cam_id}/activate')
async def activate_cam(cam_id: str):
    """เปลี่ยนกล้อง active สำหรับ legacy endpoints"""
    global _active_cam
    with _lock:
        known = list(_cam_frames.keys())
    if cam_id not in known:
        return Response(status_code=404, content=f"cam_id '{cam_id}' ไม่พบ")
    _active_cam = cam_id
    print(f'[STREAM] Active cam → {cam_id}')
    return {"active": _active_cam}


# ─── Camera Config CRUD ───────────────────────────────────────────────────────

@app.get('/cameras/config')
async def get_cameras_config():
    """รายการกล้องทั้งหมดจาก cameras.json (รวมสถานะ active, URL masked)"""
    configs = _load_cam_configs()
    with _lock:
        active_ids = set(_cam_frames.keys())
    result = []
    for c in configs:
        entry = {**c, "active": c.get("id", "") in active_ids}
        if "url" in entry:
            entry["url"] = _mask_url(entry["url"])
        result.append(entry)
    return {"cameras": result}


@app.post('/cameras/config')
async def add_camera(req: CameraConfigRequest):
    """เพิ่มกล้องใหม่ — ID เรียงต่ออัตโนมัติ (cam1, cam2, ...)"""
    if not req.name.strip():
        return Response(status_code=400, content="ต้องระบุชื่อกล้อง")

    configs = _load_cam_configs()   # อาจ fallback จาก config.CAMERAS ถ้ายังไม่มี JSON

    cam_id  = _next_cam_id(configs)
    new_cam: dict = {"id": cam_id, "name": req.name.strip(), "flip": req.flip}

    if req.cam_type == "ip":
        new_cam["url"] = (req.url or "").strip()
    else:
        new_cam["index"] = req.index if req.index is not None else 0

    configs.append(new_cam)
    _save_cam_configs(configs)
    print(f"[CAM_MGR] เพิ่มกล้อง {cam_id} ({req.name})")
    return {"success": True, "camera": new_cam}


@app.put('/cameras/config/{cam_id}')
async def update_camera(cam_id: str, req: CameraConfigRequest):
    """แก้ไข config กล้อง — ต้อง restart ระบบเพื่อให้มีผล"""
    if not req.name.strip():
        return Response(status_code=400, content="ต้องระบุชื่อกล้อง")

    configs = _load_cam_configs()
    for i, c in enumerate(configs):
        if c.get("id") == cam_id:
            updated: dict = {"id": cam_id, "name": req.name.strip(), "flip": req.flip}
            if req.cam_type == "ip":
                updated["url"]   = (req.url or "").strip()
            else:
                updated["index"] = req.index if req.index is not None else 0
            configs[i] = updated
            _save_cam_configs(configs)
            print(f"[CAM_MGR] แก้ไขกล้อง {cam_id}")
            return {"success": True, "camera": updated}

    return Response(status_code=404, content=f"cam_id '{cam_id}' ไม่พบ")


@app.delete('/cameras/config/{cam_id}')
async def delete_camera(cam_id: str):
    """ลบกล้องออกจาก cameras.json — ต้อง restart ระบบเพื่อให้มีผล"""
    configs = _load_cam_configs()
    new_configs = [c for c in configs if c.get("id") != cam_id]
    if len(new_configs) == len(configs):
        return Response(status_code=404, content=f"cam_id '{cam_id}' ไม่พบ")
    _save_cam_configs(new_configs)
    print(f"[CAM_MGR] ลบกล้อง {cam_id}")
    return {"success": True, "deleted": cam_id}


@app.get('/admin', response_class=Response)
async def admin_page():
    """หน้า GUI จัดการกล้อง — http://localhost:8001/admin"""
    html = r"""<!DOCTYPE html>
<html lang="th">
<head>
  <meta charset="UTF-8">
  <title>FaceReg — Camera Manager</title>
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <style>
    *{box-sizing:border-box;margin:0;padding:0}
    body{background:#0d0d0d;color:#e0e0e0;font-family:'Segoe UI',sans-serif;min-height:100vh}
    /* ─── Header ─── */
    .hdr{display:flex;align-items:center;gap:14px;padding:18px 24px;
         border-bottom:1px solid #1e1e1e;background:#111}
    .hdr-title{font-size:17px;font-weight:600;color:#fff;letter-spacing:.4px}
    .hdr-sub{font-size:12px;color:#555;font-family:monospace}
    .hdr-right{margin-left:auto;display:flex;gap:10px;align-items:center}
    /* ─── Notice ─── */
    .notice{background:#1a1200;border:1px solid #403000;border-radius:6px;
            padding:10px 16px;font-size:12px;color:#c8a000;margin:20px 24px 0}
    /* ─── Grid ─── */
    .grid{display:flex;flex-wrap:wrap;gap:16px;padding:20px 24px}
    /* ─── Camera Card ─── */
    .card{background:#141414;border:1px solid #252525;border-radius:10px;
          overflow:hidden;width:300px;flex-shrink:0;transition:border-color .2s}
    .card:hover{border-color:#333}
    .card.online{border-color:#1a4a1a}
    /* snapshot area */
    .snap-wrap{position:relative;height:160px;background:#0a0a0a;overflow:hidden}
    .snap-wrap img{width:100%;height:100%;object-fit:cover;display:block}
    .snap-wrap .no-snap{display:flex;align-items:center;justify-content:center;
                        height:100%;color:#333;font-size:12px;font-family:monospace}
    .cam-id-badge{position:absolute;top:8px;left:8px;background:rgba(0,0,0,.75);
                  color:#ccc;font-size:10px;font-family:monospace;padding:3px 8px;
                  border-radius:4px}
    .status-dot{position:absolute;top:10px;right:10px;width:10px;height:10px;
                border-radius:50%;background:#333;border:2px solid #222}
    .status-dot.online{background:#22cc44;border-color:#166626}
    /* card body */
    .card-body{padding:12px 14px}
    .cam-name{font-size:14px;font-weight:600;color:#fff;margin-bottom:4px;
              white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
    .cam-meta{font-size:11px;color:#555;font-family:monospace;margin-bottom:10px;
              white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
    .cam-meta span{color:#888}
    .card-actions{display:flex;gap:8px}
    /* ─── Buttons ─── */
    .btn{border:none;border-radius:5px;font-size:12px;font-weight:500;
         cursor:pointer;padding:6px 14px;transition:opacity .15s}
    .btn:hover{opacity:.8}
    .btn-primary{background:#00a8cc;color:#000}
    .btn-secondary{background:#252525;color:#aaa;border:1px solid #333}
    .btn-danger{background:#3a0a0a;color:#e05050;border:1px solid #5a1515}
    .btn-success{background:#0a2a18;color:#44cc77;border:1px solid #1a5a35}
    .btn-add{background:#004a66;color:#00d4ff;border:1px solid #006688;
             font-size:13px;padding:8px 20px;border-radius:6px}
    .stream-link{color:#00aacc;font-size:11px;text-decoration:none;font-family:monospace}
    .stream-link:hover{text-decoration:underline}
    /* ─── Modal ─── */
    .modal-bg{display:none;position:fixed;inset:0;background:rgba(0,0,0,.7);
              z-index:100;align-items:center;justify-content:center}
    .modal-bg.open{display:flex}
    .modal{background:#161616;border:1px solid #2a2a2a;border-radius:12px;
           padding:28px;width:420px;max-width:95vw}
    .modal h2{font-size:15px;font-weight:600;margin-bottom:20px;color:#fff}
    .form-row{margin-bottom:14px}
    .form-row label{display:block;font-size:11px;color:#777;margin-bottom:5px;
                    font-family:monospace;text-transform:uppercase;letter-spacing:.5px}
    .form-row input,.form-row select{
      width:100%;background:#0d0d0d;border:1px solid #2a2a2a;border-radius:5px;
      padding:8px 10px;color:#e0e0e0;font-size:13px;font-family:monospace;outline:none}
    .form-row input:focus,.form-row select:focus{border-color:#00a8cc}
    .form-row select option{background:#161616}
    .type-row{display:flex;gap:16px}
    .type-row label{display:flex;align-items:center;gap:6px;cursor:pointer;
                    font-size:13px;color:#bbb;font-family:monospace;
                    text-transform:none;letter-spacing:0}
    .flip-row{display:flex;align-items:center;gap:8px;font-size:13px;color:#bbb}
    .flip-row input[type=checkbox]{width:16px;height:16px;cursor:pointer;accent-color:#00a8cc}
    .modal-actions{display:flex;gap:10px;margin-top:22px;justify-content:flex-end}
    /* ─── Toast ─── */
    .toast{position:fixed;bottom:24px;right:24px;padding:10px 18px;border-radius:6px;
           font-size:13px;font-family:monospace;z-index:200;display:none;
           transition:opacity .3s}
    .toast.ok{background:#00a844;color:#fff}
    .toast.err{background:#cc2222;color:#fff}
    /* ─── Empty state ─── */
    .empty{color:#333;font-family:monospace;font-size:13px;padding:40px 24px}
  </style>
</head>
<body>

<div class="hdr">
  <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#00aacc" stroke-width="1.8">
    <circle cx="12" cy="12" r="3"/><path d="M2 12h3M19 12h3M12 2v3M12 19v3"/>
    <rect x="4" y="7" width="16" height="10" rx="2" stroke="#00aacc" stroke-width="1.5" fill="none"/>
  </svg>
  <div>
    <div class="hdr-title">Camera Manager</div>
    <div class="hdr-sub">FaceReg — จัดการกล้องผ่าน GUI</div>
  </div>
  <div class="hdr-right">
    <button class="btn btn-add" onclick="openAdd()">+ เพิ่มกล้อง</button>
  </div>
</div>

<div class="notice">
  ⚠&nbsp; การเพิ่ม / แก้ไข / ลบกล้อง จะมีผลหลัง <strong>restart ระบบ</strong> เท่านั้น
</div>

<div class="grid" id="grid">
  <div class="empty">กำลังโหลด...</div>
</div>

<!-- ─── Modal: Add / Edit ─── -->
<div class="modal-bg" id="modal-bg">
  <div class="modal">
    <h2 id="modal-title">เพิ่มกล้องใหม่</h2>

    <div class="form-row">
      <label>ชื่อกล้อง (Camera Name)</label>
      <input id="f-name" type="text" placeholder="เช่น CAM_ENTRANCE" maxlength="40">
    </div>

    <div class="form-row">
      <label>ประเภทกล้อง</label>
      <div class="type-row">
        <label><input type="radio" name="cam-type" value="usb" checked onchange="typeChange()"> USB Webcam</label>
        <label><input type="radio" name="cam-type" value="ip" onchange="typeChange()"> IP Camera (RTSP/HTTP)</label>
      </div>
    </div>

    <div class="form-row" id="row-index">
      <label>USB Index (0, 1, 2 ...)</label>
      <input id="f-index" type="number" value="0" min="0" max="20">
    </div>

    <div class="form-row" id="row-url" style="display:none">
      <label>RTSP / HTTP URL</label>
      <input id="f-url" type="text" placeholder="rtsp://admin:pass@192.168.1.x:554/stream">
    </div>

    <div class="form-row">
      <label>&nbsp;</label>
      <div class="flip-row">
        <input type="checkbox" id="f-flip">
        <span>กลับภาพซ้าย-ขวา (Flip Horizontal)</span>
      </div>
    </div>

    <div class="modal-actions">
      <button class="btn btn-secondary" onclick="closeModal()">ยกเลิก</button>
      <button class="btn btn-primary" onclick="saveCamera()">บันทึก</button>
    </div>
  </div>
</div>

<div class="toast" id="toast"></div>

<script>
let _editId = null   // null = add mode, string = edit mode
let _refreshTimer = null

/* ─── Load & render cameras ─── */
async function loadCameras() {
  const res = await fetch('/cameras/config')
  if (!res.ok) { showToast('โหลดข้อมูลไม่ได้', 'err'); return }
  const data = await res.json()
  renderGrid(data.cameras)
}

function renderGrid(cameras) {
  const grid = document.getElementById('grid')
  if (!cameras || cameras.length === 0) {
    grid.innerHTML = '<div class="empty">ยังไม่มีกล้อง — กด "+ เพิ่มกล้อง" เพื่อเริ่มต้น</div>'
    return
  }

  grid.innerHTML = cameras.map(c => {
    const isOnline = c.active
    const dotCls   = isOnline ? 'status-dot online' : 'status-dot'
    const cardCls  = isOnline ? 'card online' : 'card'

    // type label
    let typeMeta = ''
    if (c.url !== undefined && c.url !== '') {
      const short = c.url.length > 36 ? c.url.slice(0,33)+'...' : c.url
      typeMeta = `IP: <span>${short}</span>`
    } else if (c.index !== undefined) {
      typeMeta = `USB index: <span>${c.index}</span>`
    } else if (c.url === '') {
      typeMeta = `IP: <span>(ยังไม่ได้ตั้ง URL)</span>`
    }
    const flipMeta = c.flip ? '&nbsp;&nbsp;Flip: <span>✓</span>' : '&nbsp;&nbsp;Flip: <span>✗</span>'

    const snap = isOnline
      ? `<img id="snap-${c.id}" src="/snapshot/${c.id}?t=${Date.now()}"
             onerror="this.style.display='none';this.nextElementSibling.style.display='flex'">`
      : ''
    const noSnap = `<div class="no-snap" style="${isOnline?'display:none':''}">ไม่มีสัญญาณ</div>`

    return `
    <div class="${cardCls}" id="card-${c.id}">
      <div class="snap-wrap">
        ${snap}${noSnap}
        <div class="cam-id-badge">${c.id}</div>
        <div class="${dotCls}" title="${isOnline?'กำลังทำงาน':'ออฟไลน์'}"></div>
      </div>
      <div class="card-body">
        <div class="cam-name" title="${c.name}">${c.name}</div>
        <div class="cam-meta">${typeMeta}${flipMeta}</div>
        <div class="card-actions">
          <a class="stream-link" href="/stream/${c.id}" target="_blank">/stream/${c.id} ↗</a>
          <button class="btn btn-secondary" style="margin-left:auto"
                  onclick="openEdit('${c.id}')">แก้ไข</button>
          <button class="btn btn-danger"
                  onclick="deleteCamera('${c.id}','${c.name}')">ลบ</button>
        </div>
      </div>
    </div>`
  }).join('')
}

/* ─── Snapshot refresh (active cams only) ─── */
function refreshSnaps() {
  document.querySelectorAll('img[id^="snap-"]').forEach(img => {
    const base = img.src.split('?')[0]
    img.src = base + '?t=' + Date.now()
  })
}
setInterval(refreshSnaps, 2500)
setInterval(loadCameras, 5000)   // sync status dots ทุก 5 วิ

/* ─── Type toggle ─── */
function typeChange() {
  const val = document.querySelector('input[name="cam-type"]:checked').value
  document.getElementById('row-index').style.display = val==='usb' ? '' : 'none'
  document.getElementById('row-url').style.display   = val==='ip'  ? '' : 'none'
}

/* ─── Open Add modal ─── */
function openAdd() {
  _editId = null
  document.getElementById('modal-title').textContent = 'เพิ่มกล้องใหม่'
  document.getElementById('f-name').value  = ''
  document.getElementById('f-index').value = '0'
  document.getElementById('f-url').value   = ''
  document.getElementById('f-flip').checked = false
  document.querySelectorAll('input[name="cam-type"]')[0].checked = true
  typeChange()
  document.getElementById('modal-bg').classList.add('open')
  document.getElementById('f-name').focus()
}

/* ─── Open Edit modal ─── */
async function openEdit(camId) {
  const res   = await fetch('/cameras/config')
  const data  = await res.json()
  const cam   = data.cameras.find(c => c.id === camId)
  if (!cam) return

  _editId = camId
  document.getElementById('modal-title').textContent = `แก้ไขกล้อง — ${camId}`
  document.getElementById('f-name').value   = cam.name  || ''
  document.getElementById('f-flip').checked = cam.flip  || false

  const isIP = cam.url !== undefined
  document.querySelectorAll('input[name="cam-type"]').forEach(r => {
    r.checked = (r.value === (isIP ? 'ip' : 'usb'))
  })
  document.getElementById('f-url').value   = cam.url   || ''
  document.getElementById('f-index').value = cam.index !== undefined ? cam.index : 0
  typeChange()
  document.getElementById('modal-bg').classList.add('open')
  document.getElementById('f-name').focus()
}

function closeModal() {
  document.getElementById('modal-bg').classList.remove('open')
}

/* ─── Save (Add or Edit) ─── */
async function saveCamera() {
  const name     = document.getElementById('f-name').value.trim()
  const cam_type = document.querySelector('input[name="cam-type"]:checked').value
  const url      = document.getElementById('f-url').value.trim()
  const index    = parseInt(document.getElementById('f-index').value) || 0
  const flip     = document.getElementById('f-flip').checked

  if (!name) { showToast('กรุณาระบุชื่อกล้อง', 'err'); return }

  const body = JSON.stringify({name, cam_type, url, index, flip})
  const endpoint = _editId ? `/cameras/config/${_editId}` : '/cameras/config'
  const method   = _editId ? 'PUT' : 'POST'

  const res = await fetch(endpoint, {
    method, headers: {'Content-Type':'application/json'}, body
  })
  if (!res.ok) {
    const msg = await res.text()
    showToast('เกิดข้อผิดพลาด: '+msg, 'err')
    return
  }
  closeModal()
  showToast(_editId ? `แก้ไขกล้อง ${_editId} แล้ว` : 'เพิ่มกล้องใหม่แล้ว', 'ok')
  loadCameras()
}

/* ─── Delete ─── */
async function deleteCamera(camId, camName) {
  if (!confirm(`ลบกล้อง "${camName}" (${camId})?\n\nกล้องจะถูกลบออกจากระบบ — ต้อง restart เพื่อให้มีผล`)) return

  const res = await fetch(`/cameras/config/${camId}`, {method:'DELETE'})
  if (!res.ok) {
    showToast('ลบไม่ได้: '+camId, 'err')
    return
  }
  showToast(`ลบกล้อง ${camId} แล้ว`, 'ok')
  loadCameras()
}

/* ─── Toast ─── */
function showToast(msg, type='ok') {
  const t = document.getElementById('toast')
  t.textContent = msg
  t.className   = `toast ${type}`
  t.style.display = 'block'
  setTimeout(() => t.style.display='none', 3000)
}

/* ─── Close modal on backdrop click ─── */
document.getElementById('modal-bg').addEventListener('click', e => {
  if (e.target === document.getElementById('modal-bg')) closeModal()
})

/* ─── ESC key ─── */
document.addEventListener('keydown', e => {
  if (e.key === 'Escape') closeModal()
})

// initial load
loadCameras()
</script>
</body>
</html>"""
    return Response(content=html, media_type="text/html; charset=utf-8")


@app.get('/stream/{cam_id}')
async def stream_cam(cam_id: str):
    return StreamingResponse(
        _mjpeg_gen(cam_id),
        media_type='multipart/x-mixed-replace; boundary=frame',
    )


@app.get('/snapshot/{cam_id}')
async def snapshot_cam(cam_id: str):
    with _lock:
        jpeg = _cam_frames.get(cam_id)
    if jpeg is None:
        return Response(status_code=503)
    return Response(content=jpeg, media_type='image/jpeg')


@app.get('/state/{cam_id}')
async def state_cam(cam_id: str):
    with _lock:
        s = dict(_cam_states.get(cam_id, {}))
    return s


@app.get('/snap/{cam_id}/{name}')
async def snap_person_cam(cam_id: str, name: str):
    with _lock:
        jpeg = _cam_snaps.get(cam_id, {}).get(name)
    if jpeg is None:
        return Response(status_code=404)
    return Response(content=jpeg, media_type='image/jpeg')


# ─── Legacy single-cam endpoints (→ cam1) ────────────────────────────────────

@app.get('/stream')
async def stream():
    return StreamingResponse(
        _mjpeg_gen(_active_cam),
        media_type='multipart/x-mixed-replace; boundary=frame',
    )


@app.get('/snapshot')
async def snapshot():
    with _lock:
        jpeg = _cam_frames.get(_active_cam)
    if jpeg is None:
        return Response(status_code=503)
    return Response(content=jpeg, media_type='image/jpeg')


@app.get('/status')
async def status():
    with _lock:
        jpeg  = _cam_frames.get(_active_cam)
        count = _cam_counts.get(_active_cam, 0)
    return {"ready": jpeg is not None, "frames_pushed": count}


@app.get('/state')
async def state_endpoint():
    with _lock:
        s = dict(_cam_states.get(_active_cam, {}))
    return s


@app.get('/snap/{name}')
async def snap_person(name: str):
    with _lock:
        jpeg = _cam_snaps.get(_active_cam, {}).get(name)
    if jpeg is None:
        return Response(status_code=404)
    return Response(content=jpeg, media_type='image/jpeg')


@app.get('/window')
async def window_get():
    return {"show_window": _cv_window}


@app.post('/window')
async def window_toggle():
    global _cv_window
    _cv_window = not _cv_window
    print(f'[STREAM] OpenCV window → {"ON" if _cv_window else "OFF"}')
    return {"show_window": _cv_window}


# ─── Start (daemon thread) ────────────────────────────────────────────────────
def start(port: int = 8001):
    def _run():
        uvicorn.run(app, host='0.0.0.0', port=port, log_level='warning')
    t = threading.Thread(target=_run, daemon=True, name='stream-server')
    t.start()
    print(f'[STREAM] Per-cam stream  → http://localhost:{port}/stream/{{cam_id}}')
    print(f'[STREAM] Camera list     → http://localhost:{port}/cameras')
    print(f'[STREAM] Legacy stream   → http://localhost:{port}/stream  (→ active cam)')
    print(f'[STREAM] Camera admin    → http://localhost:{port}/admin')
