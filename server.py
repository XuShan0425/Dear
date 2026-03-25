#!/usr/bin/env python3
import os
from http.server import ThreadingHTTPServer

from backend.admin_auth import ensure_admin_user_from_env
from backend.constants import ENV_FILE
from backend.db import cleanup_expired_sessions, init_db
from backend.env_utils import load_env
from backend.http_handler import XiaoMoHandler


#下面代码实现的功能：启动 VPS 版服务端程序

def main():
    load_env(ENV_FILE)
    init_db()
    ensure_admin_user_from_env()
    cleanup_expired_sessions()

    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8080"))

    server = ThreadingHTTPServer((host, port), XiaoMoHandler)
    print(f"XiaoMo server running at http://{host}:{port}")
    server.serve_forever()


#下面代码实现的功能：脚本入口
if __name__ == "__main__":
    main()
