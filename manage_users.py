"""
manage_users.py — CLI จัดการ users (login system)
=====================================================
รัน:
    python manage_users.py list
    python manage_users.py add <username> --role admin|viewer
    python manage_users.py reset-password <username>
    python manage_users.py delete <username>
    python manage_users.py bootstrap          # seed default users (ถ้าตารางว่าง)
"""

import argparse
import getpass
import sys

from dotenv import load_dotenv
load_dotenv()

import auth


def _prompt_password(prompt: str = "password: ") -> str:
    pw = getpass.getpass(prompt)
    pw2 = getpass.getpass("ยืนยัน password อีกครั้ง: ")
    if pw != pw2:
        print("✗ password ไม่ตรงกัน — ยกเลิก")
        sys.exit(1)
    return pw


def cmd_list(_args):
    rows = auth.list_users()
    if not rows:
        print("(ยังไม่มี user — รัน 'python manage_users.py bootstrap' หรือ 'add')")
        return
    print(f"{'ID':>3}  {'USERNAME':<20} {'ROLE':<8} {'LAST LOGIN':<25} CREATED")
    print("─" * 90)
    for u in rows:
        print(f"{u['id']:>3}  {u['username']:<20} {u['role']:<8} "
              f"{(u['last_login'] or '-'):<25} {u['created_at'] or '-'}")


def cmd_add(args):
    pw = _prompt_password()
    auth.add_user(args.username, pw, args.role)
    print(f"✓ เพิ่ม user '{args.username}' (role={args.role}) สำเร็จ")


def cmd_reset(args):
    pw = _prompt_password("password ใหม่: ")
    auth.set_password(args.username, pw)
    print(f"✓ เปลี่ยน password ของ '{args.username}' สำเร็จ")


def cmd_delete(args):
    if input(f"ยืนยันลบ user '{args.username}'? (yes/no): ").strip().lower() != "yes":
        print("ยกเลิก")
        return
    auth.delete_user(args.username)
    print(f"✓ ลบ user '{args.username}' สำเร็จ")


def cmd_bootstrap(_args):
    auth.bootstrap_default_users()


def main():
    p = argparse.ArgumentParser(description="จัดการ users สำหรับระบบ login")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("list", help="แสดงรายการ users").set_defaults(func=cmd_list)

    sp_add = sub.add_parser("add", help="เพิ่ม user ใหม่")
    sp_add.add_argument("username")
    sp_add.add_argument("--role", required=True, choices=["admin", "viewer"])
    sp_add.set_defaults(func=cmd_add)

    sp_reset = sub.add_parser("reset-password", help="เปลี่ยน password (admin reset)")
    sp_reset.add_argument("username")
    sp_reset.set_defaults(func=cmd_reset)

    sp_del = sub.add_parser("delete", help="ลบ user")
    sp_del.add_argument("username")
    sp_del.set_defaults(func=cmd_delete)

    sub.add_parser("bootstrap", help="seed default admin/viewer (ถ้าตารางว่าง)") \
        .set_defaults(func=cmd_bootstrap)

    args = p.parse_args()
    try:
        args.func(args)
    except (ValueError, RuntimeError) as e:
        print(f"✗ {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
