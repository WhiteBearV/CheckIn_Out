-- mock_attendance.sql — สร้าง mock data สำหรับทดสอบหน้า /history และ /reports
-- รัน (ทางง่าย — ไม่ต้อง sudo):
--   PGPASSWORD=1234 psql -h localhost -U face_user -d face_attendance -f mock_attendance.sql
-- =====================================================================
-- ลักษณะข้อมูล:
--   • 8 คน 3 หน่วยงาน, ย้อนหลัง 30 วัน (จันทร์–ศุกร์ เท่านั้น)
--   • IN  ช่วง 07:30–09:30, OUT ช่วง 16:30–18:30 (สุ่ม)
--   • ~80% ลงครบ IN+OUT, ~12% IN อย่างเดียว, ~8% OUT อย่างเดียว
--   • กล้อง CAM_FRONT / CAM_BACK / CAM_GATE สุ่ม
--   • SAFE: ใช้ NOT EXISTS — รันซ้ำได้ ไม่ duplicate (ไม่ต้อง DELETE)
--           per_id ขึ้นต้น "9000" → ไม่ชนของจริง
--
-- ★ ถ้าต้องการ "ล้าง + insert ใหม่" (ต้องใช้สิทธิ์ DELETE — รันด้วย postgres):
--   sudo -u postgres psql -d face_attendance -c \
--     "DELETE FROM attendance_logs WHERE per_id LIKE '9000%';"
-- =====================================================================

BEGIN;

-- ── 1. เตรียม person + dept seed ────────────────────────────────────────
WITH persons(per_id, prename_th, per_name, per_surname, posname_th, organize_th, organize_id) AS (
    VALUES
        ('9000000000001', 'นาย',     'สมชาย', 'ใจดี',         'นักวิเคราะห์',     'กองสารสนเทศ',    'ORG01'),
        ('9000000000002', 'นางสาว',  'อรอุมา','ทองพูน',       'นักพัฒนา',         'กองสารสนเทศ',    'ORG01'),
        ('9000000000003', 'นาย',     'ภัทรพล','สายสว่าง',     'หัวหน้าฝ่าย',      'กองสารสนเทศ',    'ORG01'),
        ('9000000000004', 'นาย',     'ธนวัฒน์','ศิริชัย',     'พนักงานบุคคล',    'กองทรัพยากรบุคคล','ORG02'),
        ('9000000000005', 'นางสาว',  'ปิยะดา','รุ่งเรือง',    'พนักงานบัญชี',     'กองการเงิน',     'ORG03'),
        ('9000000000006', 'นาย',     'วีระชัย','ก้อนทอง',     'พนักงานการเงิน',   'กองการเงิน',     'ORG03'),
        ('9000000000007', 'นางสาว',  'สุภาภรณ์','แสงทอง',    'นักวิชาการ',       'กองทรัพยากรบุคคล','ORG02'),
        ('9000000000008', 'นาย',     'กิตติชัย','พงษ์ไพบูลย์','ผู้อำนวยการ',     'กองสารสนเทศ',    'ORG01')
),
-- ── 3. วันทำงาน 30 วันย้อนหลัง (ตัดเสาร์-อาทิตย์) ──────────────────────
work_days AS (
    SELECT d::date AS work_date
    FROM generate_series(CURRENT_DATE - INTERVAL '29 days', CURRENT_DATE, INTERVAL '1 day') d
    WHERE EXTRACT(DOW FROM d) BETWEEN 1 AND 5     -- 1=Mon..5=Fri
),
-- ── 4. ทุก (person, day) — ตัดสินสถานะ pattern ──────────────────────────
plan AS (
    SELECT
        p.*,
        wd.work_date,
        -- สุ่ม pattern: 0..79 = ครบ, 80..91 = IN-only, 92..99 = OUT-only
        (random() * 100)::int                                 AS rnd,
        -- IN time: 07:30 + 0..120 นาที (สุ่ม) → 07:30..09:30
        (work_date + TIME '07:30' + (floor(random()*121)::int || ' minutes')::interval) AS in_ts,
        -- OUT time: 16:30 + 0..120 นาที (สุ่ม) → 16:30..18:30
        (work_date + TIME '16:30' + (floor(random()*121)::int || ' minutes')::interval) AS out_ts,
        -- สุ่มกล้อง
        (ARRAY['CAM_FRONT','CAM_BACK','CAM_GATE'])[1 + (random()*3)::int % 3] AS cam_in,
        (ARRAY['CAM_FRONT','CAM_BACK','CAM_GATE'])[1 + (random()*3)::int % 3] AS cam_out
    FROM persons p
    CROSS JOIN work_days wd
),
-- ── 5. แตกออกเป็น row IN/OUT ────────────────────────────────────────────
in_rows AS (
    SELECT per_id, 'IN' AS status, cam_in AS camera_name, in_ts AS check_time,
           (prename_th || per_name || ' ' || per_surname) AS name,
           prename_th, per_name, per_surname, posname_th, organize_th, organize_id
    FROM plan
    WHERE rnd < 92                       -- ครบ + IN-only
),
out_rows AS (
    SELECT per_id, 'OUT' AS status, cam_out AS camera_name, out_ts AS check_time,
           (prename_th || per_name || ' ' || per_surname) AS name,
           prename_th, per_name, per_surname, posname_th, organize_th, organize_id
    FROM plan
    WHERE rnd < 80 OR rnd >= 92          -- ครบ + OUT-only
)
INSERT INTO attendance_logs
    (per_id, status, camera_name, check_time,
     name, prename_th, per_name, per_surname,
     posname_th, organize_th, organize_id)
SELECT i.* FROM in_rows i
WHERE NOT EXISTS (
    SELECT 1 FROM attendance_logs a
    WHERE a.per_id = i.per_id AND a.status = 'IN'
      AND DATE(a.check_time) = DATE(i.check_time)
)
UNION ALL
SELECT o.* FROM out_rows o
WHERE NOT EXISTS (
    SELECT 1 FROM attendance_logs a
    WHERE a.per_id = o.per_id AND a.status = 'OUT'
      AND DATE(a.check_time) = DATE(o.check_time)
);

COMMIT;

-- ── สรุปผล ──────────────────────────────────────────────────────────────
SELECT
    DATE(check_time) AS d,
    COUNT(*) FILTER (WHERE status = 'IN')  AS ins,
    COUNT(*) FILTER (WHERE status = 'OUT') AS outs,
    COUNT(DISTINCT per_id)                  AS persons
FROM attendance_logs
WHERE per_id LIKE '9000%'
GROUP BY DATE(check_time)
ORDER BY d DESC
LIMIT 10;

SELECT 'Mock data inserted (per_id LIKE 9000%)' AS info,
       COUNT(*) AS total_rows
FROM attendance_logs
WHERE per_id LIKE '9000%';
