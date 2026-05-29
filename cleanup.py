#!/usr/bin/env python3
"""
cleanup.py — ลบไฟล์รูปเก่าอัตโนมัติ
  - PicSAVE/  : เก็บ PICSAVE_DAYS วัน (default 365)
  - live_snap*: เก็บ SNAP_DAYS วัน    (default 7)

รัน: python cleanup.py
     python cleanup.py --dry-run   ← ดูว่าจะลบอะไรบ้าง โดยไม่ลบจริง
"""

import os
import sys
import argparse
import shutil
from datetime import datetime, timedelta
from pathlib import Path

BASE_DIR      = Path(__file__).parent
PICSAVE_DIR   = BASE_DIR / "PicSAVE"
PICSAVE_DAYS  = int(os.environ.get("PICSAVE_RETENTION_DAYS", 365))
SNAP_DAYS     = int(os.environ.get("SNAP_RETENTION_DAYS", 7))


def log(msg: str):
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}")


def cleanup_picsave(cutoff: datetime, dry_run: bool) -> tuple[int, int]:
    """ลบไฟล์ใน PicSAVE/YYYY/MM/DD/ ที่เก่ากว่า cutoff"""
    deleted_files = 0
    deleted_dirs  = 0

    if not PICSAVE_DIR.exists():
        return 0, 0

    for year_dir in sorted(PICSAVE_DIR.iterdir()):
        if not year_dir.is_dir() or not year_dir.name.isdigit():
            continue
        for month_dir in sorted(year_dir.iterdir()):
            if not month_dir.is_dir() or not month_dir.name.isdigit():
                continue
            for day_dir in sorted(month_dir.iterdir()):
                if not day_dir.is_dir() or not day_dir.name.isdigit():
                    continue
                try:
                    dir_date = datetime(int(year_dir.name), int(month_dir.name), int(day_dir.name))
                except ValueError:
                    continue

                if dir_date < cutoff:
                    files = list(day_dir.glob("*.jpg"))
                    if dry_run:
                        log(f"[DRY] จะลบ {day_dir.relative_to(BASE_DIR)}/ ({len(files)} ไฟล์)")
                    else:
                        shutil.rmtree(day_dir)
                        log(f"ลบ {day_dir.relative_to(BASE_DIR)}/ ({len(files)} ไฟล์)")
                    deleted_files += len(files)
                    deleted_dirs  += 1

    # ลบ month/year ที่ว่างแล้ว
    if not dry_run:
        for year_dir in PICSAVE_DIR.iterdir():
            if not year_dir.is_dir(): continue
            for month_dir in year_dir.iterdir():
                if not month_dir.is_dir(): continue
                if not any(month_dir.iterdir()):
                    month_dir.rmdir()
            if not any(year_dir.iterdir()):
                year_dir.rmdir()

    return deleted_files, deleted_dirs


def cleanup_live_snaps(cutoff: datetime, dry_run: bool) -> int:
    """ลบ live_snap* และ live_snapfull* ที่เก่ากว่า cutoff"""
    deleted = 0
    patterns = ["live_snap_*.jpg", "live_snapfull_*.jpg"]

    for pattern in patterns:
        for f in BASE_DIR.glob(pattern):
            mtime = datetime.fromtimestamp(f.stat().st_mtime)
            if mtime < cutoff:
                if dry_run:
                    log(f"[DRY] จะลบ {f.name}")
                else:
                    f.unlink()
                    log(f"ลบ {f.name}")
                deleted += 1

    return deleted


def main():
    parser = argparse.ArgumentParser(description="FaceReg image cleanup")
    parser.add_argument("--dry-run", action="store_true", help="แสดงว่าจะลบอะไร โดยไม่ลบจริง")
    parser.add_argument("--picsave-days", type=int, default=PICSAVE_DAYS,
                        help=f"เก็บ PicSAVE กี่วัน (default {PICSAVE_DAYS})")
    parser.add_argument("--snap-days", type=int, default=SNAP_DAYS,
                        help=f"เก็บ live_snap กี่วัน (default {SNAP_DAYS})")
    args = parser.parse_args()

    now = datetime.now()
    picsave_cutoff = now - timedelta(days=args.picsave_days)
    snap_cutoff    = now - timedelta(days=args.snap_days)

    log(f"{'[DRY RUN] ' if args.dry_run else ''}เริ่ม cleanup")
    log(f"PicSAVE   : ลบที่เก่ากว่า {picsave_cutoff.strftime('%Y-%m-%d')} (>{args.picsave_days} วัน)")
    log(f"live_snap : ลบที่เก่ากว่า {snap_cutoff.strftime('%Y-%m-%d')}  (>{args.snap_days} วัน)")

    files, dirs = cleanup_picsave(picsave_cutoff, args.dry_run)
    snaps       = cleanup_live_snaps(snap_cutoff, args.dry_run)

    log(f"เสร็จ — PicSAVE: {files} ไฟล์ / {dirs} วัน-folder | live_snap: {snaps} ไฟล์")


if __name__ == "__main__":
    main()
