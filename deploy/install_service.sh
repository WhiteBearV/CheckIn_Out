#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────
# ติดตั้ง systemd services + timers ทั้งหมดสำหรับ FaceReg
# รัน:  sudo bash deploy/install_service.sh
# ─────────────────────────────────────────────────────────────────────
set -euo pipefail

if [[ $EUID -ne 0 ]]; then
    echo "[ERR] ต้องรันด้วย sudo:  sudo bash deploy/install_service.sh"
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SYSTEMD_DIR="/etc/systemd/system"

# ─── helper ───────────────────────────────────────────────────────────
install_unit() {
    local name="$1"
    local src="$SCRIPT_DIR/${name}"
    if [[ ! -f "$src" ]]; then
        echo "[SKIP] ไม่พบ $src"
        return
    fi
    cp "$src" "$SYSTEMD_DIR/${name}"
    chmod 644 "$SYSTEMD_DIR/${name}"
    echo "  → $SYSTEMD_DIR/${name}"
}

# ─── 1. stream server (main process) ─────────────────────────────────
echo "[1/5] facereg-stream.service"
install_unit "facereg-stream.service"

# ─── 2. backup timer ─────────────────────────────────────────────────
echo "[2/5] facereg-backup (service + timer)"
install_unit "facereg-backup.service"
install_unit "facereg-backup.timer"

# ─── 3. cleanup timer ────────────────────────────────────────────────
echo "[3/5] facereg-cleanup (service + timer)"
install_unit "facereg-cleanup.service"
install_unit "facereg-cleanup.timer"

# ─── 4. journald log rotation ────────────────────────────────────────
echo "[4/5] journald config (log rotation)"
JOURNALD_CONF_DIR="/etc/systemd/journald.conf.d"
mkdir -p "$JOURNALD_CONF_DIR"
cp "$SCRIPT_DIR/journald-facereg.conf" "$JOURNALD_CONF_DIR/facereg.conf"
chmod 644 "$JOURNALD_CONF_DIR/facereg.conf"
echo "  → $JOURNALD_CONF_DIR/facereg.conf"
systemctl restart systemd-journald
echo "  systemd-journald restarted"

# ─── 5. enable + start ───────────────────────────────────────────────
echo "[5/5] daemon-reload + enable + start"
systemctl daemon-reload

systemctl enable --now facereg-stream
systemctl enable facereg-backup.timer facereg-cleanup.timer
systemctl start  facereg-backup.timer facereg-cleanup.timer

sleep 2
systemctl status facereg-stream --no-pager --lines=5 || true

cat <<EOF

────────────────────────────────────────────────────────
[OK] ติดตั้งเสร็จครบทุก service

STREAM SERVER
    sudo systemctl status   facereg-stream
    sudo systemctl restart  facereg-stream
    journalctl -u facereg-stream -f

BACKUP / CLEANUP TIMERS
    systemctl list-timers --no-pager | grep facereg
    journalctl -u facereg-backup  -n 50
    journalctl -u facereg-cleanup -n 50

หน้าเว็บ:        http://localhost:8001
Admin panel:     http://localhost:8001/admin
Watchdog status: http://localhost:8001/system/watchdog
────────────────────────────────────────────────────────
EOF
