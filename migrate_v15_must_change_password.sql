-- migrate_v15_must_change_password.sql — บังคับเปลี่ยนรหัสผ่านครั้งแรก
-- รัน: PGPASSWORD=1234 psql -h localhost -U face_user -d face_attendance -f migrate_v15_must_change_password.sql
-- =====================================================================

BEGIN;

ALTER TABLE users
    ADD COLUMN IF NOT EXISTS must_change_password BOOLEAN NOT NULL DEFAULT FALSE;

-- default user ที่มีอยู่ตอนนี้ (admin, viewer ที่ใช้ password เริ่มต้น) → บังคับเปลี่ยน
UPDATE users
SET    must_change_password = TRUE
WHERE  username IN ('admin', 'viewer');

COMMIT;

SELECT username, role, must_change_password FROM users ORDER BY id;

