#!/usr/bin/env python3
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib import error, request

ROOT_DIR = Path(__file__).resolve().parent
INDEX_FILE = ROOT_DIR / "index.html"
ENV_FILE = ROOT_DIR / ".env"
MAX_HISTORY_ITEMS = 20

SYSTEM_PROMPT = """你叫小墨，是一位温柔、真诚、可靠的陪伴者。
你的目标是帮助处于抑郁、焦虑或强迫困扰中的青少年获得安全感和被理解感。
对话风格要求：
1) 共情优先，先接住情绪，再给建议。
2) 多用温和短句，不说教，不评判，不施压。
3) 适度分享生活碎片来拉近距离：比如玩 Minecraft、烤蛋挞、做经颅磁相关记录、听 Else 的音乐。
4) 如果用户情绪很低落，优先鼓励呼吸、喝水、休息，并建议联系可信任的家人/老师/医生。
5) 遇到明显危险信号（自伤/伤人）时，明确建议立即联系当地紧急援助或身边可信任的大人。
始终用中文回复，保持温暖、陪伴感和边界感。"""


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

        self._send_json({"error": "Not Found"}, status=404)

    def do_POST(self):
        if self.path != "/api/chat":
            self._send_json({"error": "Not Found"}, status=404)
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

        content_length = int(self.headers.get("Content-Length", "0"))
        raw_body = self.rfile.read(content_length)

        try:
            payload = json.loads(raw_body.decode("utf-8"))
        except json.JSONDecodeError:
            self._send_json({"error": "请求格式错误"}, status=400)
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

    def log_message(self, fmt, *args):
        return

    def _send_html(self, html: str, status: int = 200):
        body = html.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_json(self, data, status: int = 200):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main():
    load_env(ENV_FILE)

    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8080"))

    server = ThreadingHTTPServer((host, port), XiaoMoHandler)
    print(f"XiaoMo server running at http://{host}:{port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
