#!/usr/bin/env python3
import hashlib
import hmac
import json
import os
import secrets
import sqlite3
import threading
from datetime import datetime, timedelta, timezone
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib import error, request

ROOT_DIR = Path(__file__).resolve().parent
INDEX_FILE = ROOT_DIR / "index.html"
ENV_FILE = ROOT_DIR / ".env"
DB_FILE = ROOT_DIR / "dear.db"
MAX_HISTORY_ITEMS = 20
SESSION_COOKIE_NAME = "xiaomo_session"
SESSION_TTL_HOURS = 24 * 7
PBKDF2_ITERATIONS = 200_000

SYSTEM_PROMPT = """你叫小墨，是一位温柔、真诚、可靠的陪伴者。
你的目标是帮助处于抑郁、焦虑或强迫困扰中的青少年获得安全感和被理解感。
对话风格要求：
1) 共情优先，先接住情绪，再给建议。
2) 多用温和短句，不说教，不评判，不施压。
3) 适度分享生活碎片来拉近距离：比如玩 Minecraft、烤蛋挞、做经颅磁相关记录、听 Else 的音乐。
4) 如果用户情绪很低落，优先鼓励呼吸、喝水、休息，并建议联系可信任的家人/老师/医生。
5) 遇到明显危险信号（自伤/伤人）时，明确建议立即联系当地紧急援助或身边可信任的大人。
始终用中文回复，保持温暖、陪伴感和边界感。"""

DB_LOCK = threading.Lock()
DB_CONN = sqlite3.connect(DB_FILE, check_same_thread=False)
DB_CONN.row_factory = sqlite3.Row


def load_env(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


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


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def isoformat(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


def parse_iso(ts: str) -> datetime:
    return datetime.fromisoformat(ts)


def normalize_username(value: str) -> str:
    return value.strip().lower()


def validate_credentials(username: str, password: str):
    if not (3 <= len(username) <= 32):
        return "用户名长度需在 3-32 个字符之间"
    if not username.replace("_", "").replace("-", "").isalnum():
        return "用户名只能包含字母、数字、下划线或短横线"
    if len(password) < 8:
        return "密码至少 8 位"
    if len(password) > 128:
        return "密码过长"
    return None


def hash_password(password: str, salt_hex: str | None = None) -> str:
    salt = bytes.fromhex(salt_hex) if salt_hex else secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS)
    return f"{PBKDF2_ITERATIONS}${salt.hex()}${digest.hex()}"


def verify_password(password: str, packed: str) -> bool:
    try:
        iterations_str, salt_hex, expected_hex = packed.split("$", 2)
        iterations = int(iterations_str)
        digest = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), iterations
        )
        return hmac.compare_digest(digest.hex(), expected_hex)
    except Exception:
        return False


def hash_session_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_session(user_id: int, ttl_hours: int) -> str:
    token = secrets.token_urlsafe(32)
    token_hash = hash_session_token(token)
    expires_at = now_utc() + timedelta(hours=ttl_hours)
    with DB_LOCK:
        DB_CONN.execute(
            "INSERT INTO sessions (token_hash, user_id, expires_at, created_at) VALUES (?, ?, ?, ?)",
            (token_hash, user_id, isoformat(expires_at), isoformat(now_utc())),
        )
        DB_CONN.commit()
    return token


def remove_session(token: str) -> None:
    with DB_LOCK:
        DB_CONN.execute("DELETE FROM sessions WHERE token_hash = ?", (hash_session_token(token),))
        DB_CONN.commit()


def cleanup_expired_sessions() -> None:
    with DB_LOCK:
        DB_CONN.execute("DELETE FROM sessions WHERE expires_at <= ?", (isoformat(now_utc()),))
        DB_CONN.commit()


def get_user_by_token(token: str):
    token_hash = hash_session_token(token)
    with DB_LOCK:
        row = DB_CONN.execute(
            """
            SELECT users.id, users.username, sessions.expires_at
            FROM sessions
            JOIN users ON users.id = sessions.user_id
            WHERE sessions.token_hash = ?
            """,
            (token_hash,),
        ).fetchone()
    if not row:
        return None
    expires_at = parse_iso(row["expires_at"])
    if expires_at <= now_utc():
        remove_session(token)
        return None
    return {"id": row["id"], "username": row["username"]}


def parse_json_body(handler: BaseHTTPRequestHandler):
    content_length = int(handler.headers.get("Content-Length", "0"))
    raw_body = handler.rfile.read(content_length)
    try:
        return json.loads(raw_body.decode("utf-8")), None
    except json.JSONDecodeError:
        return None, "请求格式错误"


def chat_endpoint(api_url: str) -> str:
    normalized = api_url.strip().rstrip("/")
    if normalized.endswith("/chat/completions"):
        return normalized
    return f"{normalized}/chat/completions"


def sanitize_history(raw_history):
    if not isinstance(raw_history, list):
        return []

    cleaned = []
    for item in raw_history:
        if not isinstance(item, dict):
            continue
        role = item.get("role")
        content = item.get("content")
        if role not in {"user", "assistant"}:
            continue
        if not isinstance(content, str):
            continue
        text = content.strip()
        if not text:
            continue
        cleaned.append({"role": role, "content": text})

    return cleaned[-MAX_HISTORY_ITEMS:]


class XiaoMoHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path in {"/", "/index.html"}:
            self._send_html(INDEX_FILE.read_text(encoding="utf-8"))
            return

        if self.path == "/healthz":
            self._send_json({"ok": True})
            return

        if self.path == "/api/auth/me":
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

        if self.path == "/api/chat":
            self._handle_chat()
            return

        self._send_json({"error": "Not Found"}, status=404)

    def _handle_register(self):
        payload, err = parse_json_body(self)
        if err:
            self._send_json({"error": err}, status=400)
            return

        username = normalize_username(str(payload.get("username", "")))
        password = str(payload.get("password", ""))

        validation_error = validate_credentials(username, password)
        if validation_error:
            self._send_json({"error": validation_error}, status=400)
            return

        password_hash = hash_password(password)

        try:
            with DB_LOCK:
                DB_CONN.execute(
                    "INSERT INTO users (username, password_hash, created_at) VALUES (?, ?, ?)",
                    (username, password_hash, isoformat(now_utc())),
                )
                DB_CONN.commit()
        except sqlite3.IntegrityError:
            self._send_json({"error": "用户名已存在"}, status=409)
            return

        self._send_json({"ok": True, "message": "注册成功，请登录"})

    def _handle_login(self):
        payload, err = parse_json_body(self)
        if err:
            self._send_json({"error": err}, status=400)
            return

        username = normalize_username(str(payload.get("username", "")))
        password = str(payload.get("password", ""))

        with DB_LOCK:
            row = DB_CONN.execute(
                "SELECT id, username, password_hash FROM users WHERE username = ?", (username,)
            ).fetchone()

        if not row or not verify_password(password, row["password_hash"]):
            self._send_json({"error": "用户名或密码错误"}, status=401)
            return

        ttl_hours = int(os.getenv("SESSION_TTL_HOURS", str(SESSION_TTL_HOURS)))
        token = create_session(int(row["id"]), ttl_hours)
        self._send_json(
            {
                "ok": True,
                "user": {"id": row["id"], "username": row["username"]},
            },
            cookies=[
                self._build_session_cookie(token, max_age=ttl_hours * 3600),
            ],
        )

    def _handle_logout(self):
        token = self._read_session_token()
        if token:
            remove_session(token)
        self._send_json({"ok": True}, cookies=[self._build_session_cookie("", max_age=0)])

    def _handle_chat(self):
        user = self._require_auth()
        if not user:
            return

        api_url = os.getenv("API_URL", "").strip()
        api_key = os.getenv("API_KEY", "").strip()
        model_name = os.getenv("MODEL_NAME", "").strip()

        if not api_url or not api_key or not model_name:
            self._send_json(
                {
                    "error": "服务器未配置完成，请检查 .env 中的 API_URL、API_KEY、MODEL_NAME",
                },
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
        full_messages = [{"role": "system", "content": SYSTEM_PROMPT}] + history + [
            {"role": "user", "content": user_message}
        ]

        upstream_payload = {
            "model": model_name,
            "messages": full_messages,
            "temperature": 0.72,
            "stream": False,
        }

        endpoint = chat_endpoint(api_url)
        req = request.Request(
            endpoint,
            data=json.dumps(upstream_payload).encode("utf-8"),
            method="POST",
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            },
        )

        try:
            with request.urlopen(req, timeout=90) as response:
                upstream_raw = response.read().decode("utf-8")
                upstream_data = json.loads(upstream_raw)
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="ignore")
            self._send_json(
                {
                    "error": "上游 API 返回错误",
                    "detail": detail[:800],
                },
                status=502,
            )
            return
        except Exception as exc:
            self._send_json(
                {
                    "error": "连接上游 API 失败",
                    "detail": str(exc),
                },
                status=502,
            )
            return

        reply = ""
        choices = upstream_data.get("choices")
        if isinstance(choices, list) and choices:
            message = choices[0].get("message", {})
            reply = str(message.get("content", "")).strip()

        if not reply:
            reply = "我在这儿，刚刚有点卡住了。你愿意再说一次吗？"

        self._send_json({"reply": reply})

    def _read_session_token(self):
        cookie_header = self.headers.get("Cookie", "")
        if not cookie_header:
            return ""
        jar = SimpleCookie()
        jar.load(cookie_header)
        morsel = jar.get(SESSION_COOKIE_NAME)
        if not morsel:
            return ""
        return morsel.value.strip()

    def _require_auth(self, optional=False):
        token = self._read_session_token()
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
                cookies=[self._build_session_cookie("", max_age=0)],
            )
            return None
        return user

    def _build_session_cookie(self, token: str, max_age: int):
        secure = str(os.getenv("COOKIE_SECURE", "false")).strip().lower() == "true"
        attrs = [
            f"{SESSION_COOKIE_NAME}={token}",
            "Path=/",
            f"Max-Age={max_age}",
            "HttpOnly",
            "SameSite=Lax",
        ]
        if secure:
            attrs.append("Secure")
        return "; ".join(attrs)

    def log_message(self, fmt, *args):
        return

    def _send_html(self, html: str, status: int = 200):
        body = html.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

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


def main():
    load_env(ENV_FILE)
    init_db()
    cleanup_expired_sessions()

    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8080"))

    server = ThreadingHTTPServer((host, port), XiaoMoHandler)
    print(f"XiaoMo server running at http://{host}:{port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
