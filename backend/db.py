import sqlite3
import threading
from datetime import datetime, timezone

from backend.constants import DB_FILE

#下面代码实现的功能：初始化数据库连接与线程锁
DB_LOCK = threading.Lock()
DB_CONN = sqlite3.connect(DB_FILE, check_same_thread=False)
DB_CONN.row_factory = sqlite3.Row


#下面代码实现的功能：获取 UTC 当前时间

def now_utc() -> datetime:
    return datetime.now(timezone.utc)


#下面代码实现的功能：格式化时间为 ISO 文本

def isoformat(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


#下面代码实现的功能：解析 ISO 时间文本

def parse_iso(ts: str) -> datetime:
    return datetime.fromisoformat(ts)


#下面代码实现的功能：创建用户与会话表结构

def init_db() -> None:
    with DB_LOCK:
        DB_CONN.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        DB_CONN.execute(
            """
            CREATE TABLE IF NOT EXISTS sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                token_hash TEXT NOT NULL UNIQUE,
                user_id INTEGER NOT NULL,
                expires_at TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(user_id) REFERENCES users(id)
            )
            """
        )
        DB_CONN.execute("CREATE INDEX IF NOT EXISTS idx_sessions_expires_at ON sessions(expires_at)")
        DB_CONN.commit()


#下面代码实现的功能：清理过期会话

def cleanup_expired_sessions() -> None:
    with DB_LOCK:
        DB_CONN.execute("DELETE FROM sessions WHERE expires_at <= ?", (isoformat(now_utc()),))
        DB_CONN.commit()
