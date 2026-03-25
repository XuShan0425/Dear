"""
这个文件实现什么功能：定义 Dear 服务端的全局常量、关键文件路径与默认配置。
它负责什么：集中维护前端静态文件路径、数据库路径、Cookie 名称、默认会话时长等共享常量。
它不负责什么：不处理环境变量加载、不执行数据库读写、不处理业务逻辑。
对外暴露什么：ROOT_DIR、INDEX_FILE、ADMIN_INDEX_FILE、ENV_FILE、DB_FILE 等全局常量。
依赖哪些关键模块：pathlib。
"""

from pathlib import Path

#下面代码实现的功能：定义服务端全局常量配置
ROOT_DIR = Path(__file__).resolve().parent.parent
INDEX_FILE = ROOT_DIR / "index.html"
ADMIN_INDEX_FILE = ROOT_DIR / "admin.html"
ENV_FILE = ROOT_DIR / ".env"
DB_FILE = ROOT_DIR / "dear.db"
MAX_HISTORY_ITEMS = 20
SESSION_COOKIE_NAME = "xiaomo_session"
ADMIN_SESSION_COOKIE_NAME = "dear_admin_session"
SESSION_TTL_HOURS = 24 * 7
ADMIN_SESSION_TTL_HOURS = 12
PBKDF2_ITERATIONS = 200_000
