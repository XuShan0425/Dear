"""
这个文件实现什么功能：封装 Dear 的聊天回复服务编排。
它负责什么：清理前端 history、在独立 Web API 转发模式与直连模型模式之间做切换，并返回统一的前端响应结构。
它不负责什么：不处理 HTTP 路由、不校验登录态、不管理数据库用户会话。
对外暴露什么：sanitize_history、fetch_chat_reply。
依赖哪些关键模块：backend.agent_core、backend.external_chat_api、urllib.request。
"""

import json
from urllib import error, request

from backend.agent_core import AGENT_CORE_VERSION, build_agent_messages
from backend.constants import MAX_HISTORY_ITEMS
from backend.external_chat_api import fetch_external_chat_reply


#下面代码实现的功能：规范化上游 chat/completions 接口地址

def chat_endpoint(api_url: str) -> str:
    normalized = api_url.strip().rstrip("/")
    if normalized.endswith("/chat/completions"):
        return normalized
    return f"{normalized}/chat/completions"


#下面代码实现的功能：清理历史对话数据

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


#下面代码实现的功能：调用 Dear 配置的聊天回复能力，优先走独立 Web API，未配置时再回退到直连模型模式
def fetch_chat_reply(
    api_url: str,
    api_key: str,
    model_name: str,
    user_message: str,
    history,
    *,
    user_id: str = "",
    username: str = "",
    conversation_id: str = "",
    web_api_base_url: str = "",
    web_api_role: str = "",
    request_id: str = "",
):
    if str(web_api_base_url).strip():
        return fetch_external_chat_reply(
            api_base_url=web_api_base_url,
            user_id=user_id,
            username=username,
            user_message=user_message,
            conversation_id=conversation_id,
            request_id=request_id,
            role=web_api_role,
        )

    #下面代码实现的功能：通过主 agent 核心层统一构建 messages，避免人格逻辑散落在接口主流程中
    full_messages = build_agent_messages(user_message=user_message, history=history)
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
        return None, {"error": "上游 API 返回错误", "detail": detail[:800]}, 502
    except Exception as exc:
        return None, {"error": "连接上游 API 失败", "detail": str(exc)}, 502

    reply = ""
    choices = upstream_data.get("choices")
    if isinstance(choices, list) and choices:
        message = choices[0].get("message", {})
        reply = str(message.get("content", "")).strip()

    if not reply:
        reply = "我在这儿，刚刚有点卡住了。你愿意再说一次吗？"

    return {"reply": reply, "agentCoreVersion": AGENT_CORE_VERSION}, None, 200
