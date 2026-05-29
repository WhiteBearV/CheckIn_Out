# Archive — เอกสาร/ไฟล์เก่าที่ยังเก็บไว้อ้างอิง

⚠ **ไฟล์ในโฟลเดอร์นี้ outdated** — ใช้สำหรับอ้างอิงประวัติเท่านั้น
**ห้ามใช้สำหรับ deploy/ติดตั้งจริง** ให้ดูเอกสารปัจจุบันแทน

---

## เอกสารปัจจุบัน (ใช้ตัวนี้)

| ต้องการอะไร | อ่านไฟล์ไหน |
|---|---|
| Quick start / ภาพรวม | [`../README.md`](../README.md) |
| คู่มือปฏิบัติการเต็ม (deploy/ops/network) | [`../RUNBOOK.md`](../RUNBOOK.md) |
| Template env vars | [`../.env.example`](../.env.example) |
| Template DB config | [`../db_config.example.json`](../db_config.example.json) |

---

## ไฟล์ในโฟลเดอร์นี้

### `คู่มือติดตั้งและใช้งาน.txt`
- **เขียนเมื่อ:** 2026-04-29
- **สำหรับ version:** v12 (ปัจจุบัน v16+)
- **เหตุที่ archive:** มี `RUNBOOK.md` ที่ใหม่กว่า ครบกว่า และรวมเนื้อหา Phase 1-4 + network requirements ที่ไฟล์เก่าไม่มี
- **เนื้อหาที่ยังอ้างอิงได้:** ส่วน Anti-Spoofing Pipeline, Active Windows, PicSAVE structure (logic ส่วนนี้ไม่เปลี่ยน)
- **ส่วนที่ outdated:** ติดตั้ง systemd, env vars, JWT auth, offline queue, backup/cleanup, User Management — ทุกอย่างนี้ดู `RUNBOOK.md` แทน
