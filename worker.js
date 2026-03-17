const HISTORY_LIMIT = 20;

const SYSTEM_PROMPT = `你叫小墨，是一位温柔、真诚、可靠的陪伴者。
你的目标是帮助处于抑郁、焦虑或强迫困扰中的青少年获得安全感和被理解感。
对话风格要求：
1) 共情优先，先接住情绪，再给建议。
2) 多用温和短句，不说教，不评判，不施压。
3) 适度分享生活碎片来拉近距离：比如玩 Minecraft、烤蛋挞、做经颅磁相关记录、听 Else 的音乐。
4) 如果用户情绪很低落，优先鼓励呼吸、喝水、休息，并建议联系可信任的家人/老师/医生。
5) 遇到明显危险信号（自伤/伤人）时，明确建议立即联系当地紧急援助或身边可信任的大人。
始终用中文回复，保持温暖、陪伴感和边界感。`;

function jsonResponse(data, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: {
      "content-type": "application/json; charset=utf-8",
    },
  });
}

function normalizeChatEndpoint(apiUrl) {
  const normalized = String(apiUrl || "").trim().replace(/\/+$/, "");
  if (!normalized) {
    return "";
  }
  if (normalized.endsWith("/chat/completions")) {
    return normalized;
  }
  return `${normalized}/chat/completions`;
}

function sanitizeHistory(rawHistory) {
  if (!Array.isArray(rawHistory)) {
    return [];
  }

  const cleaned = [];
  for (const item of rawHistory) {
    if (!item || typeof item !== "object") {
      continue;
    }
    const role = item.role;
    const content = item.content;
    if (role !== "user" && role !== "assistant") {
      continue;
    }
    if (typeof content !== "string") {
      continue;
    }
    const text = content.trim();
    if (!text) {
      continue;
    }
    cleaned.push({ role, content: text });
  }

  return cleaned.slice(-HISTORY_LIMIT);
}

async function handleChatRequest(request, env) {
  const apiUrl = normalizeChatEndpoint(env.API_URL);
  const apiKey = String(env.API_KEY || "").trim();
  const modelName = String(env.MODEL_NAME || "").trim();

  if (!apiUrl || !apiKey || !modelName) {
    return jsonResponse(
      {
        error: "服务器未配置完成，请设置 API_URL、API_KEY、MODEL_NAME",
      },
      500
    );
  }

  let payload;
  try {
    payload = await request.json();
  } catch {
    return jsonResponse({ error: "请求格式错误" }, 400);
  }

  const userMessage = String(payload?.message || "").trim();
  if (!userMessage) {
    return jsonResponse({ error: "消息不能为空" }, 400);
  }

  const history = sanitizeHistory(payload?.history);
  const messages = [
    { role: "system", content: SYSTEM_PROMPT },
    ...history,
    { role: "user", content: userMessage },
  ];

  let upstreamResponse;
  try {
    upstreamResponse = await fetch(apiUrl, {
      method: "POST",
      headers: {
        "content-type": "application/json",
        authorization: `Bearer ${apiKey}`,
      },
      body: JSON.stringify({
        model: modelName,
        messages,
        temperature: 0.72,
        stream: false,
      }),
    });
  } catch (error) {
    return jsonResponse(
      {
        error: "连接上游 API 失败",
        detail: String(error),
      },
      502
    );
  }

  const rawText = await upstreamResponse.text();
  let upstreamData = {};
  try {
    upstreamData = JSON.parse(rawText);
  } catch {
    upstreamData = {};
  }

  if (!upstreamResponse.ok) {
    return jsonResponse(
      {
        error: "上游 API 返回错误",
        detail: rawText.slice(0, 800),
      },
      502
    );
  }

  const reply =
    upstreamData?.choices?.[0]?.message?.content?.trim() ||
    "我在这儿，刚刚有点卡住了。你愿意再说一次吗？";

  return jsonResponse({ reply });
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    if (url.pathname === "/healthz") {
      return jsonResponse({ ok: true });
    }

    if (url.pathname === "/api/chat" && request.method === "POST") {
      return handleChatRequest(request, env);
    }

    return env.ASSETS.fetch(request);
  },
};
