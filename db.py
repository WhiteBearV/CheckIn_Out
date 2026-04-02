import json
import psycopg

with open("db_config.json") as f:
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
