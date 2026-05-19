import json
import os
import psycopg

# Docker: ถ้ามี env var DB_HOST ให้ใช้แทน db_config.json
if os.environ.get("DB_HOST"):
    DB_CONFIG = {
        "host":     os.environ["DB_HOST"],
        "port":     int(os.environ.get("DB_PORT", 5432)),
        "database": os.environ.get("DB_NAME", "face_attendance"),
        "user":     os.environ.get("DB_USER", "face_user"),
        "password": os.environ.get("DB_PASSWORD", ""),
    }
else:
    _db_cfg_path = os.path.join(os.path.dirname(__file__), "db_config.json")
    with open(_db_cfg_path) as f:
        _cfg = json.load(f)
    DB_CONFIG = _cfg[_cfg["mode"]]

def get_connection():
    return psycopg.connect(
        host=DB_CONFIG["host"],
        port=DB_CONFIG["port"],
        dbname=DB_CONFIG["database"],
        user=DB_CONFIG["user"],
        password=DB_CONFIG["password"],
    )
