"""
这个文件实现什么功能：管理后台管理员账号、后台会话与后台登录鉴权。
它负责什么：同步环境变量中的管理员账号、处理后台登录/登出、校验后台会话有效性。
它不负责什么：不拼装后台统计面板、不处理普通用户登录、不负责页面渲染。
对外暴露什么：ensure_admin_user_from_env、login_admin、get_admin_by_token、read_admin_session_token_from_headers 等后台鉴权函数。
依赖哪些关键模块：backend.auth、backend.constants、backend.db、os、secrets。
"""

import os
import secrets
from datetime import timedelta
from http.cookies import SimpleCookie

from backend.auth import hash_password, hash_session_token, normalize_username, verify_password
from backend.constants import ADMIN_SESSION_COOKIE_NAME, ADMIN_SESSION_TTL_HOURS
from backend.db import DB_CONN, DB_LOCK, isoformat, now_utc, parse_iso


#下面代码实现的功能：判断当前环境是否已经配置后台管理员账号
def admin_auth_configured() -> bool:
    return bool(get_configured_admin_username()) and bool(os.getenv("ADMIN_PASSWORD", "").strip())


#下面代码实现的功能：统一读取并标准化管理员用户名
def get_configured_admin_username() -> str:
    return normalize_username(os.getenv("ADMIN_USERNAME", ""))


#下面代码实现的功能：创建管理员 session 并写入数据库
def create_admin_session(admin_user_id: int, ttl_hours: int) -> str:
    token = secrets.token_urlsafe(32)
    token_hash = hash_session_token(token)
    expires_at = now_utc() + timedelta(hours=ttl_hours)
    with DB_LOCK:
        DB_CONN.execute(
            """
            INSERT INTO admin_sessions (token_hash, admin_user_id, expires_at, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (token_hash, admin_user_id, isoformat(expires_at), isoformat(now_utc())),
        )
        DB_CONN.commit()
    return token


#下面代码实现的功能：清理过期的后台会话
def cleanup_expired_admin_sessions() -> None:
    with DB_LOCK:
        DB_CONN.execute("DELETE FROM admin_sessions WHERE expires_at <= ?", (isoformat(now_utc()),))
        DB_CONN.commit()


#下面代码实现的功能：删除指定管理员 session
def remove_admin_session(token: str) -> None:
    with DB_LOCK:
        DB_CONN.execute("DELETE FROM admin_sessions WHERE token_hash = ?", (hash_session_token(token),))
        DB_CONN.commit()


#下面代码实现的功能：读取请求中的后台 session cookie
def read_admin_session_token_from_headers(headers) -> str:
    cookie_header = headers.get("Cookie", "")
    if not cookie_header:
        return ""
    jar = SimpleCookie()
    jar.load(cookie_header)
    morsel = jar.get(ADMIN_SESSION_COOKIE_NAME)
    if not morsel:
        return ""
    return morsel.value.strip()


#下面代码实现的功能：构建后台专用 Set-Cookie 响应头
def build_admin_session_cookie(token: str, max_age: int):
    secure = str(os.getenv("COOKIE_SECURE", "false")).strip().lower() == "true"
    attrs = [
        f"{ADMIN_SESSION_COOKIE_NAME}={token}",
        "Path=/",
        f"Max-Age={max_age}",
        "HttpOnly",
        "SameSite=Strict",
    ]
    if secure:
        attrs.append("Secure")
    return "; ".join(attrs)


#下面代码实现的功能：按 token 查询有效管理员
def get_admin_by_token(token: str):
    if not admin_auth_configured():
        return None

    token_hash = hash_session_token(token)
    with DB_LOCK:
        row = DB_CONN.execute(
            """
            SELECT admin_users.id, admin_users.username, admin_sessions.expires_at
            FROM admin_sessions
            JOIN admin_users ON admin_users.id = admin_sessions.admin_user_id
            WHERE admin_sessions.token_hash = ?
            """,
            (token_hash,),
        ).fetchone()

    if not row:
        return None

    expires_at = parse_iso(row["expires_at"])
    if expires_at <= now_utc():
        remove_admin_session(token)
        return None

    return {"id": row["id"], "username": row["username"]}


#下面代码实现的功能：把环境变量同步成单一管理员账号
def ensure_admin_user_from_env() -> None:
    if not admin_auth_configured():
        return

    username = get_configured_admin_username()
    password = os.getenv("ADMIN_PASSWORD", "")
    password_hash = hash_password(password)

    with DB_LOCK:
        existing_rows = DB_CONN.execute("SELECT id, username FROM admin_users ORDER BY id ASC").fetchall()
        current_row = next((row for row in existing_rows if row["username"] == username), None)

        if current_row:
            admin_user_id = int(current_row["id"])
            DB_CONN.execute(
                "UPDATE admin_users SET password_hash = ? WHERE id = ?",
                (password_hash, admin_user_id),
            )
        else:
            cursor = DB_CONN.execute(
                "INSERT INTO admin_users (username, password_hash, created_at) VALUES (?, ?, ?)",
                (username, password_hash, isoformat(now_utc())),
            )
            admin_user_id = int(cursor.lastrowid)

        stale_ids = [int(row["id"]) for row in existing_rows if int(row["id"]) != admin_user_id]
        if stale_ids:
            placeholders = ",".join("?" for _ in stale_ids)
            # 当前版本只支持环境变量托管的单管理员，启动时主动回收旧管理员与其后台会话，
            # 避免主理人改了 .env 后旧账号仍然残留访问权限。
            DB_CONN.execute(
                f"DELETE FROM admin_sessions WHERE admin_user_id IN ({placeholders})",
                stale_ids,
            )
            DB_CONN.execute(f"DELETE FROM admin_users WHERE id IN ({placeholders})", stale_ids)

        DB_CONN.commit()


#下面代码实现的功能：处理后台管理员登录
def login_admin(username: str, password: str):
    if not admin_auth_configured():
        return None, "后台未配置管理员账号，请先在 .env 中设置 ADMIN_USERNAME 和 ADMIN_PASSWORD", 503, None

    normalized = normalize_username(username)
    with DB_LOCK:
        row = DB_CONN.execute(
            "SELECT id, username, password_hash FROM admin_users WHERE username = ?",
            (normalized,),
        ).fetchone()

    if not row or not verify_password(password, row["password_hash"]):
        return None, "管理员账号或密码错误", 401, None

    cleanup_expired_admin_sessions()
    ttl_hours = int(os.getenv("ADMIN_SESSION_TTL_HOURS", str(ADMIN_SESSION_TTL_HOURS)))
    token = create_admin_session(int(row["id"]), ttl_hours)
    cookie = build_admin_session_cookie(token, max_age=ttl_hours * 3600)
    payload = {"ok": True, "admin": {"id": row["id"], "username": row["username"]}}
    return payload, None, 200, cookie
