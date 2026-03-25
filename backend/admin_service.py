"""
这个文件实现什么功能：聚合后台管理台需要的运营数据与管理动作。
它负责什么：统计用户与会话概览、输出后台页面所需列表数据、执行按用户下线全部设备。
它不负责什么：不处理后台登录态、不渲染 HTML、不直接调用上游模型接口。
对外暴露什么：build_admin_dashboard_payload、list_admin_users、list_active_user_sessions、logout_all_sessions_for_user。
依赖哪些关键模块：backend.agent_core、backend.auth、backend.db、os。
"""

import os
from datetime import timedelta

from backend.agent_core import AGENT_CORE_LAYERS, AGENT_CORE_VERSION
from backend.auth import remove_all_sessions_by_user
from backend.db import DB_CONN, DB_LOCK, cleanup_expired_sessions, isoformat, now_utc


#下面代码实现的功能：查询后台用户总览列表
def _fetch_user_rows():
    current_time = isoformat(now_utc())
    with DB_LOCK:
        rows = DB_CONN.execute(
            """
            SELECT
                users.id,
                users.username,
                users.created_at,
                COUNT(sessions.id) AS active_session_count,
                MAX(sessions.created_at) AS latest_session_created_at,
                MAX(sessions.expires_at) AS latest_session_expires_at
            FROM users
            LEFT JOIN sessions
                ON sessions.user_id = users.id
                AND sessions.expires_at > ?
            GROUP BY users.id
            ORDER BY users.created_at DESC, users.id DESC
            """,
            (current_time,),
        ).fetchall()

    return [
        {
            "id": int(row["id"]),
            "username": row["username"],
            "created_at": row["created_at"],
            "active_session_count": int(row["active_session_count"] or 0),
            "latest_session_created_at": row["latest_session_created_at"],
            "latest_session_expires_at": row["latest_session_expires_at"],
        }
        for row in rows
    ]


#下面代码实现的功能：查询当前活跃会话列表（不返回敏感 token）
def list_active_user_sessions(limit: int = 200):
    cleanup_expired_sessions()
    current_time = isoformat(now_utc())
    with DB_LOCK:
        rows = DB_CONN.execute(
            """
            SELECT
                sessions.id,
                users.id AS user_id,
                users.username,
                sessions.created_at,
                sessions.expires_at
            FROM sessions
            JOIN users ON users.id = sessions.user_id
            WHERE sessions.expires_at > ?
            ORDER BY sessions.expires_at ASC, sessions.created_at DESC
            LIMIT ?
            """,
            (current_time, limit),
        ).fetchall()

    return {
        "sessions": [
            {
                "id": int(row["id"]),
                "user_id": int(row["user_id"]),
                "username": row["username"],
                "created_at": row["created_at"],
                "expires_at": row["expires_at"],
            }
            for row in rows
        ]
    }


#下面代码实现的功能：返回后台用户列表
def list_admin_users():
    cleanup_expired_sessions()
    return {"users": _fetch_user_rows()}


#下面代码实现的功能：汇总后台概览面板所需数据
def build_admin_dashboard_payload():
    cleanup_expired_sessions()
    user_rows = _fetch_user_rows()
    current_dt = now_utc()
    current_iso = isoformat(current_dt)
    next_day_iso = isoformat(current_dt + timedelta(hours=24))
    session_payload = list_active_user_sessions(limit=8)["sessions"]

    with DB_LOCK:
        new_users_7d = int(
            DB_CONN.execute(
                "SELECT COUNT(*) FROM users WHERE created_at >= ?",
                (isoformat(current_dt - timedelta(days=7)),),
            ).fetchone()[0]
        )
        active_session_count = int(
            DB_CONN.execute(
                "SELECT COUNT(*) FROM sessions WHERE expires_at > ?",
                (current_iso,),
            ).fetchone()[0]
        )
        expiring_session_count = int(
            DB_CONN.execute(
                """
                SELECT COUNT(*)
                FROM sessions
                WHERE expires_at > ? AND expires_at <= ?
                """,
                (current_iso, next_day_iso),
            ).fetchone()[0]
        )

    return {
        "summary": {
            "total_users": len(user_rows),
            "active_sessions": active_session_count,
            "weekly_new_users": new_users_7d,
            "expiring_sessions_24h": expiring_session_count,
            "users_with_active_sessions": sum(
                1 for row in user_rows if row["active_session_count"] > 0
            ),
        },
        "system": {
            "server_time": current_iso,
            "api_configured": all(
                [
                    os.getenv("API_URL", "").strip(),
                    os.getenv("API_KEY", "").strip(),
                    os.getenv("MODEL_NAME", "").strip(),
                ]
            ),
            "cookie_secure": str(os.getenv("COOKIE_SECURE", "false")).strip().lower() == "true",
            "session_ttl_hours": int(os.getenv("SESSION_TTL_HOURS", "168")),
            "admin_username": os.getenv("ADMIN_USERNAME", "").strip(),
            "admin_session_ttl_hours": int(os.getenv("ADMIN_SESSION_TTL_HOURS", "12")),
        },
        "agent_core": {
            "version": AGENT_CORE_VERSION,
            "layers": AGENT_CORE_LAYERS,
        },
        "recent_users": user_rows[:5],
        "expiring_sessions": session_payload,
        "risk_monitoring": {
            "status": "pending",
            "title": "风险巡检待接入",
            "message": "当前后台已接入用户与会话维度，尚未接入对话级风险事件落库与告警流。",
        },
    }


#下面代码实现的功能：按用户下线全部设备，供后台危险操作使用
def logout_all_sessions_for_user(user_id: int):
    cleanup_expired_sessions()

    with DB_LOCK:
        user_row = DB_CONN.execute(
            "SELECT id, username FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()
        active_session_count = int(
            DB_CONN.execute(
                "SELECT COUNT(*) FROM sessions WHERE user_id = ?",
                (user_id,),
            ).fetchone()[0]
        )

    if not user_row:
        return None, "用户不存在", 404

    remove_all_sessions_by_user(int(user_row["id"]))
    return {
        "ok": True,
        "message": f"已下线 {user_row['username']} 的全部设备",
        "user": {
            "id": int(user_row["id"]),
            "username": user_row["username"],
            "cleared_sessions": active_session_count,
        },
    }, None, 200
