import json
import os
from http.server import BaseHTTPRequestHandler

from backend.auth import (
    build_session_cookie,
    get_user_by_token,
    login_user,
    read_session_token_from_headers,
    register_user,
    remove_all_sessions_by_user,
    remove_session,
)
from backend.chat import fetch_chat_reply, sanitize_history
from backend.constants import INDEX_FILE
from backend.db import cleanup_expired_sessions


#下面代码实现的功能：解析 JSON 请求体

def parse_json_body(handler: BaseHTTPRequestHandler):
    content_length = int(handler.headers.get("Content-Length", "0"))
    raw_body = handler.rfile.read(content_length)
    try:
        return json.loads(raw_body.decode("utf-8")), None
    except json.JSONDecodeError:
        return None, "请求格式错误"


#下面代码实现的功能：定义 HTTP 路由处理器

class XiaoMoHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path in {"/", "/index.html"}:
            self._send_html(INDEX_FILE.read_text(encoding="utf-8"))
            return

        if self.path == "/healthz":
            self._send_json({"ok": True})
            return

        if self.path == "/api/auth/me":
            cleanup_expired_sessions()
            user = self._require_auth(optional=True)
            if not user:
                self._send_json({"authenticated": False})
                return
            self._send_json({"authenticated": True, "user": user})
            return

        self._send_json({"error": "Not Found"}, status=404)

    def do_POST(self):
        if self.path == "/api/auth/register":
            self._handle_register()
            return

        if self.path == "/api/auth/login":
            self._handle_login()
            return

        if self.path == "/api/auth/logout":
            self._handle_logout()
            return

        if self.path == "/api/auth/logout_all":
            self._handle_logout_all()
            return

        if self.path == "/api/chat":
            self._handle_chat()
            return

        self._send_json({"error": "Not Found"}, status=404)

    #下面代码实现的功能：处理用户注册
    def _handle_register(self):
        payload, err = parse_json_body(self)
        if err:
            self._send_json({"error": err}, status=400)
            return

        data, error_msg, status = register_user(
            str(payload.get("username", "")), str(payload.get("password", ""))
        )
        if error_msg:
            self._send_json({"error": error_msg}, status=status)
            return
        self._send_json(data, status=status)

    #下面代码实现的功能：处理用户登录
    def _handle_login(self):
        payload, err = parse_json_body(self)
        if err:
            self._send_json({"error": err}, status=400)
            return

        data, error_msg, status, cookie = login_user(
            str(payload.get("username", "")), str(payload.get("password", ""))
        )
        if error_msg:
            self._send_json({"error": error_msg}, status=status)
            return
        self._send_json(data, status=status, cookies=[cookie])

    #下面代码实现的功能：处理当前会话登出
    def _handle_logout(self):
        token = read_session_token_from_headers(self.headers)
        if token:
            remove_session(token)
        self._send_json({"ok": True}, cookies=[build_session_cookie("", max_age=0)])

    #下面代码实现的功能：处理账号全部会话登出
    def _handle_logout_all(self):
        user = self._require_auth()
        if not user:
            return
        remove_all_sessions_by_user(user["id"])
        self._send_json({"ok": True}, cookies=[build_session_cookie("", max_age=0)])

    #下面代码实现的功能：处理聊天请求
    def _handle_chat(self):
        user = self._require_auth()
        if not user:
            return

        api_url = os.getenv("API_URL", "").strip()
        api_key = os.getenv("API_KEY", "").strip()
        model_name = os.getenv("MODEL_NAME", "").strip()

        if not api_url or not api_key or not model_name:
            self._send_json(
                {"error": "服务器未配置完成，请检查 .env 中的 API_URL、API_KEY、MODEL_NAME"},
                status=500,
            )
            return

        payload, err = parse_json_body(self)
        if err:
            self._send_json({"error": err}, status=400)
            return

        user_message = str(payload.get("message", "")).strip()
        if not user_message:
            self._send_json({"error": "消息不能为空"}, status=400)
            return

        history = sanitize_history(payload.get("history", []))
        data, error_payload, status = fetch_chat_reply(
            api_url=api_url,
            api_key=api_key,
            model_name=model_name,
            user_message=user_message,
            history=history,
        )
        if error_payload:
            self._send_json(error_payload, status=status)
            return
        self._send_json(data, status=status)

    #下面代码实现的功能：校验请求的登录状态
    def _require_auth(self, optional=False):
        cleanup_expired_sessions()
        token = read_session_token_from_headers(self.headers)
        if not token:
            if optional:
                return None
            self._send_json({"error": "请先登录"}, status=401)
            return None

        user = get_user_by_token(token)
        if not user:
            if optional:
                return None
            self._send_json(
                {"error": "登录已失效，请重新登录"},
                status=401,
                cookies=[build_session_cookie("", max_age=0)],
            )
            return None
        return user

    #下面代码实现的功能：关闭默认日志输出
    def log_message(self, fmt, *args):
        return

    #下面代码实现的功能：返回 HTML 内容
    def _send_html(self, html: str, status: int = 200):
        body = html.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    #下面代码实现的功能：返回 JSON 内容
    def _send_json(self, data, status: int = 200, cookies=None):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        if cookies:
            for cookie in cookies:
                self.send_header("Set-Cookie", cookie)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
