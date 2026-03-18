import { handleAdminFailureLogs, handleAdminLogin } from "./worker/admin.js";
import { handleCsrf, handleLogin, handleLogout, handleLogoutAll, handleMe, handleRegister } from "./worker/auth.js";
import { handleChatRequest } from "./worker/chat.js";
import { ensureSchema, lightweightCleanup } from "./worker/db.js";
import { jsonResponse } from "./worker/utils.js";

// #下面代码实现的功能：统一包装业务返回结果为 HTTP 响应
function toResponse(result) {
  if (result.error) {
    return jsonResponse({ error: result.error, ...(result.payload || {}) }, result.status || 500, result.cookies || []);
  }
  return jsonResponse(result.payload || {}, result.status || 200, result.cookies || []);
}

// #下面代码实现的功能：Worker 路由入口
export default {
  async fetch(request, env) {
    if (!env.DB) return jsonResponse({ error: "未配置 D1 绑定（DB）" }, 500);

    await ensureSchema(env);
    const url = new URL(request.url);
    const method = request.method.toUpperCase();

    if (["/api/auth/me", "/api/auth/login", "/api/auth/register", "/api/chat"].includes(url.pathname)) {
      await lightweightCleanup(env);
    }

    if (url.pathname === "/healthz") return jsonResponse({ ok: true });
    if (url.pathname === "/api/auth/csrf" && method === "GET") return toResponse(handleCsrf());
    if (url.pathname === "/api/auth/me" && method === "GET") return toResponse(await handleMe(request, env));
    if (url.pathname === "/api/auth/login" && method === "POST") return toResponse(await handleLogin(request, env));
    if (url.pathname === "/api/auth/register" && method === "POST") return toResponse(await handleRegister(request, env));
    if (url.pathname === "/api/auth/logout" && method === "POST") return toResponse(await handleLogout(request, env));
    if (url.pathname === "/api/auth/logout_all" && method === "POST") return toResponse(await handleLogoutAll(request, env));
    if (url.pathname === "/api/admin/login" && method === "POST") return toResponse(await handleAdminLogin(request));
    if (url.pathname === "/api/admin/login-failures" && method === "GET") return toResponse(await handleAdminFailureLogs(request, env));
    if (url.pathname === "/api/chat" && method === "POST") return toResponse(await handleChatRequest(request, env));

    return env.ASSETS.fetch(request);
  },
};
