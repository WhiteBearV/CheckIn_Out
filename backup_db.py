#!/usr/bin/env python3
"""
backup_db.py — สำรองฐานข้อมูล PostgreSQL อัตโนมัติ
  - บันทึกที่ backups/YYYY-MM-DD_HH-MM-SS.sql.gz
  - เก็บ daily  7 ไฟล์ล่าสุด
  - เก็บ weekly 4 ไฟล์ล่าสุด  (ทุกวันอาทิตย์)
  - เก็บ yearly 3 ไฟล์ล่าสุด  (วันที่ 1 ม.ค.)

รัน: python backup_db.py
     python backup_db.py --dry-run
"""

import os
import sys
import json
import gzip
import shutil
import argparse
import subprocess
from datetime import datetime
from pathlib import Path

BASE_DIR    = Path(__file__).parent
BACKUP_DIR  = BASE_DIR / "backups"
CFG_FILE    = BASE_DIR / "db_config.json"

KEEP_DAILY  = int(os.environ.get("BACKUP_KEEP_DAILY",  7))
KEEP_WEEKLY = int(os.environ.get("BACKUP_KEEP_WEEKLY", 4))
KEEP_YEARLY = int(os.environ.get("BACKUP_KEEP_YEARLY", 3))


def log(msg: str):
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}")


def load_db_config() -> dict:
    with open(CFG_FILE) as f:
        cfg = json.load(f)
    return cfg[cfg["mode"]]


def run_backup(cfg: dict, out_path: Path, dry_run: bool) -> bool:
    if dry_run:
        log(f"[DRY] จะสำรองไปที่ {out_path.name}")
        return True

    env = os.environ.copy()
    env["PGPASSWORD"] = cfg["password"]

    cmd = [
        "pg_dump",
        "-h", cfg["host"],
        "-p", str(cfg["port"]),
        "-U", cfg["user"],
        "-d", cfg["database"],
        "--no-password",
        "-F", "plain",
    ]

    BACKUP_DIR.mkdir(exist_ok=True)
    try:
        result = subprocess.run(cmd, capture_output=True, env=env)
        if result.returncode != 0:
            log(f"pg_dump error: {result.stderr.decode()}")
            return False

        with gzip.open(out_path, "wb") as f:
            f.write(result.stdout)

        size_kb = out_path.stat().st_size // 1024
        log(f"สำรองสำเร็จ → {out_path.name} ({size_kb} KB)")
        return True
    except Exception as e:
        log(f"backup failed: {e}")
        return False


def rotate(backup_type: str, keep: int, dry_run: bool):
    files = sorted(BACKUP_DIR.glob(f"*_{backup_type}.sql.gz"))
    to_delete = files[:-keep] if len(files) > keep else []
    for f in to_delete:
        if dry_run:
            log(f"[DRY] จะลบ {f.name}")
        else:
            f.unlink()
            log(f"ลบเก่า: {f.name}")


def main():
    parser = argparse.ArgumentParser(description="FaceReg PostgreSQL backup")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    now   = datetime.now()
    stamp = now.strftime("%Y-%m-%d_%H-%M-%S")

    # ตัดสินใจว่าเป็น backup ประเภทไหน
    if now.month == 1 and now.day == 1:
        backup_type = "yearly"
        keep        = KEEP_YEARLY
    elif now.weekday() == 6:  # อาทิตย์
        backup_type = "weekly"
        keep        = KEEP_WEEKLY
    else:
        backup_type = "daily"
        keep        = KEEP_DAILY

    out_path = BACKUP_DIR / f"{stamp}_{backup_type}.sql.gz"

    log(f"{'[DRY RUN] ' if args.dry_run else ''}เริ่ม backup ({backup_type})")

    cfg = load_db_config()
    log(f"DB: {cfg['database']} @ {cfg['host']}:{cfg['port']}")

    ok = run_backup(cfg, out_path, args.dry_run)
    if ok:
        rotate(backup_type, keep, args.dry_run)
        log(f"เสร็จ — เก็บ daily≤{KEEP_DAILY}, weekly≤{KEEP_WEEKLY}, yearly≤{KEEP_YEARLY}")
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()
