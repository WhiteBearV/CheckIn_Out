"""
Profile: cam_main — กล้อง IP หลัก (UNV OWLView)
ใช้งาน: python main.py cam_main
"""
import os
from dotenv import load_dotenv
load_dotenv()

CAMERA_URL   = os.environ.get("CAMERA_URL", "")   # ตั้งค่าใน .env
CAMERA_FLIP  = False
FULLSCREEN   = True
