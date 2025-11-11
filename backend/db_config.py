# db_config.py
import os

def _int(val, default):
    try:
        return int(val)
    except Exception:
        return default

DB_CONFIG = {
    "host": os.getenv("DB_HOST", "127.0.0.1"),
    "port": _int(os.getenv("DB_PORT", "3306"), 3306),
    "user": os.getenv("DB_USER", "root"),
    "password": os.getenv("DB_PASSWORD", ""),
    "database": os.getenv("DB_NAME", "marmudb"),
}
