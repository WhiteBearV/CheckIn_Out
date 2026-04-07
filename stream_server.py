"""
stream_server.py — MJPEG streaming server (รันใน background thread ภายใน main.py)
====================================================================================
เปิดดูได้ที่: http://localhost:8001/stream
             http://localhost:8001/snapshot  ← ภาพเดี่ยว JPEG

วิธีใช้:
  import stream_server
  stream_server.start()        # เรียกครั้งเดียวก่อน main loop
  stream_server.push_frame(frame)  # เรียกทุก frame
"""

import asyncio
import threading
import cv2
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
import uvicorn

# ─── Shared frame buffer (thread-safe) ───────────────────────────────────────
_lock:        threading.Lock = threading.Lock()
_latest_jpeg: bytes | None   = None
_frame_count: int             = 0


def push_frame(frame, quality: int = 70):
    """
    เรียกจาก main loop หลัง draw ทุก frame (thread-safe)
    frame: numpy array BGR (ขนาดอะไรก็ได้)
    """
    global _latest_jpeg, _frame_count
    ok, buf = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, quality])
    if not ok:
        return
    with _lock:
        _latest_jpeg = buf.tobytes()
        _frame_count += 1


# ─── FastAPI app ──────────────────────────────────────────────────────────────
app = FastAPI(title="FaceReg Stream", docs_url=None)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)


async def _mjpeg_gen():
    """Async generator สำหรับ MJPEG stream — polling non-blocking"""
    prev_count = -1
    while True:
        with _lock:
            jpeg  = _latest_jpeg
            count = _frame_count
        if jpeg and count != prev_count:
            prev_count = count
            yield (
                b'--frame\r\n'
                b'Content-Type: image/jpeg\r\n\r\n'
                + jpeg +
                b'\r\n'
            )
        else:
            await asyncio.sleep(0.01)   # 100 Hz polling (non-blocking)


@app.get('/stream')
async def stream():
    """MJPEG stream — ใช้กับ <img src="/stream"> ในเว็บ"""
    return StreamingResponse(
        _mjpeg_gen(),
        media_type='multipart/x-mixed-replace; boundary=frame',
    )


@app.get('/snapshot')
async def snapshot():
    """ดึงภาพปัจจุบัน 1 ใบ (JPEG) — ใช้เมื่อต้องการ static image"""
    with _lock:
        jpeg = _latest_jpeg
    if jpeg is None:
        return StreamingResponse(iter([b'']), media_type='image/jpeg', status_code=503)
    return StreamingResponse(iter([jpeg]), media_type='image/jpeg')


@app.get('/status')
async def status():
    """ตรวจว่า stream พร้อมหรือยัง"""
    with _lock:
        ready = _latest_jpeg is not None
        count = _frame_count
    return {"ready": ready, "frames_pushed": count}


# ─── Start (daemon thread) ───────────────────────────────────────────────────
def start(port: int = 8001):
    """
    เรียกครั้งเดียวก่อน main loop — เปิด server ใน daemon thread
    ปิดอัตโนมัติเมื่อ main process ตาย
    """
    def _run():
        uvicorn.run(
            app,
            host='0.0.0.0',
            port=port,
            log_level='warning',
        )
    t = threading.Thread(target=_run, daemon=True, name='stream-server')
    t.start()
    print(f'[STREAM] MJPEG server → http://localhost:{port}/stream')
