"""
这个文件实现什么功能：封装 Dear 对独立 Web Chat API 的调用。
它负责什么：把 Dear 当前登录用户的聊天请求转发到外部 `/api/v1/chat/respond` 接口，并把返回结果转换成 Dear 前端可消费的格式。
它不负责什么：不处理 HTTP 路由、不校验 Dear 登录态、不管理前端本地 history、不定义主 agent 人格文本。
对外暴露什么：build_dear_conversation_id、fetch_external_chat_reply。
依赖哪些关键模块：json、urllib.request。
"""

import json
from urllib import error, request


EXTERNAL_AGENT_CORE_VERSION = "external-web-api"


#下面代码实现的功能：为 Dear 网页端构造稳定会话 ID，让外部 Web API 能持续维护短期上下文
def build_dear_conversation_id(user_id: str) -> str:
    normalized = str(user_id).strip() or "anonymous"
    return f"dear-web-user-{normalized}"


#下面代码实现的功能：规范化独立 Web API 的 respond 接口地址
def web_api_respond_endpoint(api_base_url: str) -> str:
    normalized = api_base_url.strip().rstrip("/")
    return f"{normalized}/api/v1/chat/respond"


#下面代码实现的功能：从外部接口错误体里尽量提取人类可读的报错文案
def extract_external_error_message(raw_detail: str) -> str:
    detail_text = str(raw_detail or "").strip()
    if not detail_text:
        return "AI 回复服务返回错误"

    try:
        payload = json.loads(detail_text)
    except json.JSONDecodeError:
        return detail_text[:200]

    if not isinstance(payload, dict):
        return detail_text[:200]

    for key in ("detail", "error", "message"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()

    return detail_text[:200]


#下面代码实现的功能：调用外部 Web API 并转换成 Dear 现有前端兼容的响应结构
def fetch_external_chat_reply(
    api_base_url: str,
    user_id: str,
    username: str,
    user_message: str,
    conversation_id: str = "",
    request_id: str = "",
    role: str = "",
):
    normalized_conversation_id = str(conversation_id).strip() or build_dear_conversation_id(user_id)
    payload = {
        "user_id": str(user_id),
        "conversation_id": normalized_conversation_id,
        "text": str(user_message),
        "metadata": {
            "source": "dear-web",
            "dear_username": str(username),
        },
    }
    if str(role).strip():
        payload["role"] = str(role).strip()

    headers = {"Content-Type": "application/json"}
    if str(request_id).strip():
        headers["X-Request-ID"] = str(request_id).strip()

    req = request.Request(
        web_api_respond_endpoint(api_base_url),
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers=headers,
    )

    try:
        with request.urlopen(req, timeout=90) as response:
            raw_response = response.read().decode("utf-8")
            response_payload = json.loads(raw_response)
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        error_message = extract_external_error_message(detail)
        status = exc.code if 400 <= exc.code < 500 else 502
        return None, {"error": error_message, "detail": detail[:800]}, status
    except Exception as exc:
        return None, {"error": "连接 AI 回复服务失败", "detail": str(exc)}, 502

    if not isinstance(response_payload, dict):
        return None, {"error": "AI 回复服务响应格式错误"}, 502

    data = response_payload.get("data")
    if not isinstance(data, dict):
        return None, {"error": "AI 回复服务响应缺少 data 字段"}, 502

    reply_text = str(data.get("reply_text", "")).strip()
    if not reply_text:
        reply_text = "我在这儿，刚刚有点卡住了。你愿意再说一次吗？"

    return {
        "reply": reply_text,
        "agentCoreVersion": EXTERNAL_AGENT_CORE_VERSION,
        "conversationId": str(data.get("conversation_id", "")).strip(),
        "historySize": data.get("history_size"),
        "role": str(data.get("role", "")).strip(),
        "requestId": str(response_payload.get("request_id", "")).strip(),
    }, None, 200
