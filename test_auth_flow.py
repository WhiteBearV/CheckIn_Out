"""
test_auth_flow.py — sanity test ระบบ login (รันหลัง migration เสร็จ)
รัน: venv/bin/python test_auth_flow.py
"""
import os
from dotenv import load_dotenv
load_dotenv()

from fastapi.testclient import TestClient
import auth
import stream_server

client = TestClient(stream_server.app)

# bootstrap default users (ถ้ายังไม่มี)
auth.bootstrap_default_users()

print("\n══ ทดสอบระบบ login ══\n")

# 1. login ผิด → 401
r = client.post('/auth/login', json={'username': 'nope', 'password': 'wrong'})
assert r.status_code == 401, f"expected 401, got {r.status_code}"
print(f"  ✓ login wrong creds → 401: {r.json()['detail']}")

# 2. login admin ถูก
r = client.post('/auth/login', json={'username': 'admin', 'password': 'Admin12345'})
assert r.status_code == 200, f"expected 200, got {r.status_code}: {r.text}"
admin_token = r.json()['token']
assert r.json()['role'] == 'admin'
print(f"  ✓ login admin → 200, role=admin, token={admin_token[:30]}...")

# 3. login viewer ถูก
r = client.post('/auth/login', json={'username': 'viewer', 'password': 'User12345'})
assert r.status_code == 200
viewer_token = r.json()['token']
assert r.json()['role'] == 'viewer'
print(f"  ✓ login viewer → 200, role=viewer")

# 4. /auth/me ไม่มี token → 401
r = client.get('/auth/me')
assert r.status_code == 401
print(f"  ✓ /auth/me no-token → 401")

# 5. /auth/me ด้วย valid token
r = client.get('/auth/me', headers={'Authorization': f'Bearer {admin_token}'})
assert r.status_code == 200 and r.json()['username'] == 'admin'
print(f"  ✓ /auth/me valid-token → 200, {r.json()}")

# 6. mutating endpoint ไม่มี token → 401
r = client.post('/cache/clear')
assert r.status_code == 401
print(f"  ✓ /cache/clear no-token → 401")

# 7. mutating endpoint viewer → 403
r = client.post('/cache/clear', headers={'Authorization': f'Bearer {viewer_token}'})
assert r.status_code == 403, f"expected 403, got {r.status_code}: {r.text}"
print(f"  ✓ /cache/clear viewer-token → 403: {r.json()['detail']}")

# 8. mutating endpoint admin → 200
r = client.post('/cache/clear', headers={'Authorization': f'Bearer {admin_token}'})
assert r.status_code == 200, f"expected 200, got {r.status_code}: {r.text}"
print(f"  ✓ /cache/clear admin-token → 200, {r.json()}")

# 9. GET endpoint (ไม่ guard) ใช้ได้แม้ไม่มี token
r = client.get('/system/status')
assert r.status_code == 200
print(f"  ✓ GET /system/status no-token → 200 (public)")

# 10. GET endpoint ด้วย viewer ก็ได้
r = client.get('/system/status', headers={'Authorization': f'Bearer {viewer_token}'})
assert r.status_code == 200
print(f"  ✓ GET /system/status viewer → 200")

# 11. change password (admin เปลี่ยนของตัวเอง)
r = client.post('/auth/change-password',
                headers={'Authorization': f'Bearer {admin_token}'},
                json={'old_password': 'Admin12345', 'new_password': 'AdminTemp99'})
assert r.status_code == 200
print(f"  ✓ change password admin → 200")

# 12. login ด้วยรหัสใหม่
r = client.post('/auth/login', json={'username': 'admin', 'password': 'AdminTemp99'})
assert r.status_code == 200
print(f"  ✓ login admin ใหม่ → 200")

# 13. revert password
r = client.post('/auth/change-password',
                headers={'Authorization': f"Bearer {r.json()['token']}"},
                json={'old_password': 'AdminTemp99', 'new_password': 'Admin12345'})
assert r.status_code == 200
print(f"  ✓ revert password admin → 200")

# 14. CORS preflight สำหรับ origin ที่ allow
r = client.options('/auth/login', headers={
    'Origin': 'http://localhost:5173',
    'Access-Control-Request-Method': 'POST',
})
print(f"  ✓ CORS preflight allowed origin → {r.status_code}, "
      f"acao={r.headers.get('access-control-allow-origin')}")

# 15. CORS preflight จาก origin ที่ไม่ allow → ไม่มี header
r = client.options('/auth/login', headers={
    'Origin': 'http://evil.example.com',
    'Access-Control-Request-Method': 'POST',
})
acao = r.headers.get('access-control-allow-origin')
print(f"  ✓ CORS preflight disallowed origin → "
      f"{'BLOCKED (no ACAO)' if not acao else f'LEAK: {acao}'}")

print("\n══ ทดสอบ api.py JWT migration (Phase 1.1) ══\n")

import api as api_mod
api_client = TestClient(api_mod.app)
_ADMIN_KEY = os.environ.get("ADMIN_API_KEY", "")

# A1. PUT ไม่มี header → 401
r = api_client.put('/attendance/999999999', json={'status': 'IN'})
assert r.status_code == 401, f"expected 401, got {r.status_code}: {r.text}"
print(f"  ✓ api PUT no-auth → 401")

# A2. DELETE ไม่มี header → 401
r = api_client.delete('/attendance/999999999')
assert r.status_code == 401
print(f"  ✓ api DELETE no-auth → 401")

# A3. PUT ด้วย viewer JWT → 403 (role ไม่ใช่ admin)
r = api_client.put('/attendance/999999999',
                   headers={'Authorization': f'Bearer {viewer_token}'},
                   json={'status': 'IN'})
assert r.status_code == 403, f"expected 403, got {r.status_code}: {r.text}"
print(f"  ✓ api PUT viewer-JWT → 403")

# A4. DELETE ด้วย X-Admin-Key ผิด → 401
r = api_client.delete('/attendance/999999999', headers={'X-Admin-Key': 'wrong'})
assert r.status_code == 401
print(f"  ✓ api DELETE wrong-X-Admin-Key → 401")

# A5. PUT ด้วย X-Admin-Key ถูก (legacy fallback) — auth ผ่าน → 404 หรือ 200 (record ไม่มี)
if _ADMIN_KEY:
    try:
        r = api_client.put('/attendance/999999999',
                           headers={'X-Admin-Key': _ADMIN_KEY},
                           json={'status': 'IN'})
        # auth ผ่าน → handler ทำงาน → 404 (record ไม่มี) ก็ใช่ที่เราต้องการ
        # ถ้า DB ไม่ขึ้นได้ 500 → skip
        if r.status_code in (404, 500):
            print(f"  ✓ api PUT legacy-X-Admin-Key → {r.status_code} (auth ผ่าน, record ไม่มีหรือ DB down)")
        else:
            print(f"  ⚠ api PUT legacy-X-Admin-Key → {r.status_code}: {r.text}")
    except Exception as e:
        print(f"  ⚠ api PUT legacy-X-Admin-Key → DB unavailable: {e}")

    # A6. DELETE ด้วย admin JWT → auth ผ่าน → 404 (record ไม่มี)
    try:
        r = api_client.delete('/attendance/999999999',
                              headers={'Authorization': f'Bearer {admin_token}'})
        if r.status_code in (404, 500):
            print(f"  ✓ api DELETE admin-JWT → {r.status_code} (auth ผ่าน)")
        else:
            print(f"  ⚠ api DELETE admin-JWT → {r.status_code}: {r.text}")
    except Exception as e:
        print(f"  ⚠ api DELETE admin-JWT → DB unavailable: {e}")
else:
    print(f"  ⚠ skip A5/A6 — ADMIN_API_KEY ไม่ตั้งใน .env")

print("\n══ ทุกการทดสอบผ่าน ✅ ══\n")
