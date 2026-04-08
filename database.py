import os
import pymysql
from pymysql.cursors import DictCursor

# Render inyecta DATABASE_URL, pero usamos variables separadas para Webempresa MySQL
DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "user": os.getenv("DB_USER", "root"),
    "password": os.getenv("DB_PASS", ""),
    "database": os.getenv("DB_NAME", "whes_pro"),
    "port": int(os.getenv("DB_PORT", 3306)),
    "cursorclass": DictCursor,
    "charset": "utf8mb4"
}

def get_db():
    conn = pymysql.connect(**DB_CONFIG)
    try:
        yield conn
    finally:
        conn.close()