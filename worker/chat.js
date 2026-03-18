import { HISTORY_LIMIT } from "./constants.js";
import { AGENT_CORE_VERSION, buildAgentMessages } from "./agent_core.js";
import { normalizeChatEndpoint, requireCsrf, sanitizeHistory } from "./utils.js";
import { getSession } from "./auth.js";

// #下面代码实现的功能：处理聊天接口请求
export async function handleChatRequest(request, env) {
  const session = await getSession(request, env);
  if (!session) return { error: "请先登录", status: 401 };
  if (!requireCsrf(request, session)) return { error: "CSRF 校验失败", status: 403 };

  const apiUrl = normalizeChatEndpoint(env.API_URL);
  const apiKey = String(env.API_KEY || "").trim();
  const modelName = String(env.MODEL_NAME || "").trim();
  if (!apiUrl || !apiKey || !modelName) {
    return { error: "服务器未配置完成，请设置 API_URL、API_KEY、MODEL_NAME", status: 500 };
  }

  let payload;
  try {
    payload = await request.json();
  } catch {
    return { error: "请求格式错误", status: 400 };
  }

  const userMessage = String(payload?.message || "").trim();
  if (!userMessage) return { error: "消息不能为空", status: 400 };

  const history = sanitizeHistory(payload?.history, HISTORY_LIMIT);

  // #下面代码实现的功能：通过主 agent 核心层统一构建 messages，避免人格逻辑散落在接口主流程中
  const messages = buildAgentMessages({ history, userMessage });

  let upstreamResponse;
  try {
    upstreamResponse = await fetch(apiUrl, {
      method: "POST",
      headers: { "content-type": "application/json", authorization: `Bearer ${apiKey}` },
      body: JSON.stringify({ model: modelName, messages, temperature: 0.72, stream: false }),
    });
  } catch (error) {
    return { error: "连接上游 API 失败", payload: { detail: String(error) }, status: 502 };
  }

  const rawText = await upstreamResponse.text();
  let upstreamData = {};
  try {
    upstreamData = JSON.parse(rawText);
  } catch {
    upstreamData = {};
  }

  if (!upstreamResponse.ok) {
    return { error: "上游 API 返回错误", payload: { detail: rawText.slice(0, 800) }, status: 502 };
  }

  const reply =
    upstreamData?.choices?.[0]?.message?.content?.trim() || "我在这儿，刚刚有点卡住了。你愿意再说一次吗？";
  return { payload: { reply, agentCoreVersion: AGENT_CORE_VERSION }, status: 200 };
}
