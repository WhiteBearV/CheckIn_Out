#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────
# ติดตั้ง systemd service สำหรับ FaceReg stream_server.py
# รัน:  sudo bash deploy/install_service.sh
# ─────────────────────────────────────────────────────────────────────
set -euo pipefail

if [[ $EUID -ne 0 ]]; then
    echo "[ERR] ต้องรันด้วย sudo:  sudo bash deploy/install_service.sh"
    exit 1
fi

SERVICE_NAME="facereg-stream"
SERVICE_FILE="/home/maeb/internship_work/FaceReg/deploy/${SERVICE_NAME}.service"
TARGET="/etc/systemd/system/${SERVICE_NAME}.service"

if [[ ! -f "$SERVICE_FILE" ]]; then
    echo "[ERR] ไม่พบ $SERVICE_FILE"
    exit 1
fi

echo "[1/4] copy service file → $TARGET"
cp "$SERVICE_FILE" "$TARGET"
chmod 644 "$TARGET"

echo "[2/4] systemctl daemon-reload"
systemctl daemon-reload

echo "[3/4] enable service (auto-start ตอน boot)"
systemctl enable "$SERVICE_NAME"

echo "[4/4] start service"
systemctl restart "$SERVICE_NAME"

sleep 2
systemctl status "$SERVICE_NAME" --no-pager --lines=5 || true

cat <<EOF

────────────────────────────────────────────────────────
[OK] ติดตั้งเสร็จ — คำสั่งที่ใช้บ่อย:

    sudo systemctl status   ${SERVICE_NAME}     # ดูสถานะ
    sudo systemctl restart  ${SERVICE_NAME}     # restart
    sudo systemctl stop     ${SERVICE_NAME}     # หยุด (จะไม่ auto-start จนกว่าจะ start)
    sudo systemctl start    ${SERVICE_NAME}     # start
    sudo systemctl disable  ${SERVICE_NAME}     # ปิดไม่ให้ auto-start ตอน boot
    journalctl -u ${SERVICE_NAME} -f            # ดู log สด
    journalctl -u ${SERVICE_NAME} -n 200        # ดู log 200 บรรทัดล่าสุด

หน้าเว็บ:  http://localhost:8001/admin
สถานะ watchdog (child process):  http://localhost:8001/system/watchdog
────────────────────────────────────────────────────────
EOF
