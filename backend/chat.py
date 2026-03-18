import json
from urllib import error, request

from backend.agent_core import AGENT_CORE_VERSION, build_agent_messages
from backend.constants import MAX_HISTORY_ITEMS


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


#下面代码实现的功能：调用上游模型接口

def fetch_chat_reply(api_url: str, api_key: str, model_name: str, user_message: str, history):
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
