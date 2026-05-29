#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────
# ติดตั้ง systemd services + timers ทั้งหมดสำหรับ FaceReg
# รัน:  sudo bash deploy/install_service.sh
#
# Script นี้จะ substitute path/user อัตโนมัติให้ตรงกับ environment ปัจจุบัน:
#   - FACEREG_DIR  = path ของ repo (autodetect จาก script location)
#   - FACEREG_USER = user ที่จะ own service (default = invoker user)
#
# Override ได้ด้วย env var:
#   sudo FACEREG_DIR=/opt/facereg FACEREG_USER=facereg bash deploy/install_service.sh
# ─────────────────────────────────────────────────────────────────────
set -euo pipefail

if [[ $EUID -ne 0 ]]; then
    echo "[ERR] ต้องรันด้วย sudo:  sudo bash deploy/install_service.sh"
    exit 1
fi

# ─── Auto-detect paths / user ────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEFAULT_DIR="$(dirname "$SCRIPT_DIR")"   # ../  (repo root)
DEFAULT_USER="${SUDO_USER:-$(whoami)}"

FACEREG_DIR="${FACEREG_DIR:-$DEFAULT_DIR}"
FACEREG_USER="${FACEREG_USER:-$DEFAULT_USER}"

# Sanity check
if [[ ! -d "$FACEREG_DIR" ]]; then
    echo "[ERR] FACEREG_DIR ไม่มีจริง: $FACEREG_DIR"
    exit 1
fi
if [[ ! -x "$FACEREG_DIR/venv/bin/python" ]]; then
    echo "[ERR] ไม่มี $FACEREG_DIR/venv/bin/python — ติดตั้ง venv ก่อน:"
    echo "      cd $FACEREG_DIR && python3 -m venv venv && venv/bin/pip install -r requirements.txt"
    exit 1
fi
if ! id "$FACEREG_USER" &>/dev/null; then
    echo "[ERR] user '$FACEREG_USER' ไม่มีจริง"
    exit 1
fi
FACEREG_GROUP="$(id -gn "$FACEREG_USER")"

echo "════════════════════════════════════════════════════════════════"
echo " FaceReg systemd installer"
echo "════════════════════════════════════════════════════════════════"
echo "  Repo path : $FACEREG_DIR"
echo "  Run as    : $FACEREG_USER:$FACEREG_GROUP"
echo "════════════════════════════════════════════════════════════════"
echo ""

SYSTEMD_DIR="/etc/systemd/system"

# ─── helper: install unit พร้อม substitute placeholder ───────────────
install_unit() {
    local name="$1"
    local src="$SCRIPT_DIR/${name}"
    local dst="$SYSTEMD_DIR/${name}"
    if [[ ! -f "$src" ]]; then
        echo "[SKIP] ไม่พบ $src"
        return
    fi
    # แทนที่ hardcoded path/user ด้วยค่าจริงตอน install
    sed \
        -e "s|User=maeb|User=$FACEREG_USER|g" \
        -e "s|Group=maeb|Group=$FACEREG_GROUP|g" \
        -e "s|/home/maeb/internship_work/FaceReg|$FACEREG_DIR|g" \
        "$src" > "$dst"
    chmod 644 "$dst"
    echo "  → $dst"
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

NOTE: ถ้ายังไม่ตั้ง env ต้องแก้ /etc/systemd/system/facereg-stream.service
เพิ่ม Environment=... ตามค่าใน $FACEREG_DIR/.env.example
แล้วรัน: sudo systemctl daemon-reload && sudo systemctl restart facereg-stream
────────────────────────────────────────────────────────
EOF
