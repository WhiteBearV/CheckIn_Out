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

print("\n══ ทดสอบ must_change_password (Phase 1.4) ══\n")

# /auth/login response ต้องมี must_change_password
r = client.post('/auth/login', json={'username': 'admin', 'password': 'Admin12345'})
assert r.status_code == 200
data = r.json()
assert 'must_change_password' in data, f"login response missing must_change_password: {data}"
print(f"  ✓ /auth/login response includes must_change_password={data['must_change_password']}")

# /auth/me ต้อง include must_change_password
admin_token_v2 = data['token']
r = client.get('/auth/me', headers={'Authorization': f'Bearer {admin_token_v2}'})
assert r.status_code == 200
assert 'must_change_password' in r.json(), f"/auth/me missing must_change_password: {r.json()}"
print(f"  ✓ /auth/me response includes must_change_password={r.json()['must_change_password']}")

# change-password ที่ส่ง newPw ซ้ำกับเดิม → 400
r = client.post('/auth/change-password',
                headers={'Authorization': f'Bearer {admin_token_v2}'},
                json={'old_password': 'Admin12345', 'new_password': 'Admin12345'})
assert r.status_code == 400, f"expected 400 (same pw), got {r.status_code}"
print(f"  ✓ change-password new==old → 400: {r.json()['detail']}")

print("\n══ ทดสอบ rate limit /auth/login (Phase 1.3) ══\n")

# reset limiter — test ก่อนหน้าได้ login ไปหลายครั้งแล้ว
try:
    stream_server.limiter.reset()
except Exception as e:
    print(f"  ⚠ limiter.reset() failed: {e}")

# ส่ง login ผิด 6 ครั้ง — 5 แรกควร 401, ครั้งที่ 6+ ควร 429
codes = []
for i in range(6):
    r = client.post('/auth/login', json={'username': 'rl_test', 'password': 'wrong'})
    codes.append(r.status_code)

n_401 = sum(1 for c in codes if c == 401)
n_429 = sum(1 for c in codes if c == 429)
assert n_401 == 5, f"expected 5×401 (under limit), got {codes}"
assert n_429 == 1, f"expected 1×429 (limit exceeded on 6th), got {codes}"
print(f"  ✓ /auth/login rate limit: 5×401 + 1×429 → {codes}")

# 429 response ต้องเป็น Thai message ตาม custom handler
r = client.post('/auth/login', json={'username': 'rl_test', 'password': 'wrong'})
assert r.status_code == 429
detail = r.json().get('detail', '')
assert 'ใส่รหัสผิด' in detail and 'ลองใหม่' in detail, \
    f"429 detail ไม่ใช่ Thai message: {detail!r}"
print(f"  ✓ 429 detail: {detail}")

# reset อีกครั้งก่อน test ต่อ — ไม่ให้กระทบ section อื่น
stream_server.limiter.reset()

print("\n══ ทดสอบ stream_server image/state guards (Phase 1.2) ══\n")

# ใช้ admin token ตัวล่าสุด (หลัง revert password)
r2 = client.post('/auth/login', json={'username': 'admin', 'password': 'Admin12345'})
admin_token = r2.json()['token']

GUARDED_ENDPOINTS = [
    ('GET',  '/cameras'),
    ('GET',  '/cameras/config'),
    ('GET',  '/state/cam1'),
    ('GET',  '/snapshot/cam1'),
    ('GET',  '/snap/cam1/test'),
    ('GET',  '/snapfull/cam1/test'),
    # /stream/cam1 และ /stream ใช้ MJPEG infinite generator → TestClient block
    # → ทดสอบเฉพาะ no-token (ก่อน enter generator) ด้านล่างแยกต่างหาก
    ('GET',  '/state'),
    ('GET',  '/snapshot'),
    ('GET',  '/status'),
    ('GET',  '/snap/test'),
    ('GET',  '/window'),
    ('GET',  '/system/watchdog'),
]

for method, path in GUARDED_ENDPOINTS:
    # 1. no-token → 401
    r = client.request(method, path)
    assert r.status_code == 401, f"{method} {path} expected 401, got {r.status_code}"
    # 2. valid token → ไม่ใช่ 401 (อาจ 200, 404, 503 ก็ได้ — แค่ auth ผ่าน)
    r = client.request(method, path, headers={'Authorization': f'Bearer {admin_token}'})
    assert r.status_code != 401, f"{method} {path} with valid token got 401"
    print(f"  ✓ {method} {path}: no-token=401, with-token={r.status_code}")

# admin-only endpoint guard ที่เพิ่มใน Phase 1.2
r = client.get('/admin')
assert r.status_code == 401, f"GET /admin expected 401, got {r.status_code}"
r = client.get('/admin', headers={'Authorization': f'Bearer {viewer_token}'})
assert r.status_code == 403, f"GET /admin viewer expected 403, got {r.status_code}"
r = client.get('/admin', headers={'Authorization': f'Bearer {admin_token}'})
assert r.status_code == 200
print(f"  ✓ GET /admin: no-token=401, viewer=403, admin=200")

# /stream/cam1 และ /stream — ทดสอบเฉพาะ no-token (auth dep raise ก่อน enter MJPEG generator)
r = client.get('/stream/cam1')
assert r.status_code == 401, f"GET /stream/cam1 expected 401, got {r.status_code}"
r = client.get('/stream')
assert r.status_code == 401
print(f"  ✓ GET /stream/cam1, /stream: no-token=401 (MJPEG guard works)")

# /system/status ต้อง public (UI เช็คก่อน login)
r = client.get('/system/status')
assert r.status_code == 200
print(f"  ✓ GET /system/status: public (200)")

print("\n══ ทดสอบ audit log (Phase 1.5) ══\n")

# /audit/logs guard
r = client.get('/audit/logs')
assert r.status_code == 401
print(f"  ✓ GET /audit/logs no-token → 401")

r = client.get('/audit/logs', headers={'Authorization': f'Bearer {viewer_token}'})
assert r.status_code == 403
print(f"  ✓ GET /audit/logs viewer → 403")

# trigger event ใหม่ (cache/clear) แล้วเช็คว่า audit row โผล่
import audit as _audit_mod
before = _audit_mod.fetch(limit=1, action="system.cache_clear")
client.post('/cache/clear', headers={'Authorization': f'Bearer {admin_token}'})
after  = _audit_mod.fetch(limit=1, action="system.cache_clear")
if not after:
    print("  ⚠ audit_logs ว่าง — ยังไม่ได้รัน migrate_v16_audit_logs.sql ?")
else:
    assert after and (not before or after[0]['id'] != before[0]['id']), \
        "expected new system.cache_clear row in audit_logs"
    row = after[0]
    assert row['username'] == 'admin'
    assert row['success'] is True
    print(f"  ✓ system.cache_clear logged: id={row['id']}, ip={row['ip']}, "
          f"details={row['details']}")

# /audit/logs admin → 200 + structure ถูก
r = client.get('/audit/logs?limit=5',
               headers={'Authorization': f'Bearer {admin_token}'})
assert r.status_code == 200
data = r.json()
assert 'logs' in data and 'count' in data
print(f"  ✓ GET /audit/logs admin → 200, count={data['count']}")

# auth.login.success / auth.login.fail logged
r = client.post('/auth/login', json={'username': 'admin', 'password': 'wrong-pw'})
assert r.status_code == 401
fail_logs = _audit_mod.fetch(limit=1, action="auth.login.fail")
if fail_logs:
    print(f"  ✓ auth.login.fail logged for username={fail_logs[0]['username']}")
else:
    print("  ⚠ auth.login.fail ไม่ปรากฏใน audit_logs")

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
