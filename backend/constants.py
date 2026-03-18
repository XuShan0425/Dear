from pathlib import Path

#下面代码实现的功能：定义服务端全局常量配置
ROOT_DIR = Path(__file__).resolve().parent.parent
INDEX_FILE = ROOT_DIR / "index.html"
ENV_FILE = ROOT_DIR / ".env"
DB_FILE = ROOT_DIR / "dear.db"
MAX_HISTORY_ITEMS = 20
SESSION_COOKIE_NAME = "xiaomo_session"
SESSION_TTL_HOURS = 24 * 7
PBKDF2_ITERATIONS = 200_000
