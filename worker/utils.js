import { CSRF_COOKIE_NAME } from "./constants.js";

// #下面代码实现的功能：返回 JSON 响应
export function jsonResponse(data, status = 200, cookies = []) {
  const headers = { "content-type": "application/json; charset=utf-8" };
  if (cookies.length > 0) headers["Set-Cookie"] = cookies;
  return new Response(JSON.stringify(data), { status, headers });
}

// #下面代码实现的功能：规范化上游接口地址
export function normalizeChatEndpoint(apiUrl) {
  const normalized = String(apiUrl || "").trim().replace(/\/+$/, "");
  if (!normalized) return "";
  if (normalized.endsWith("/chat/completions")) return normalized;
  return `${normalized}/chat/completions`;
}

// #下面代码实现的功能：清理聊天历史
export function sanitizeHistory(rawHistory, limit) {
  if (!Array.isArray(rawHistory)) return [];
  const cleaned = [];
  for (const item of rawHistory) {
    if (!item || typeof item !== "object") continue;
    if (!["user", "assistant"].includes(item.role)) continue;
    if (typeof item.content !== "string") continue;
    const text = item.content.trim();
    if (!text) continue;
    cleaned.push({ role: item.role, content: text });
  }
  return cleaned.slice(-limit);
}

// #下面代码实现的功能：解析 Cookie
export function parseCookies(request) {
  const raw = request.headers.get("Cookie") || "";
  const map = {};
  for (const part of raw.split(";")) {
    const [k, ...v] = part.trim().split("=");
    if (!k) continue;
    map[k] = decodeURIComponent(v.join("="));
  }
  return map;
}

// #下面代码实现的功能：生成随机 token
export function randomToken(bytes = 24) {
  const arr = new Uint8Array(bytes);
  crypto.getRandomValues(arr);
  return btoa(String.fromCharCode(...arr)).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

// #下面代码实现的功能：计算 SHA256 十六进制摘要
export async function sha256Hex(value) {
  const enc = new TextEncoder().encode(value);
  const digest = await crypto.subtle.digest("SHA-256", enc);
  return [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

// #下面代码实现的功能：构建 cookie 字符串
export function buildCookie(name, value, { maxAge = 0, httpOnly = true, secure = true } = {}) {
  const attrs = [`${name}=${encodeURIComponent(value)}`, "Path=/", `Max-Age=${maxAge}`, "SameSite=Lax"];
  if (httpOnly) attrs.push("HttpOnly");
  if (secure) attrs.push("Secure");
  return attrs.join("; ");
}

// #下面代码实现的功能：校验 CSRF token
export function requireCsrf(request, session) {
  const cookies = parseCookies(request);
  const cookieToken = cookies[CSRF_COOKIE_NAME];
  const headerToken = request.headers.get("X-CSRF-Token") || "";
  if (!cookieToken || !headerToken) return false;
  if (cookieToken !== headerToken) return false;
  if (session && session.csrfToken !== headerToken) return false;
  return true;
}
