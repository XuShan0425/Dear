import { ADMIN_COOKIE_NAME, ADMIN_PASSWORD, ADMIN_USERNAME } from "./constants.js";
import { buildCookie, parseCookies, randomToken } from "./utils.js";

// #下面代码实现的功能：管理员登录
export async function handleAdminLogin(request) {
  let payload;
  try {
    payload = await request.json();
  } catch {
    return { error: "请求格式错误", status: 400 };
  }

  if (String(payload?.username || "") !== ADMIN_USERNAME || String(payload?.password || "") !== ADMIN_PASSWORD) {
    return { error: "后台账号或密码错误", status: 401 };
  }

  return {
    payload: { ok: true },
    status: 200,
    cookies: [buildCookie(ADMIN_COOKIE_NAME, randomToken(24), { maxAge: 3600, httpOnly: true })],
  };
}

// #下面代码实现的功能：判断是否管理员
function isAdmin(request) {
  const cookies = parseCookies(request);
  return Boolean(cookies[ADMIN_COOKIE_NAME]);
}

// #下面代码实现的功能：查询登录失败日志
export async function handleAdminFailureLogs(request, env) {
  if (!isAdmin(request)) return { error: "未授权", status: 401 };
  const rows = await env.DB.prepare(
    "SELECT id, created_at, ip, username, reason FROM login_failure_logs ORDER BY id DESC LIMIT 200"
  ).all();
  return { payload: { items: rows.results || [] }, status: 200 };
}
