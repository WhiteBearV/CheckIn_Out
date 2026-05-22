const {
  Document, Packer, Paragraph, TextRun, HeadingLevel,
  AlignmentType, PageNumber, Header, Footer,
  LevelFormat, NumberFormat, WidthType, convertInchesToTwip
} = require('/opt/homebrew/lib/node_modules/docx');
const fs = require('fs');

// ── ค่าหน้ากระดาษ A4 (DXA) ──────────────────────────────────────────
const A4_W   = 11906; // ~210mm
const A4_H   = 16838; // ~297mm
const MARGIN = 1701;  // ~3cm (top/bottom/left/right)
const CONTENT_W = A4_W - MARGIN * 2; // ความกว้าง content จริง

const FONT   = 'TH SarabunPSK';
const SIZE_BODY   = 28; // 14pt
const SIZE_H1     = 36; // 18pt
const SIZE_H2     = 28; // 14pt
const SIZE_SMALL  = 24; // 12pt

// ── helper: paragraph เนื้อหาปกติ (indent บรรทัดแรก 720 DXA) ────────
function body(text, opts = {}) {
  const runs = typeof text === 'string'
    ? [new TextRun({ text, font: FONT, size: SIZE_BODY })]
    : text;
  return new Paragraph({
    children: runs,
    alignment: opts.align ?? AlignmentType.THAI_JUSTIFY,
    spacing: { before: 0, after: 60, line: 360, lineRule: 'auto' },
    indent: opts.noIndent ? {} : { firstLine: 720 },
    ...opts.extra,
  });
}

// ── helper: heading บท (บทที่ X / หัวข้อ X.X) ───────────────────────
function chapterTitle(text) {
  return new Paragraph({
    children: [new TextRun({ text, bold: true, font: FONT, size: SIZE_H1 })],
    alignment: AlignmentType.CENTER,
    spacing: { before: 480, after: 240, line: 360, lineRule: 'auto' },
  });
}

function sectionTitle(text) {
  return new Paragraph({
    children: [new TextRun({ text, bold: true, font: FONT, size: SIZE_H2 })],
    alignment: AlignmentType.LEFT,
    spacing: { before: 240, after: 60, line: 360, lineRule: 'auto' },
  });
}

function subsectionTitle(text) {
  return new Paragraph({
    children: [new TextRun({ text, bold: true, font: FONT, size: SIZE_H2 })],
    alignment: AlignmentType.LEFT,
    spacing: { before: 120, after: 60, line: 360, lineRule: 'auto' },
    indent: { left: 720 },
  });
}

// ── helper: bullet list ──────────────────────────────────────────────
function bullet(text, indent = 1) {
  return new Paragraph({
    children: [new TextRun({ text, font: FONT, size: SIZE_BODY })],
    numbering: { reference: 'bullets', level: indent - 1 },
    spacing: { before: 0, after: 40, line: 360, lineRule: 'auto' },
  });
}

// ── helper: numbered list ─────────────────────────────────────────────
function numbered(text, ref = 'numbers1') {
  return new Paragraph({
    children: [new TextRun({ text, font: FONT, size: SIZE_BODY })],
    numbering: { reference: ref, level: 0 },
    spacing: { before: 0, after: 60, line: 360, lineRule: 'auto' },
  });
}

// ── helper: ย่อหน้าเนื้อหาย่อย (indent ซ้าย 720) ────────────────────
function sub(text) {
  return body(text, { noIndent: true, extra: { indent: { left: 720, firstLine: 720 } } });
}

function spacer(n = 1) {
  return new Paragraph({
    children: [new TextRun({ text: '', font: FONT, size: SIZE_BODY })],
    spacing: { before: 0, after: n * 120, line: 360, lineRule: 'auto' },
  });
}

// ── Page break ────────────────────────────────────────────────────────
function pageBreak() {
  return new Paragraph({
    children: [new TextRun({ break: 1 })],
  });
}

// ═══════════════════════════════════════════════════════════════════════
//  เนื้อหาเอกสาร
// ═══════════════════════════════════════════════════════════════════════

const content = [

  // ════════════════ บทที่ 1 ════════════════
  chapterTitle('บทที่ 1'),
  chapterTitle('บทนำ'),
  spacer(),

  // 1.1
  sectionTitle('1.1 หลักการและเหตุผล'),
  body('การฝึกประสบการณ์วิชาชีพเป็นกิจกรรมสำคัญที่ช่วยให้นักศึกษาได้นำความรู้ทางทฤษฎีมาประยุกต์ใช้กับสภาพการทำงานจริง โดยมีจุดมุ่งหมายเพื่อให้นักศึกษาได้เพิ่มพูนทักษะ สร้างเสริมประสบการณ์ และพัฒนาวิชาชีพตามสภาพความเป็นจริงในสถานประกอบการ รวมถึงได้พัฒนาทักษะการทำงานร่วมกับผู้อื่น ฝึกคิดวิเคราะห์ การแก้ไขปัญหา และการปรับตัวให้เหมาะสมกับสภาพแวดล้อมในการทำงาน'),
  body('ผู้จัดทำได้มีโอกาสเข้ารับการฝึกงาน ณ ศูนย์เทคโนโลยีดิจิทัล หน่วยราชการในพระองค์ ภายใต้การกำกับดูแลของกองการศึกษา วิจัย และพัฒนา ระหว่างวันที่ 24 มีนาคม ถึง 30 พฤษภาคม 2568 โดยได้รับมอบหมายให้พัฒนาระบบบันทึกเวลาเข้า-ออกด้วยการจดจำใบหน้า (Face Attendance System) เพื่อทดแทนระบบเดิมที่ใช้การลงชื่อด้วยมือ ลดความผิดพลาดในการบันทึกข้อมูล และเพิ่มประสิทธิภาพในการบริหารจัดการข้อมูลบุคลากร'),
  body('จากการเข้าร่วมฝึกงานครั้งนี้ ผู้จัดทำได้รับประสบการณ์ที่มีคุณค่าอย่างยิ่ง ทั้งในด้านทักษะทางเทคนิค การทำงานเป็นทีม และความเข้าใจในการดำเนินงานในภาคราชการ ซึ่งเป็นพื้นฐานสำคัญในการเตรียมความพร้อมเข้าสู่ตลาดแรงงานในอนาคต'),

  // 1.2
  sectionTitle('1.2 วัตถุประสงค์ของงาน'),
  numbered('เพื่อพัฒนาระบบบันทึกเวลาเข้า-ออกด้วยการจดจำใบหน้าที่มีความแม่นยำสูง พร้อมระบบป้องกันการปลอมแปลง (Anti-Spoofing) หลายชั้น'),
  numbered('เพื่อพัฒนาทักษะด้านการเขียนโปรแกรม การออกแบบระบบ และการทำงานกับฐานข้อมูลในสภาพการณ์จริง'),
  numbered('เพื่อเรียนรู้การทำงานร่วมกับบุคลากรในองค์กร ทั้งการสื่อสาร การแก้ไขปัญหา และการบริหารเวลา'),
  numbered('เพื่อสร้างระบบที่สามารถนำไปใช้งานจริงภายในองค์กรได้อย่างมีประสิทธิภาพ'),

  // 1.3
  sectionTitle('1.3 ขอบเขตของงาน'),
  body('การฝึกงานครอบคลุมระยะเวลา 10 สัปดาห์ โดยเน้นการพัฒนาระบบ Face Attendance System ดังนี้', { noIndent: false }),
  bullet('การพัฒนาส่วนการจดจำใบหน้า (Face Recognition) โดยใช้ InsightFace (ArcFace) ร่วมกับ ONNX Runtime สำหรับประมวลผล'),
  bullet('การพัฒนาระบบป้องกันการปลอมแปลง (Anti-Spoofing) หลายชั้น ประกอบด้วย Landmark Depth, Micro-Motion, Blink Detection, Texture Analysis, Finger Challenge และ MiniFASNet AI Model'),
  bullet('การพัฒนา Web Dashboard ด้วย Vue.js สำหรับแสดงผลการเช็คชื่อแบบ Real-time พร้อมฟีเจอร์จัดการกล้องและระบบ Login'),
  bullet('การพัฒนา REST API ด้วย FastAPI และการจัดเก็บข้อมูลใน PostgreSQL'),
  bullet('การ Deploy ระบบผ่าน Docker รองรับการติดตั้งบนเครื่องอื่นในวง LAN'),

  // 1.4
  sectionTitle('1.4 ประโยชน์ที่คาดว่าจะได้รับ'),
  bullet('ได้พัฒนาทักษะและความรู้ทางด้านเทคโนโลยีสารสนเทศจากการปฏิบัติงานจริง โดยเฉพาะด้าน Computer Vision และ AI'),
  bullet('มีประสบการณ์ในการทำงานเป็นทีมและร่วมมือกับบุคลากรในองค์กร'),
  bullet('เข้าใจแนวทางการทำงานในหน่วยงานราชการ รวมถึงระเบียบและข้อกำหนดที่เกี่ยวข้อง'),
  bullet('มีผลงานที่สามารถนำไปใช้เป็นส่วนหนึ่งของแฟ้มสะสมงาน (Portfolio) ในอนาคต'),

  // ════════════════ บทที่ 2 ════════════════
  pageBreak(),
  chapterTitle('บทที่ 2 รายละเอียดของการฝึกงาน'),
  spacer(),

  // 2.1
  sectionTitle('2.1 รายละเอียดของงานที่ปฏิบัติงาน'),
  body('ตลอดระยะเวลาฝึกงานระหว่างวันที่ 24 มีนาคม ถึง 30 พฤษภาคม 2568 ผู้จัดทำได้รับมอบหมายให้พัฒนาระบบบันทึกเวลาเข้า-ออกด้วยการจดจำใบหน้า (Face Attendance System) สำหรับศูนย์เทคโนโลยีดิจิทัล หน่วยราชการในพระองค์ โดยลักษณะงานที่ได้รับมอบหมายสามารถสรุปได้ดังนี้'),

  subsectionTitle('2.1.1 การพัฒนา Face Recognition Engine'),
  sub('เป็นภารกิจหลักของระบบ ทำหน้าที่ตรวจจับและจดจำใบหน้าบุคลากรผ่านกล้องโดยอัตโนมัติ โดยใช้ InsightFace (buffalo_l, ArcFace 512d) ร่วมกับ ONNX Runtime สำหรับเปรียบเทียบใบหน้ากับฐานข้อมูลที่บันทึกไว้ใน known_faces/ ระบบรองรับทั้ง USB Camera และ IP Camera ผ่าน RTSP ผ่าน ThreadedCamera เพื่อไม่ให้การ capture ภาพขัดขวาง main loop'),

  subsectionTitle('2.1.2 การพัฒนาระบบป้องกันการปลอมแปลง (Anti-Spoofing)'),
  sub('พัฒนา Liveness Detection Pipeline หลายชั้น เพื่อป้องกันไม่ให้ผู้ไม่ประสงค์ดีใช้รูปถ่ายหรือวิดีโอแทนใบหน้าจริง ประกอบด้วย'),
  bullet('Landmark Depth: ตรวจความลึก 3D จาก 68-point facial landmarks'),
  bullet('Micro-Motion Detection: ตรวจการขยับใบหน้าเล็กน้อย'),
  bullet('Blink Detection: ตรวจการกะพริบตาจาก Eye Aspect Ratio (EAR)'),
  bullet('Texture Analysis: ตรวจลวดลายผิวด้วย LBP, Laplacian และ Chroma'),
  bullet('Finger Challenge: ให้ผู้ใช้ยกนิ้วตามจำนวนที่กำหนดโดยสุ่ม ผ่าน MediaPipe Hands'),
  bullet('MiniFASNet: AI Model ตรวจจับ Spoof โดยตรง'),

  subsectionTitle('2.1.3 การพัฒนา Web Dashboard'),
  sub('พัฒนาส่วนติดต่อผู้ใช้งานบนเว็บด้วย Vue.js 3 (Composition API) ครอบคลุมหน้าจอต่างๆ ได้แก่'),
  bullet('DashboardView: แสดงสถิติภาพรวม กราฟรายชั่วโมง และรายชื่อผู้เช็คชื่อวันนี้แบบ Real-time'),
  bullet('CameraView: แสดงภาพ Live จากกล้องทุกตัวพร้อม Multi-Camera support และ Fullscreen Mode (โหมด CCTV)'),
  bullet('LiveDetection: แสดงสถานะการตรวจจับใบหน้าแบบ Real-time พร้อม Liveness Badge 4 ระดับ'),
  bullet('HistoryView: ดูประวัติการลงเวลาพร้อมตัวกรองตามวันที่และ Export ข้อมูล'),
  bullet('SettingsView: จัดการ Users และ Roles ผ่าน Role-Based Access Control (RBAC)'),

  subsectionTitle('2.1.4 การพัฒนา REST API และฐานข้อมูล'),
  sub('ออกแบบและพัฒนา FastAPI Backend สำหรับรับ-ส่งข้อมูลระหว่าง Face Recognition Engine กับ Web Dashboard โดยบันทึกข้อมูลการเข้า-ออกใน PostgreSQL รองรับการเชื่อมต่อ External Personnel API สำหรับดึงข้อมูลพนักงาน พร้อม TTL Cache ป้องกัน API Flood และระบบ Auto-Checkout เวลา 22:00 น. ผ่าน asyncio Background Task'),

  subsectionTitle('2.1.5 การ Deploy และ Containerization'),
  sub('ออกแบบ Docker Compose สำหรับ Deploy ระบบทั้งหมด ประกอบด้วย api service และ db (PostgreSQL) สามารถรันด้วยคำสั่งเดียวและ Push image ขึ้น Docker Hub เพื่อให้ติดตั้งบนเครื่องอื่นได้ง่าย รองรับการเข้าถึงจากเครื่องอื่นในวง LAN ผ่าน http://<IP>/dashboard/'),

  // 2.2
  sectionTitle('2.2 รายละเอียดการดำเนินงาน'),
  body('การดำเนินงานในการพัฒนาระบบ Face Attendance มีการแบ่งงานออกเป็นขั้นตอนอย่างเป็นระบบ เพื่อให้สามารถส่งมอบผลงานที่มีคุณภาพตรงตามความต้องการของหน่วยงาน ซึ่งมีรายละเอียดแต่ละขั้นตอนดังนี้'),

  subsectionTitle('2.2.1 การวิเคราะห์ความต้องการและออกแบบระบบ (สัปดาห์ที่ 1–2)'),
  sub('เริ่มต้นด้วยการศึกษาความต้องการของหน่วยงานและวิเคราะห์ปัญหาของระบบเดิม จากนั้นออกแบบโครงสร้างระบบใหม่ที่รองรับการทำงานแบบ Multi-Camera การสื่อสารระหว่าง Process ผ่าน File-based IPC (live_state.json) การจัดเก็บข้อมูลใน PostgreSQL และการแสดงผลแบบ Real-time ผ่าน Web Dashboard'),

  subsectionTitle('2.2.2 การพัฒนา Face Recognition และ Anti-Spoofing Pipeline (สัปดาห์ที่ 1–6)'),
  sub('พัฒนาระบบหลักโดยใช้ InsightFace และ ONNX Runtime สำหรับการจดจำใบหน้า พร้อมออกแบบ Anti-Spoofing Pipeline 6 ชั้น ระบบสามารถตรวจจับใบหน้าหลายคนพร้อมกัน บันทึกเวลา Check-in ทันทีที่ผ่านการตรวจสอบ Liveness ครบทุกด่าน และบันทึกภาพ Snapshot ไว้เป็นหลักฐานประกอบด้วย 3 ประเภท ได้แก่ รูป Full Frame รูป Face Crop และรูป Out'),

  subsectionTitle('2.2.3 การพัฒนา Web Dashboard (สัปดาห์ที่ 2–10)'),
  sub('พัฒนา Frontend ด้วย Vue.js 3 โดยใช้ Composition API เริ่มจาก Dashboard แสดงสถิติรายวันและ Live Feed จากกล้องหลายตัว ต่อด้วยฟีเจอร์ Fullscreen Mode สำหรับโหมด CCTV ระบบ Theme (Light/Dark) ที่สลับอัตโนมัติตามเวลา การจัดการกล้องผ่าน Web โดยไม่ต้องแก้โค้ด หน้าประวัติการลงเวลาพร้อม Export และสุดท้ายระบบ Login ด้วย JWT พร้อม Role-Based Access Control (RBAC)'),

  subsectionTitle('2.2.4 การพัฒนา REST API และการเชื่อมต่อระบบ (สัปดาห์ที่ 1–10)'),
  sub('พัฒนา FastAPI Backend ครอบคลุม Endpoints สำหรับบันทึกการเช็คชื่อ แสดงสถานะ Real-time ผ่าน MJPEG Streaming จัดการกล้อง ดึงข้อมูลพนักงานจาก External Personnel API พร้อม TTL Cache ป้องกัน API Flood และระบบ Auto-Checkout เวลา 22:00 น. ผ่าน asyncio Background Task นอกจากนี้ยังมีระบบ Live State ที่ main.py เขียนสถานะทุก 1 วินาที เพื่อให้ Dashboard ทราบสถานะแบบ Real-time'),

  subsectionTitle('2.2.5 การแก้ไขประสิทธิภาพและ Deploy ด้วย Docker (สัปดาห์ที่ 5–6)'),
  sub('วิเคราะห์และแก้ไขปัญหา MJPEG Stream กระตุกบน Docker โดยเพิ่ม mtime tracking ส่ง Frame เฉพาะเมื่อมีการเปลี่ยนแปลง ใช้ tmpfs Mount (RAM Disk 32MB) ลด Disk I/O latency ปรับ Detection Size และ Frame Rate ให้เหมาะสมกับ CPU-only environment และตั้งค่า Timezone ให้ถูกต้อง นอกจากนี้ยังได้ Build และ Push Docker Image ขึ้น Docker Hub พร้อมเปิด Port 80 สำหรับเข้าถึงจากวง LAN โดยไม่ต้องระบุ Port'),

  subsectionTitle('2.2.6 การพัฒนาระบบ Authentication และ RBAC (สัปดาห์ที่ 10)'),
  sub('ออกแบบและพัฒนาระบบ Login ด้วย JWT Token (HS256 อายุ 8 ชั่วโมง) พร้อม Role-Based Access Control (RBAC) รองรับ 5 สิทธิ์ ได้แก่ attendance.view, attendance.clear, cameras.view, cameras.manage และ users.manage โดยมี Superadmin ที่มีสิทธิ์ทุกอย่าง ระบบสร้าง Role และ User เริ่มต้นอัตโนมัติเมื่อ Database ว่างเปล่า และผู้ดูแลระบบสามารถจัดการ Users/Roles ได้ผ่าน Settings View บน Dashboard'),

  // ════════════════ บทที่ 3 ════════════════
  pageBreak(),
  chapterTitle('บทที่ 3 สรุปผลการฝึกงาน'),
  spacer(),

  // 3.1
  sectionTitle('3.1 สรุปผลการฝึกงาน'),
  body('จากการฝึกงานตลอด 10 สัปดาห์ ที่ศูนย์เทคโนโลยีดิจิทัล หน่วยราชการในพระองค์ ผู้จัดทำได้พัฒนาระบบ Face Attendance System อย่างครบถ้วนสมบูรณ์ ประกอบด้วย Face Recognition Engine ที่ใช้ InsightFace (ArcFace) ซึ่งมีความแม่นยำสูง ระบบป้องกันการปลอมแปลงหลายชั้น Web Dashboard แบบ Real-time พร้อมระบบ Authentication และ RBAC REST API ด้วย FastAPI รวมถึง PostgreSQL Database และการ Deploy ผ่าน Docker ที่สามารถติดตั้งได้ง่ายบนเครื่องอื่นในวง LAN'),
  body('การฝึกงานครั้งนี้ไม่เพียงแต่ช่วยให้ผู้จัดทำได้นำความรู้จากการเรียนรายวิชาต่างๆ มาประยุกต์ใช้กับงานจริง สามารถแก้ไขปัญหาที่เกิดขึ้นจริง การแก้ไขปัญหาเฉพาะหน้า และการได้รับคำแนะนำจากผู้ควบคุมการฝึกงาน ทำให้สามารถปฏิบัติงานได้จริง คณะผู้จัดทำได้ฝึกการทำงานร่วมกับผู้อื่น ให้ความเคารพต่อทุกคนในองค์กร เรียนรู้การรับฟังความคิดเห็นของผู้อื่น'),
  body('ดังนั้นการฝึกงานมีความสำคัญอย่างมาก เพราะถือเป็นการเรียนรู้รูปแบบหนึ่งที่ช่วยพัฒนาความสามารถของคณะผู้จัดทำได้ และทราบถึงความสามารถที่ได้รับจากการศึกษามีประโยชน์ต่อการทำงานไม่มากก็น้อย เมื่อสำเร็จการศึกษาไปพร้อมเข้าสู่โลกการทำงาน คณะผู้จัดทำจะสามารถนำไปประยุกต์ใช้ในการทำงานได้อย่างแท้จริง'),

  // 3.2
  sectionTitle('3.2 ประโยชน์ของการฝึกงาน'),

  subsectionTitle('3.2.1 ประโยชน์ที่นักศึกษาได้รับจากการฝึกงาน'),
  sub('ได้รับประสบการณ์จริงในการพัฒนาระบบ AI และ Computer Vision ตั้งแต่การวิเคราะห์ความต้องการจนถึงการส่งมอบระบบที่ใช้งานได้จริง ทั้งในด้านการพัฒนา Full-Stack (Python FastAPI + Vue.js + PostgreSQL + Docker) การออกแบบสถาปัตยกรรมระบบ และการแก้ไขปัญหาเชิงเทคนิคในสภาพแวดล้อมจริง นอกจากนี้ยังได้รับประสบการณ์ในการทำงานร่วมกับทีมงานในองค์กรราชการ ฝึกการสื่อสาร การนำเสนอผลงาน และการปรับตัวให้เข้ากับวัฒนธรรมองค์กร'),

  subsectionTitle('3.2.2 ประโยชน์ที่หน่วยงานได้รับจากการฝึกงาน'),
  sub('หน่วยงานได้ระบบ Face Attendance System ที่ครบถ้วนสมบูรณ์ สามารถนำไปใช้งานได้จริง ช่วยลดภาระงาน Manual ในการบันทึกเวลาและเพิ่มความถูกต้องของข้อมูล นอกจากนี้ยังได้ Web Dashboard สำหรับบริหารจัดการข้อมูลการเข้า-ออกงานแบบ Real-time ที่ผู้ดูแลระบบสามารถควบคุมสิทธิ์การเข้าถึงได้อย่างละเอียดผ่านระบบ RBAC'),
];

// ═══════════════════════════════════════════════════════════════════════
//  สร้าง Document
// ═══════════════════════════════════════════════════════════════════════

const doc = new Document({
  numbering: {
    config: [
      {
        reference: 'bullets',
        levels: [
          {
            level: 0,
            format: LevelFormat.BULLET,
            text: '●',
            alignment: AlignmentType.LEFT,
            style: {
              run: { font: 'Symbol', size: SIZE_BODY },
              paragraph: { indent: { left: 900, hanging: 360 } },
            },
          },
        ],
      },
      {
        reference: 'numbers1',
        levels: [
          {
            level: 0,
            format: LevelFormat.DECIMAL,
            text: '%1.',
            alignment: AlignmentType.LEFT,
            style: {
              run: { font: FONT, size: SIZE_BODY },
              paragraph: { indent: { left: 900, hanging: 360 } },
            },
          },
        ],
      },
    ],
  },

  styles: {
    default: {
      document: {
        run: { font: FONT, size: SIZE_BODY },
        paragraph: { spacing: { line: 360, lineRule: 'auto' } },
      },
    },
  },

  sections: [
    {
      properties: {
        page: {
          size: { width: A4_W, height: A4_H },
          margin: { top: MARGIN, right: MARGIN, bottom: MARGIN, left: MARGIN },
        },
      },
      headers: {
        default: new Header({
          children: [
            new Paragraph({
              children: [
                new TextRun({ children: [PageNumber.CURRENT], font: FONT, size: SIZE_SMALL }),
              ],
              alignment: AlignmentType.RIGHT,
            }),
          ],
        }),
      },
      children: content,
    },
  ],
});

Packer.toBuffer(doc).then(buf => {
  fs.writeFileSync('/Users/photcharaphoempool/InternProject/CheckIn_Out/D_report/report_3chapters.docx', buf);
  console.log('Done: report_3chapters.docx');
});
