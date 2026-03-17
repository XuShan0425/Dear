const HISTORY_LIMIT = 20;
const SESSION_COOKIE_NAME = "xiaomo_session";
const CSRF_COOKIE_NAME = "xiaomo_csrf";
const ADMIN_COOKIE_NAME = "xiaomo_admin";
const DEFAULT_SESSION_HOURS = 24 * 7;
const LOGIN_RATE_LIMIT_PER_MIN = 30;
const LOGIN_LOCK_FAIL_THRESHOLD = 10;
const LOGIN_LOCK_MINUTES = 10;
const ADMIN_USERNAME = "Tong";
const ADMIN_PASSWORD = "15010190";

const SYSTEM_PROMPT = `你叫小墨，是一位温柔、真诚、可靠的陪伴者。
你的目标是帮助处于抑郁、焦虑或强迫困扰中的青少年获得安全感和被理解感。
对话风格要求：
1) 共情优先，先接住情绪，再给建议。
2) 多用温和短句，不说教，不评判，不施压。
3) 适度分享生活碎片来拉近距离：比如玩 Minecraft、烤蛋挞、做经颅磁相关记录、听 Else 的音乐。
4) 如果用户情绪很低落，优先鼓励呼吸、喝水、休息，并建议联系可信任的家人/老师/医生。
5) 遇到明显危险信号（自伤/伤人）时，明确建议立即联系当地紧急援助或身边可信任的大人。
始终用中文回复，保持温暖、陪伴感和边界感。`;

function jsonResponse(data, status = 200, cookies = []) {
  const headers = { "content-type": "application/json; charset=utf-8" };
  if (cookies.length > 0) headers["Set-Cookie"] = cookies;
  return new Response(JSON.stringify(data), { status, headers });
}

function normalizeChatEndpoint(apiUrl) {
  const normalized = String(apiUrl || "").trim().replace(/\/+$/, "");
  if (!normalized) return "";
  if (normalized.endsWith("/chat/completions")) return normalized;
  return `${normalized}/chat/completions`;
}

function sanitizeHistory(rawHistory) {
  if (!Array.isArray(rawHistory)) return [];
  const cleaned = [];
  for (const item of rawHistory) {
    if (!item || typeof item !== "object") continue;
    const role = item.role;
    const content = item.content;
    if (role !== "user" && role !== "assistant") continue;
    if (typeof content !== "string") continue;
    const text = content.trim();
    if (!text) continue;
    cleaned.push({ role, content: text });
  }
  return cleaned.slice(-HISTORY_LIMIT);
}

function parseCookies(request) {
  const raw = request.headers.get("Cookie") || "";
  const map = {};
  for (const part of raw.split(";")) {
    const [k, ...v] = part.trim().split("=");
    if (!k) continue;
    map[k] = decodeURIComponent(v.join("="));
  }
  return map;
}

function randomToken(bytes = 24) {
  const arr = new Uint8Array(bytes);
  crypto.getRandomValues(arr);
  return btoa(String.fromCharCode(...arr)).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

async function sha256Hex(value) {
  const enc = new TextEncoder().encode(value);
  const digest = await crypto.subtle.digest("SHA-256", enc);
  return [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

async function pbkdf2Hash(password, saltHex, iterations = 150000) {
  const enc = new TextEncoder();
  const keyMaterial = await crypto.subtle.importKey("raw", enc.encode(password), "PBKDF2", false, ["deriveBits"]);
  const salt = Uint8Array.from(saltHex.match(/.{1,2}/g).map((h) => parseInt(h, 16)));
  const bits = await crypto.subtle.deriveBits({ name: "PBKDF2", hash: "SHA-256", salt, iterations }, keyMaterial, 256);
  const bytes = new Uint8Array(bits);
  return [...bytes].map((b) => b.toString(16).padStart(2, "0")).join("");
}

async function hashPassword(password) {
  const salt = crypto.getRandomValues(new Uint8Array(16));
  const saltHex = [...salt].map((b) => b.toString(16).padStart(2, "0")).join("");
  const digest = await pbkdf2Hash(password, saltHex);
  return `150000$${saltHex}$${digest}`;
}

async function verifyPassword(password, packed) {
  try {
    const [iterationsRaw, saltHex, expected] = String(packed || "").split("$");
    const digest = await pbkdf2Hash(password, saltHex, Number(iterationsRaw));
    return digest === expected;
  } catch {
    return false;
  }
}

function ipFromRequest(request) {
  return (
    request.headers.get("CF-Connecting-IP") ||
    request.headers.get("X-Forwarded-For")?.split(",")[0]?.trim() ||
    "0.0.0.0"
  );
}

function buildCookie(name, value, { maxAge = 0, httpOnly = true, secure = true } = {}) {
  const attrs = [
    `${name}=${encodeURIComponent(value)}`,
    "Path=/",
    `Max-Age=${maxAge}`,
    "SameSite=Lax",
  ];
  if (httpOnly) attrs.push("HttpOnly");
  if (secure) attrs.push("Secure");
  return attrs.join("; ");
}

function validateUsername(username) {
  const u = String(username || "").trim().toLowerCase();
  if (u.length < 3 || u.length > 32) return [null, "用户名长度需在 3-32 个字符之间"];
  if (!u.replaceAll("_", "").replaceAll("-", "").match(/^[a-z0-9]+$/)) {
    return [null, "用户名只能包含字母、数字、下划线或短横线"];
  }
  return [u, null];
}

function validatePassword(password) {
  const p = String(password || "");
  if (p.length < 8) return "密码至少 8 位";
  if (p.length > 128) return "密码过长";
  return null;
}

async function ensureSchema(env) {
  await env.DB.exec(`
CREATE TABLE IF NOT EXISTS users (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  username TEXT NOT NULL UNIQUE,
  password_hash TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sessions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  token_hash TEXT NOT NULL UNIQUE,
  user_id INTEGER NOT NULL,
  csrf_token TEXT NOT NULL,
  expires_at INTEGER NOT NULL,
  created_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_sessions_user_id ON sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_sessions_expires ON sessions(expires_at);
CREATE TABLE IF NOT EXISTS login_limits (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ip TEXT NOT NULL,
  username TEXT NOT NULL,
  minute_start INTEGER NOT NULL,
  minute_count INTEGER NOT NULL DEFAULT 0,
  consecutive_failures INTEGER NOT NULL DEFAULT 0,
  locked_until INTEGER NOT NULL DEFAULT 0,
  updated_at INTEGER NOT NULL,
  UNIQUE(ip, username)
);
CREATE TABLE IF NOT EXISTS login_failure_logs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  created_at INTEGER NOT NULL,
  ip TEXT NOT NULL,
  username TEXT NOT NULL,
  reason TEXT NOT NULL
);
`);
}

async function lightweightCleanup(env) {
  const now = Date.now();
  await env.DB.prepare("DELETE FROM sessions WHERE expires_at <= ?").bind(now).run();
  await env.DB.prepare("DELETE FROM login_limits WHERE updated_at <= ?").bind(now - 7 * 24 * 3600 * 1000).run();
}

async function getSession(request, env) {
  const cookies = parseCookies(request);
  const rawToken = cookies[SESSION_COOKIE_NAME];
  if (!rawToken) return null;
  const tokenHash = await sha256Hex(rawToken);
  const row = await env.DB.prepare(`
    SELECT sessions.id, sessions.user_id, sessions.csrf_token, sessions.expires_at, users.username
    FROM sessions JOIN users ON users.id = sessions.user_id
    WHERE sessions.token_hash = ?
  `).bind(tokenHash).first();
  if (!row) return null;
  if (Number(row.expires_at) <= Date.now()) {
    await env.DB.prepare("DELETE FROM sessions WHERE id = ?").bind(row.id).run();
    return null;
  }
  return {
    token: rawToken,
    sessionId: row.id,
    userId: row.user_id,
    username: row.username,
    csrfToken: row.csrf_token,
  };
}

function requireCsrf(request, session) {
  const cookies = parseCookies(request);
  const cookieToken = cookies[CSRF_COOKIE_NAME];
  const headerToken = request.headers.get("X-CSRF-Token") || "";
  if (!cookieToken || !headerToken) return false;
  if (cookieToken !== headerToken) return false;
  if (session && session.csrfToken !== headerToken) return false;
  return true;
}

async function getLoginLimit(env, ip, username) {
  const row = await env.DB.prepare("SELECT * FROM login_limits WHERE ip = ? AND username = ?").bind(ip, username).first();
  return row;
}

async function upsertLoginLimit(env, ip, username, data) {
  await env.DB.prepare(`
    INSERT INTO login_limits (ip, username, minute_start, minute_count, consecutive_failures, locked_until, updated_at)
    VALUES (?, ?, ?, ?, ?, ?, ?)
    ON CONFLICT(ip, username) DO UPDATE SET
      minute_start = excluded.minute_start,
      minute_count = excluded.minute_count,
      consecutive_failures = excluded.consecutive_failures,
      locked_until = excluded.locked_until,
      updated_at = excluded.updated_at
  `)
    .bind(ip, username, data.minuteStart, data.minuteCount, data.consecutiveFailures, data.lockedUntil, data.updatedAt)
    .run();
}

async function logFailure(env, ip, username, reason) {
  await env.DB.prepare(
    "INSERT INTO login_failure_logs (created_at, ip, username, reason) VALUES (?, ?, ?, ?)"
  ).bind(Date.now(), ip, username || "", reason).run();
}

async function enforceRateLimit(env, ip, username) {
  const now = Date.now();
  const minuteStart = Math.floor(now / 60000) * 60000;
  let row = await getLoginLimit(env, ip, username);
  if (!row) {
    await upsertLoginLimit(env, ip, username, {
      minuteStart,
      minuteCount: 0,
      consecutiveFailures: 0,
      lockedUntil: 0,
      updatedAt: now,
    });
    row = await getLoginLimit(env, ip, username);
  }

  const current = {
    minuteStart: Number(row.minute_start),
    minuteCount: Number(row.minute_count),
    consecutiveFailures: Number(row.consecutive_failures),
    lockedUntil: Number(row.locked_until),
  };

  if (current.lockedUntil > now) {
    return { blocked: true, status: 423, remainingSeconds: Math.ceil((current.lockedUntil - now) / 1000) };
  }

  if (current.minuteStart !== minuteStart) {
    current.minuteStart = minuteStart;
    current.minuteCount = 0;
  }

  if (current.minuteCount >= LOGIN_RATE_LIMIT_PER_MIN) {
    return { blocked: true, status: 429, remainingSeconds: 60 };
  }

  return { blocked: false, current };
}

async function markLoginFailure(env, ip, username, current, reason) {
  const now = Date.now();
  current.minuteCount += 1;
  current.consecutiveFailures += 1;
  if (current.consecutiveFailures >= LOGIN_LOCK_FAIL_THRESHOLD) {
    current.lockedUntil = now + LOGIN_LOCK_MINUTES * 60 * 1000;
  }
  await upsertLoginLimit(env, ip, username, {
    minuteStart: current.minuteStart,
    minuteCount: current.minuteCount,
    consecutiveFailures: current.consecutiveFailures,
    lockedUntil: current.lockedUntil,
    updatedAt: now,
  });
  await logFailure(env, ip, username, reason);
  return current.lockedUntil > now ? Math.ceil((current.lockedUntil - now) / 1000) : 0;
}

async function markLoginSuccess(env, ip, username, current) {
  const now = Date.now();
  current.minuteCount += 1;
  current.consecutiveFailures = 0;
  current.lockedUntil = 0;
  await upsertLoginLimit(env, ip, username, {
    minuteStart: current.minuteStart,
    minuteCount: current.minuteCount,
    consecutiveFailures: current.consecutiveFailures,
    lockedUntil: current.lockedUntil,
    updatedAt: now,
  });
}

async function handleCsrf(request) {
  const token = randomToken(18);
  return jsonResponse({ csrfToken: token }, 200, [buildCookie(CSRF_COOKIE_NAME, token, { maxAge: 3600, httpOnly: false })]);
}

async function handleRegister(request, env) {
  if (!requireCsrf(request)) {
    return jsonResponse({ error: "CSRF 校验失败" }, 403);
  }

  let payload;
  try {
    payload = await request.json();
  } catch {
    return jsonResponse({ error: "请求格式错误" }, 400);
  }

  const [username, usernameErr] = validateUsername(payload?.username);
  if (usernameErr) return jsonResponse({ error: usernameErr }, 400);
  const passwordErr = validatePassword(payload?.password);
  if (passwordErr) return jsonResponse({ error: passwordErr }, 400);

  const passwordHash = await hashPassword(payload.password);
  const createdAt = new Date().toISOString();
  try {
    await env.DB.prepare("INSERT INTO users (username, password_hash, created_at) VALUES (?, ?, ?)")
      .bind(username, passwordHash, createdAt)
      .run();
  } catch {
    return jsonResponse({ error: "用户名已存在" }, 409);
  }

  return jsonResponse({ ok: true, message: "注册成功，请登录", username });
}

async function handleLogin(request, env) {
  if (!requireCsrf(request)) {
    return jsonResponse({ error: "CSRF 校验失败" }, 403);
  }

  let payload;
  try {
    payload = await request.json();
  } catch {
    return jsonResponse({ error: "请求格式错误" }, 400);
  }

  const [username, usernameErr] = validateUsername(payload?.username);
  if (usernameErr) return jsonResponse({ error: usernameErr }, 400);
  const password = String(payload?.password || "");
  const ip = ipFromRequest(request);

  const limiter = await enforceRateLimit(env, ip, username);
  if (limiter.blocked) {
    await logFailure(env, ip, username, limiter.status === 423 ? "locked" : "rate_limited");
    return jsonResponse(
      {
        error: limiter.status === 423 ? "登录失败次数过多，已临时锁定" : "登录过于频繁，请稍后再试",
        lockRemainingSeconds: limiter.remainingSeconds,
      },
      limiter.status
    );
  }

  const row = await env.DB.prepare("SELECT id, username, password_hash FROM users WHERE username = ?").bind(username).first();
  if (!row || !(await verifyPassword(password, row.password_hash))) {
    const remain = await markLoginFailure(env, ip, username, limiter.current, "invalid_credentials");
    if (remain > 0) {
      return jsonResponse({ error: "登录失败次数过多，已临时锁定", lockRemainingSeconds: remain }, 423);
    }
    return jsonResponse({ error: "用户名或密码错误" }, 401);
  }

  await markLoginSuccess(env, ip, username, limiter.current);

  const token = randomToken(32);
  const csrfToken = randomToken(18);
  const tokenHash = await sha256Hex(token);
  const hours = Number(env.SESSION_TTL_HOURS || DEFAULT_SESSION_HOURS);
  const expiresAt = Date.now() + hours * 3600 * 1000;

  await env.DB.prepare(
    "INSERT INTO sessions (token_hash, user_id, csrf_token, expires_at, created_at) VALUES (?, ?, ?, ?, ?)"
  )
    .bind(tokenHash, row.id, csrfToken, expiresAt, Date.now())
    .run();

  return jsonResponse(
    { ok: true, user: { id: row.id, username: row.username }, csrfToken },
    200,
    [
      buildCookie(SESSION_COOKIE_NAME, token, { maxAge: hours * 3600, httpOnly: true }),
      buildCookie(CSRF_COOKIE_NAME, csrfToken, { maxAge: hours * 3600, httpOnly: false }),
    ]
  );
}

async function handleLogout(request, env) {
  const session = await getSession(request, env);
  if (session) {
    await env.DB.prepare("DELETE FROM sessions WHERE id = ?").bind(session.sessionId).run();
  }
  return jsonResponse({ ok: true }, 200, [
    buildCookie(SESSION_COOKIE_NAME, "", { maxAge: 0, httpOnly: true }),
    buildCookie(CSRF_COOKIE_NAME, "", { maxAge: 0, httpOnly: false }),
  ]);
}

async function handleLogoutAll(request, env) {
  const session = await getSession(request, env);
  if (!session) return jsonResponse({ error: "请先登录" }, 401);
  if (!requireCsrf(request, session)) return jsonResponse({ error: "CSRF 校验失败" }, 403);
  await env.DB.prepare("DELETE FROM sessions WHERE user_id = ?").bind(session.userId).run();
  return jsonResponse({ ok: true }, 200, [
    buildCookie(SESSION_COOKIE_NAME, "", { maxAge: 0, httpOnly: true }),
    buildCookie(CSRF_COOKIE_NAME, "", { maxAge: 0, httpOnly: false }),
  ]);
}

async function handleMe(request, env) {
  const session = await getSession(request, env);
  if (!session) return jsonResponse({ authenticated: false });
  return jsonResponse({ authenticated: true, user: { id: session.userId, username: session.username }, csrfToken: session.csrfToken });
}

async function handleAdminLogin(request) {
  let payload;
  try {
    payload = await request.json();
  } catch {
    return jsonResponse({ error: "请求格式错误" }, 400);
  }
  if (String(payload?.username || "") !== ADMIN_USERNAME || String(payload?.password || "") !== ADMIN_PASSWORD) {
    return jsonResponse({ error: "后台账号或密码错误" }, 401);
  }
  const adminToken = randomToken(24);
  return jsonResponse({ ok: true }, 200, [buildCookie(ADMIN_COOKIE_NAME, adminToken, { maxAge: 3600, httpOnly: true })]);
}

function isAdmin(request) {
  const cookies = parseCookies(request);
  return Boolean(cookies[ADMIN_COOKIE_NAME]);
}

async function handleAdminFailureLogs(request, env) {
  if (!isAdmin(request)) return jsonResponse({ error: "未授权" }, 401);
  const rows = await env.DB.prepare(
    "SELECT id, created_at, ip, username, reason FROM login_failure_logs ORDER BY id DESC LIMIT 200"
  ).all();
  return jsonResponse({ items: rows.results || [] });
}

async function handleChatRequest(request, env) {
  const session = await getSession(request, env);
  if (!session) return jsonResponse({ error: "请先登录" }, 401);
  if (!requireCsrf(request, session)) return jsonResponse({ error: "CSRF 校验失败" }, 403);

  const apiUrl = normalizeChatEndpoint(env.API_URL);
  const apiKey = String(env.API_KEY || "").trim();
  const modelName = String(env.MODEL_NAME || "").trim();
  if (!apiUrl || !apiKey || !modelName) return jsonResponse({ error: "服务器未配置完成，请设置 API_URL、API_KEY、MODEL_NAME" }, 500);

  let payload;
  try {
    payload = await request.json();
  } catch {
    return jsonResponse({ error: "请求格式错误" }, 400);
  }
  const userMessage = String(payload?.message || "").trim();
  if (!userMessage) return jsonResponse({ error: "消息不能为空" }, 400);

  const history = sanitizeHistory(payload?.history);
  const messages = [{ role: "system", content: SYSTEM_PROMPT }, ...history, { role: "user", content: userMessage }];

  let upstreamResponse;
  try {
    upstreamResponse = await fetch(apiUrl, {
      method: "POST",
      headers: { "content-type": "application/json", authorization: `Bearer ${apiKey}` },
      body: JSON.stringify({ model: modelName, messages, temperature: 0.72, stream: false }),
    });
  } catch (error) {
    return jsonResponse({ error: "连接上游 API 失败", detail: String(error) }, 502);
  }

  const rawText = await upstreamResponse.text();
  let upstreamData = {};
  try { upstreamData = JSON.parse(rawText); } catch { upstreamData = {}; }

  if (!upstreamResponse.ok) return jsonResponse({ error: "上游 API 返回错误", detail: rawText.slice(0, 800) }, 502);
  const reply = upstreamData?.choices?.[0]?.message?.content?.trim() || "我在这儿，刚刚有点卡住了。你愿意再说一次吗？";
  return jsonResponse({ reply });
}

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
    if (url.pathname === "/api/auth/csrf" && method === "GET") return handleCsrf(request);
    if (url.pathname === "/api/auth/me" && method === "GET") return handleMe(request, env);
    if (url.pathname === "/api/auth/login" && method === "POST") return handleLogin(request, env);
    if (url.pathname === "/api/auth/register" && method === "POST") return handleRegister(request, env);
    if (url.pathname === "/api/auth/logout" && method === "POST") return handleLogout(request, env);
    if (url.pathname === "/api/auth/logout_all" && method === "POST") return handleLogoutAll(request, env);
    if (url.pathname === "/api/admin/login" && method === "POST") return handleAdminLogin(request);
    if (url.pathname === "/api/admin/login-failures" && method === "GET") return handleAdminFailureLogs(request, env);
    if (url.pathname === "/api/chat" && method === "POST") return handleChatRequest(request, env);

    return env.ASSETS.fetch(request);
  },
};
