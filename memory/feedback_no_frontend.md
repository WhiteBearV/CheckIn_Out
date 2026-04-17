---
name: Don't touch frontend unless told
description: User explicitly said not to modify React frontend files unless instructed
type: feedback
---

อย่าแตะไฟล์ใน front_end/ ถ้าไม่ได้รับคำสั่งโดยตรง

**Why:** User แยก "GUI หลังบ้าน" (FastAPI/OpenCV) กับ "หน้าบ้าน" (React) ชัดเจน เคยเตือนครั้งนึงแล้วเมื่อเริ่มแก้ LiveCam.jsx โดยไม่ได้รับอนุญาต

**How to apply:** ถ้า task เกี่ยวกับ UI/GUI ให้ถามก่อนว่าหมายถึงหลังบ้าน (FastAPI HTML, OpenCV) หรือหน้าบ้าน (React) — ถ้าไม่แน่ใจ default = หลังบ้านเท่านั้น
