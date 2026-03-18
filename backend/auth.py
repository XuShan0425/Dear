import hashlib
import hmac
import os
import secrets
from datetime import timedelta
from http.cookies import SimpleCookie

from backend.constants import PBKDF2_ITERATIONS, SESSION_COOKIE_NAME, SESSION_TTL_HOURS
from backend.db import DB_CONN, DB_LOCK, cleanup_expired_sessions, isoformat, now_utc, parse_iso


#下面代码实现的功能：标准化用户名

def normalize_username(value: str) -> str:
    return value.strip().lower()


#下面代码实现的功能：校验用户名与密码的格式

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


#下面代码实现的功能：生成密码哈希

def hash_password(password: str, salt_hex: str | None = None) -> str:
    salt = bytes.fromhex(salt_hex) if salt_hex else secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS)
    return f"{PBKDF2_ITERATIONS}${salt.hex()}${digest.hex()}"


#下面代码实现的功能：验证用户密码

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


#下面代码实现的功能：对 session token 做 SHA256 摘要

def hash_session_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


#下面代码实现的功能：创建 session 并写入数据库

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


#下面代码实现的功能：删除指定 token 的 session

def remove_session(token: str) -> None:
    with DB_LOCK:
        DB_CONN.execute("DELETE FROM sessions WHERE token_hash = ?", (hash_session_token(token),))
        DB_CONN.commit()


#下面代码实现的功能：按用户 ID 删除所有会话

def remove_all_sessions_by_user(user_id: int) -> None:
    with DB_LOCK:
        DB_CONN.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
        DB_CONN.commit()


#下面代码实现的功能：按 token 查询有效用户

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


#下面代码实现的功能：读取请求中的 session cookie

def read_session_token_from_headers(headers) -> str:
    cookie_header = headers.get("Cookie", "")
    if not cookie_header:
        return ""
    jar = SimpleCookie()
    jar.load(cookie_header)
    morsel = jar.get(SESSION_COOKIE_NAME)
    if not morsel:
        return ""
    return morsel.value.strip()


#下面代码实现的功能：构建 Set-Cookie 响应头

def build_session_cookie(token: str, max_age: int):
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


#下面代码实现的功能：用户注册

def register_user(username: str, password: str):
    normalized = normalize_username(username)
    error = validate_credentials(normalized, password)
    if error:
        return None, error, 400

    password_hash = hash_password(password)
    try:
        with DB_LOCK:
            DB_CONN.execute(
                "INSERT INTO users (username, password_hash, created_at) VALUES (?, ?, ?)",
                (normalized, password_hash, isoformat(now_utc())),
            )
            DB_CONN.commit()
    except Exception:
        return None, "用户名已存在", 409

    return {"ok": True, "message": "注册成功，请登录"}, None, 200


#下面代码实现的功能：用户登录

def login_user(username: str, password: str):
    normalized = normalize_username(username)
    with DB_LOCK:
        row = DB_CONN.execute(
            "SELECT id, username, password_hash FROM users WHERE username = ?", (normalized,)
        ).fetchone()

    if not row or not verify_password(password, row["password_hash"]):
        return None, "用户名或密码错误", 401, None

    cleanup_expired_sessions()
    ttl_hours = int(os.getenv("SESSION_TTL_HOURS", str(SESSION_TTL_HOURS)))
    token = create_session(int(row["id"]), ttl_hours)
    cookie = build_session_cookie(token, max_age=ttl_hours * 3600)
    payload = {"ok": True, "user": {"id": row["id"], "username": row["username"]}}
    return payload, None, 200, cookie
