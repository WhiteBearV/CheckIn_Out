-- migrate_v9.sql (ปรับใหม่ — ต่อจากที่ค้างอยู่)
-- สถานะปัจจุบันของ attendance_logs:
--   มี: id, per_id, status, camera_name, check_time, full_name, organize_th
--   ขาด: name, prename_th, per_name, per_surname, posname_th, organize_id
-- รัน: sudo -u postgres psql -d face_attendance -f migrate_v9.sql
-- =====================================================================

BEGIN;

-- ── 1. เปลี่ยนชื่อ full_name → name ────────────────────────────────
ALTER TABLE attendance_logs RENAME COLUMN full_name TO name;

-- ── 2. เพิ่ม columns ที่ยังขาดอยู่ ──────────────────────────────────
ALTER TABLE attendance_logs
    ADD COLUMN IF NOT EXISTS prename_th  VARCHAR(100),
    ADD COLUMN IF NOT EXISTS per_name    VARCHAR(100),
    ADD COLUMN IF NOT EXISTS per_surname VARCHAR(100),
    ADD COLUMN IF NOT EXISTS posname_th  VARCHAR(200),
    ADD COLUMN IF NOT EXISTS organize_id VARCHAR(20);

-- ── 3. rename employees → employees_backup (ถ้า employees ยังมีอยู่) ──
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables
               WHERE table_name = 'employees') THEN
        ALTER TABLE employees RENAME TO employees_backup;
        RAISE NOTICE 'employees → employees_backup';
    ELSE
        RAISE NOTICE 'employees ไม่มีอยู่แล้ว — ข้าม';
    END IF;
END$$;

-- ── 4. index ────────────────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_attendance_per_id
    ON attendance_logs (per_id);

CREATE INDEX IF NOT EXISTS idx_attendance_date
    ON attendance_logs (DATE(check_time));

COMMIT;

-- ตรวจสอบผลลัพธ์
SELECT column_name, data_type
FROM information_schema.columns
WHERE table_name = 'attendance_logs'
ORDER BY ordinal_position;
