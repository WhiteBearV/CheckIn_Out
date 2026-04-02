/**
 * server.js — Express API Server สำหรับระบบ Face Attendance
 * ===========================================================
 * รัน: node server.js
 * หรือ: npm run dev  (auto-reload ด้วย nodemon)
 *
 * Endpoints:
 *   POST   /attendance              — บันทึกเวลา IN/OUT
 *   GET    /attendance/today        — การลงเวลาวันนี้ทั้งหมด
 *   GET    /attendance/today/check  — ตรวจว่า IN/OUT วันนี้แล้วหรือยัง
 *   GET    /attendance/:per_id      — ประวัติลงเวลาของพนักงาน
 *   PUT    /attendance/:log_id      — แก้ไข record ลงเวลา
 *   DELETE /attendance/:log_id      — ลบ record ลงเวลา
 */

const express = require("express");
const pool    = require("./db.js");

const app  = express();
const PORT = process.env.PORT || 8000;

app.use(express.json());

// ── Helper ───────────────────────────────────────────────────────────────────
const query = (text, params) => pool.query(text, params);


// ╔═══════════════════════════════════════════════════════════════════════════╗
// ║  POST /attendance — บันทึกเวลา IN/OUT                                    ║
// ╚═══════════════════════════════════════════════════════════════════════════╝
app.post("/attendance", async (req, res) => {
  const {
    per_id, status, camera_name, check_time,
    name, prename_th, per_name, per_surname,
    posname_th, organize_th, organize_id,
  } = req.body;

  if (!per_id || !status) {
    return res.status(400).json({ error: "per_id และ status จำเป็นต้องมี" });
  }
  if (!["IN", "OUT"].includes(status)) {
    return res.status(400).json({ error: "status ต้องเป็น 'IN' หรือ 'OUT'" });
  }

  try {
    // ตรวจซ้ำ
    const dupCheck = await query(
      `SELECT 1 FROM attendance_logs
       WHERE per_id = $1 AND DATE(check_time) = CURRENT_DATE AND status = $2
       LIMIT 1`,
      [per_id, status]
    );
    if (dupCheck.rowCount > 0) {
      return res.json({ success: false, reason: `วันนี้บันทึก ${status} แล้ว` });
    }

    // OUT ต้องมี IN ก่อน
    if (status === "OUT") {
      const inCheck = await query(
        `SELECT 1 FROM attendance_logs
         WHERE per_id = $1 AND DATE(check_time) = CURRENT_DATE AND status = 'IN'
         LIMIT 1`,
        [per_id]
      );
      if (inCheck.rowCount === 0) {
        return res.json({ success: false, reason: "ยังไม่มี IN วันนี้" });
      }
    }

    // บันทึก
    await query(
      `INSERT INTO attendance_logs
         (per_id, status, camera_name, check_time,
          name, prename_th, per_name, per_surname,
          posname_th, organize_th, organize_id)
       VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11)`,
      [
        per_id, status, camera_name || null,
        check_time ? new Date(check_time) : new Date(),
        name || null, prename_th || null, per_name || null,
        per_surname || null, posname_th || null,
        organize_th || null, organize_id || null,
      ]
    );

    return res.json({ success: true, per_id, status });
  } catch (err) {
    console.error("[POST /attendance]", err.message);
    return res.status(500).json({ error: err.message });
  }
});


// ╔═══════════════════════════════════════════════════════════════════════════╗
// ║  GET /attendance/today/check — ตรวจว่า IN/OUT แล้วหรือยัง              ║
// ╚═══════════════════════════════════════════════════════════════════════════╝
app.get("/attendance/today/check", async (req, res) => {
  const { per_id, status } = req.query;
  if (!per_id || !status) {
    return res.status(400).json({ error: "per_id และ status จำเป็นต้องมี" });
  }

  try {
    const result = await query(
      `SELECT 1 FROM attendance_logs
       WHERE per_id = $1 AND DATE(check_time) = CURRENT_DATE AND status = $2
       LIMIT 1`,
      [per_id, status]
    );
    return res.json({ marked: result.rowCount > 0, per_id, status });
  } catch (err) {
    console.error("[GET /attendance/today/check]", err.message);
    return res.status(500).json({ error: err.message });
  }
});


// ╔═══════════════════════════════════════════════════════════════════════════╗
// ║  GET /attendance/today — รายการลงเวลาวันนี้ทั้งหมด                      ║
// ╚═══════════════════════════════════════════════════════════════════════════╝
app.get("/attendance/today", async (req, res) => {
  try {
    const result = await query(
      `SELECT id, per_id, name, prename_th, per_name, per_surname,
              posname_th, organize_th, organize_id,
              status, camera_name, check_time
       FROM attendance_logs
       WHERE DATE(check_time) = CURRENT_DATE
       ORDER BY check_time DESC`
    );
    return res.json(result.rows.map(r => ({
      ...r,
      check_time: r.check_time ? r.check_time.toISOString() : null,
    })));
  } catch (err) {
    console.error("[GET /attendance/today]", err.message);
    return res.status(500).json({ error: err.message });
  }
});


// ╔═══════════════════════════════════════════════════════════════════════════╗
// ║  GET /attendance/:per_id — ประวัติลงเวลาของพนักงาน                       ║
// ╚═══════════════════════════════════════════════════════════════════════════╝
app.get("/attendance/:per_id", async (req, res) => {
  const { per_id } = req.params;
  const { start_date, end_date } = req.query;

  let text = `
    SELECT id, name, prename_th, per_name, per_surname,
           posname_th, organize_th, organize_id,
           status, camera_name, check_time
    FROM attendance_logs
    WHERE per_id = $1
  `;
  const params = [per_id];

  if (start_date) {
    params.push(start_date);
    text += ` AND DATE(check_time) >= $${params.length}`;
  }
  if (end_date) {
    params.push(end_date);
    text += ` AND DATE(check_time) <= $${params.length}`;
  }
  text += " ORDER BY check_time DESC LIMIT 100";

  try {
    const result = await query(text, params);
    return res.json(result.rows.map(r => ({
      ...r,
      check_time: r.check_time ? r.check_time.toISOString() : null,
    })));
  } catch (err) {
    console.error("[GET /attendance/:per_id]", err.message);
    return res.status(500).json({ error: err.message });
  }
});


// ╔═══════════════════════════════════════════════════════════════════════════╗
// ║  PUT /attendance/:log_id — แก้ไข record ลงเวลา                          ║
// ╚═══════════════════════════════════════════════════════════════════════════╝
app.put("/attendance/:log_id", async (req, res) => {
  const log_id = parseInt(req.params.log_id);
  if (isNaN(log_id)) {
    return res.status(400).json({ error: "log_id ต้องเป็นตัวเลข" });
  }

  const allowed = ["status", "camera_name", "check_time",
                   "name", "prename_th", "per_name", "per_surname",
                   "posname_th", "organize_th", "organize_id"];

  const fields = Object.entries(req.body).filter(([k]) => allowed.includes(k));
  if (fields.length === 0) {
    return res.status(400).json({ error: "ไม่มี field ที่ต้องการแก้ไข" });
  }
  if (req.body.status && !["IN", "OUT"].includes(req.body.status)) {
    return res.status(400).json({ error: "status ต้องเป็น 'IN' หรือ 'OUT'" });
  }

  const setClause = fields.map(([k], i) => `${k} = $${i + 1}`).join(", ");
  const values    = [...fields.map(([, v]) => v), log_id];

  try {
    const result = await query(
      `UPDATE attendance_logs SET ${setClause} WHERE id = $${values.length}`,
      values
    );
    if (result.rowCount === 0) {
      return res.status(404).json({ error: "Attendance record not found" });
    }
    return res.json({ success: true, id: log_id, updated: Object.fromEntries(fields) });
  } catch (err) {
    console.error("[PUT /attendance/:log_id]", err.message);
    return res.status(500).json({ error: err.message });
  }
});


// ╔═══════════════════════════════════════════════════════════════════════════╗
// ║  DELETE /attendance/:log_id — ลบ record ลงเวลา                          ║
// ╚═══════════════════════════════════════════════════════════════════════════╝
app.delete("/attendance/:log_id", async (req, res) => {
  const log_id = parseInt(req.params.log_id);
  if (isNaN(log_id)) {
    return res.status(400).json({ error: "log_id ต้องเป็นตัวเลข" });
  }

  try {
    const result = await query(
      "DELETE FROM attendance_logs WHERE id = $1",
      [log_id]
    );
    if (result.rowCount === 0) {
      return res.status(404).json({ error: "Attendance record not found" });
    }
    return res.json({ success: true, id: log_id });
  } catch (err) {
    console.error("[DELETE /attendance/:log_id]", err.message);
    return res.status(500).json({ error: err.message });
  }
});


// ── Start ────────────────────────────────────────────────────────────────────
app.listen(PORT, () => {
  console.log(`[SERVER] Face Attendance API running on http://localhost:${PORT}`);
});
