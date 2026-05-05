-- migrate_v13_users.sql — เพิ่มตาราง users สำหรับระบบ login
-- รัน: PGPASSWORD=1234 psql -h localhost -U face_user -d face_attendance -f migrate_v13_users.sql
-- =====================================================================

BEGIN;

CREATE TABLE IF NOT EXISTS users (
    id            SERIAL PRIMARY KEY,
    username      VARCHAR(64)  UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    role          VARCHAR(16)  NOT NULL CHECK (role IN ('admin', 'viewer')),
    created_at    TIMESTAMP    NOT NULL DEFAULT NOW(),
    last_login    TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_users_username ON users (username);

COMMIT;

SELECT column_name, data_type
FROM information_schema.columns
WHERE table_name = 'users'
ORDER BY ordinal_position;
