-- =============================================================================
-- setup_db.sql — สร้าง FaceReg Database Schema ทั้งหมดตั้งแต่ต้น
-- =============================================================================
-- วิธีใช้ (setup เครื่องใหม่):
--   1. สร้าง DB และ user ก่อน:
--      sudo -u postgres psql -c "CREATE USER face_user WITH PASSWORD '1234';"
--      sudo -u postgres psql -c "CREATE DATABASE face_attendance OWNER face_user;"
--
--   2. รัน script นี้:
--      PGPASSWORD=1234 psql -h localhost -U face_user -d face_attendance -f migrations/setup_db.sql
--
--   3. GRANT ส่วนสุดท้ายต้องรันด้วย postgres superuser:
--      sudo -u postgres psql -d face_attendance -f migrations/setup_db.sql
--      (หรือรัน GRANT commands แยกต่างหาก)
-- =============================================================================


-- ─── 1. attendance_logs ──────────────────────────────────────────────────────

BEGIN;

CREATE TABLE IF NOT EXISTS attendance_logs (
    id          SERIAL          PRIMARY KEY,
    per_id      VARCHAR(20)     NOT NULL,
    status      VARCHAR(10)     NOT NULL,
    camera_name VARCHAR(50)     DEFAULT '',
    check_time  TIMESTAMP       DEFAULT CURRENT_TIMESTAMP,
    name        VARCHAR(200),
    organize_th VARCHAR(200),
    prename_th  VARCHAR(100),
    per_name    VARCHAR(100),
    per_surname VARCHAR(100),
    posname_th  VARCHAR(200),
    organize_id VARCHAR(20)
);

CREATE INDEX IF NOT EXISTS idx_attendance_per_id    ON attendance_logs (per_id);
CREATE INDEX IF NOT EXISTS idx_attendance_date      ON attendance_logs (DATE(check_time));
CREATE INDEX IF NOT EXISTS idx_attendance_code_date ON attendance_logs (per_id, check_time);

COMMIT;


-- ─── 2. users ────────────────────────────────────────────────────────────────

BEGIN;

CREATE TABLE IF NOT EXISTS users (
    id                   SERIAL       PRIMARY KEY,
    username             VARCHAR(64)  UNIQUE NOT NULL,
    password_hash        VARCHAR(255) NOT NULL,
    role                 VARCHAR(16)  NOT NULL CHECK (role IN ('admin', 'viewer')),
    created_at           TIMESTAMP    NOT NULL DEFAULT NOW(),
    last_login           TIMESTAMP,
    must_change_password BOOLEAN      NOT NULL DEFAULT FALSE
);

CREATE INDEX IF NOT EXISTS idx_users_username ON users (username);

COMMIT;


-- ─── 3. audit_logs ───────────────────────────────────────────────────────────

BEGIN;

CREATE TABLE IF NOT EXISTS audit_logs (
    id         BIGSERIAL    PRIMARY KEY,
    ts         TIMESTAMP    NOT NULL DEFAULT NOW(),
    user_id    INTEGER      REFERENCES users(id) ON DELETE SET NULL,
    username   VARCHAR(64),
    action     VARCHAR(64)  NOT NULL,
    target     VARCHAR(255),
    ip         VARCHAR(45),
    user_agent VARCHAR(255),
    details    JSONB,
    success    BOOLEAN      NOT NULL DEFAULT TRUE
);

CREATE INDEX IF NOT EXISTS idx_audit_ts     ON audit_logs (ts DESC);
CREATE INDEX IF NOT EXISTS idx_audit_user   ON audit_logs (user_id);
CREATE INDEX IF NOT EXISTS idx_audit_action ON audit_logs (action);

COMMIT;


-- ─── 4. GRANT permissions ─────────────────────────────────────────────────────
-- ต้องรันด้วย postgres superuser (sudo -u postgres psql ...)

GRANT SELECT, INSERT, UPDATE, DELETE ON attendance_logs        TO face_user;
GRANT USAGE, SELECT ON SEQUENCE       attendance_logs_id_seq   TO face_user;

GRANT SELECT, INSERT, UPDATE, DELETE ON users                  TO face_user;
GRANT USAGE, SELECT ON SEQUENCE       users_id_seq             TO face_user;

GRANT SELECT, INSERT ON               audit_logs               TO face_user;
GRANT USAGE, SELECT ON SEQUENCE       audit_logs_id_seq        TO face_user;
