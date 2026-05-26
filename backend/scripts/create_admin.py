import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend"))
os.chdir(ROOT / "backend")

from werkzeug.security import generate_password_hash
import pymysql
from config.env_settings import load_env, settings

load_env()

username = os.environ.get("ADMIN_USERNAME", "admin")
email = os.environ.get("ADMIN_EMAIL", "admin@nankai.edu.cn")
password = os.environ.get("ADMIN_PASSWORD", "admin123")

conn = pymysql.connect(
    host=settings.MYSQL_HOST,
    user=settings.MYSQL_USER,
    password=settings.MYSQL_PASSWORD,
    database=settings.MYSQL_DATABASE,
    charset="utf8mb4",
)
pw = generate_password_hash(password)
with conn.cursor() as cur:
    cur.execute("SELECT user_id FROM User WHERE username = %s OR email = %s", (username, email))
    if cur.fetchone():
        cur.execute(
            "UPDATE User SET password_hash = %s, role = 'admin' WHERE username = %s OR email = %s",
            (pw, username, email),
        )
        print(f"已更新管理员: {username}")
    else:
        cur.execute(
            "INSERT INTO User (username, email, password_hash, role) VALUES (%s, %s, %s, 'admin')",
            (username, email, pw),
        )
        print(f"已创建管理员: {username} / {email}")
conn.commit()
conn.close()
print(f"默认密码: {password} （请登录后立即修改）")
