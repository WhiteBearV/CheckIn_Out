"""
stream_server.py — MJPEG streaming + JSON state API (Multi-Camera)
====================================================
Endpoints (per-camera):
  GET  /cameras              → list camera IDs ที่ active
  GET  /stream/{cam_id}      → MJPEG video stream
  GET  /snapshot/{cam_id}    → ภาพเดี่ยว JPEG
  GET  /state/{cam_id}       → JSON state สำหรับ canvas overlay
  GET  /snap/{cam_id}/{name} → thumbnail หน้าคนใน panel

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
import threading
import cv2
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, Response
import uvicorn

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
    allow_methods=["GET", "POST"],
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


@app.get('/admin', response_class=Response)
async def admin_page():
    """หน้า GUI เลือกกล้อง — เปิดได้ที่ http://localhost:8001/admin"""
    with _lock:
        ids    = list(_cam_frames.keys())
        active = _active_cam

    cam_cards = ""
    for cid in ids:
        border = "border:2px solid #00ffff;" if cid == active else "border:2px solid #333;"
        badge  = '<span style="background:#00ffff;color:#000;font-size:10px;padding:2px 6px;border-radius:3px;font-weight:700;">ACTIVE</span>' if cid == active else ""
        cam_cards += f"""
        <div onclick="activate('{cid}')" id="card-{cid}"
             style="cursor:pointer;background:#111;{border}border-radius:8px;overflow:hidden;
                    width:320px;flex-shrink:0;transition:border .2s;">
          <div style="position:relative;">
            <img id="img-{cid}" src="/snapshot/{cid}" style="width:100%;height:180px;object-fit:cover;display:block;"
                 onerror="this.style.background='#1a1a1a';this.alt='offline';" />
            <div style="position:absolute;top:8px;left:8px;font-family:monospace;font-size:11px;
                        background:rgba(0,0,0,.7);color:#fff;padding:3px 8px;border-radius:4px;">
              {cid}
            </div>
            <div id="badge-{cid}" style="position:absolute;top:8px;right:8px;">{badge}</div>
          </div>
          <div style="padding:10px 12px;font-family:monospace;font-size:12px;color:#aaa;">
            <a href="/stream/{cid}" target="_blank"
               style="color:#00ffff;text-decoration:none;" onclick="event.stopPropagation()">
              /stream/{cid} ↗
            </a>
          </div>
        </div>"""

    if not ids:
        cam_cards = '<p style="color:#555;font-family:monospace;">ยังไม่มีกล้อง — รัน main.py ก่อน</p>'

    html = f"""<!DOCTYPE html>
<html lang="th">
<head>
  <meta charset="UTF-8">
  <title>FaceReg — Camera Admin</title>
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <style>
    *{{box-sizing:border-box;margin:0;padding:0}}
    body{{background:#0a0a0a;color:#fff;font-family:sans-serif;padding:24px}}
    h1{{font-size:20px;font-weight:300;margin-bottom:4px}}
    .sub{{color:#555;font-size:13px;font-family:monospace;margin-bottom:24px}}
    .row{{display:flex;gap:16px;flex-wrap:wrap;align-items:flex-start}}
    .toast{{position:fixed;bottom:24px;right:24px;background:#00ffff;color:#000;
            padding:10px 18px;border-radius:6px;font-family:monospace;font-size:13px;
            display:none;z-index:99}}
  </style>
</head>
<body>
  <h1>Camera Admin</h1>
  <p class="sub">คลิกที่กล้องเพื่อตั้งเป็น active (legacy /stream, /state, /snap)</p>
  <div class="row">{cam_cards}</div>
  <div class="toast" id="toast"></div>
  <script>
    // refresh snapshots ทุก 2 วิ
    setInterval(()=>{{
      document.querySelectorAll('img[id^="img-"]').forEach(img=>{{
        const base = img.src.split('?')[0]
        img.src = base + '?t=' + Date.now()
      }})
    }}, 2000)

    async function activate(camId){{
      const r = await fetch('/cameras/'+camId+'/activate',{{method:'POST'}})
      if(!r.ok){{ alert('เปิดไม่ได้: '+camId); return }}
      // update border + badge ทุก card
      document.querySelectorAll('[id^="card-"]').forEach(el=>{{
        el.style.border = '2px solid #333'
      }})
      document.querySelectorAll('[id^="badge-"]').forEach(el=>{{
        el.innerHTML = ''
      }})
      document.getElementById('card-'+camId).style.border = '2px solid #00ffff'
      document.getElementById('badge-'+camId).innerHTML =
        '<span style="background:#00ffff;color:#000;font-size:10px;padding:2px 6px;border-radius:3px;font-weight:700;">ACTIVE</span>'

      const t = document.getElementById('toast')
      t.textContent = 'Active → '+camId
      t.style.display='block'
      setTimeout(()=>t.style.display='none', 2000)
    }}
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
