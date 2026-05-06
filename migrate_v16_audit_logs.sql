-- migrate_v16_audit_logs.sql — ตาราง audit_logs สำหรับบันทึกเหตุการณ์ระบบ
-- รัน: sudo -u postgres psql -d face_attendance -f migrate_v16_audit_logs.sql
-- =====================================================================

BEGIN;

CREATE TABLE IF NOT EXISTS audit_logs (
    id          BIGSERIAL PRIMARY KEY,
    ts          TIMESTAMP    NOT NULL DEFAULT NOW(),
    user_id     INTEGER      REFERENCES users(id) ON DELETE SET NULL,
    username    VARCHAR(64),                                 -- denormalize เพื่อให้อ่านได้ถ้า user ถูกลบ
    action      VARCHAR(64)  NOT NULL,                       -- เช่น "auth.login.success", "camera.create"
    target      VARCHAR(255),                                -- entity ที่ถูกแอ๊กชัน — "cam2", "log_id=123"
    ip          VARCHAR(45),                                 -- IPv6 max 45 chars
    user_agent  VARCHAR(255),
    details     JSONB,                                       -- context อื่นๆ (free-form)
    success     BOOLEAN      NOT NULL DEFAULT TRUE
);

CREATE INDEX IF NOT EXISTS idx_audit_ts     ON audit_logs (ts DESC);
CREATE INDEX IF NOT EXISTS idx_audit_user   ON audit_logs (user_id);
CREATE INDEX IF NOT EXISTS idx_audit_action ON audit_logs (action);

-- ให้สิทธิ์ face_user (ระบบเขียน + อ่านผ่าน /audit/logs)
GRANT SELECT, INSERT ON audit_logs TO face_user;
GRANT USAGE, SELECT  ON SEQUENCE audit_logs_id_seq TO face_user;

COMMIT;

SELECT column_name, data_type
FROM   information_schema.columns
WHERE  table_name = 'audit_logs'
ORDER  BY ordinal_position;
