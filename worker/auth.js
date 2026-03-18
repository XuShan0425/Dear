import {
  CSRF_COOKIE_NAME,
  DEFAULT_SESSION_HOURS,
  LOGIN_LOCK_FAIL_THRESHOLD,
  LOGIN_LOCK_MINUTES,
  LOGIN_RATE_LIMIT_PER_MIN,
  SESSION_COOKIE_NAME,
} from "./constants.js";
import { buildCookie, parseCookies, randomToken, requireCsrf, sha256Hex } from "./utils.js";

// #下面代码实现的功能：从请求中提取客户端 IP
function ipFromRequest(request) {
  return (
    request.headers.get("CF-Connecting-IP") ||
    request.headers.get("X-Forwarded-For")?.split(",")[0]?.trim() ||
    "0.0.0.0"
  );
}

// #下面代码实现的功能：用户名格式校验
function validateUsername(username) {
  const u = String(username || "").trim().toLowerCase();
  if (u.length < 3 || u.length > 32) return [null, "用户名长度需在 3-32 个字符之间"];
  if (!u.replaceAll("_", "").replaceAll("-", "").match(/^[a-z0-9]+$/)) {
    return [null, "用户名只能包含字母、数字、下划线或短横线"];
  }
  return [u, null];
}

// #下面代码实现的功能：密码格式校验
function validatePassword(password) {
  const p = String(password || "");
  if (p.length < 8) return "密码至少 8 位";
  if (p.length > 128) return "密码过长";
  return null;
}

// #下面代码实现的功能：PBKDF2 哈希计算
async function pbkdf2Hash(password, saltHex, iterations = 150000) {
  const enc = new TextEncoder();
  const keyMaterial = await crypto.subtle.importKey("raw", enc.encode(password), "PBKDF2", false, ["deriveBits"]);
  const salt = Uint8Array.from(saltHex.match(/.{1,2}/g).map((h) => parseInt(h, 16)));
  const bits = await crypto.subtle.deriveBits({ name: "PBKDF2", hash: "SHA-256", salt, iterations }, keyMaterial, 256);
  const bytes = new Uint8Array(bits);
  return [...bytes].map((b) => b.toString(16).padStart(2, "0")).join("");
}

// #下面代码实现的功能：生成密码哈希
async function hashPassword(password) {
  const salt = crypto.getRandomValues(new Uint8Array(16));
  const saltHex = [...salt].map((b) => b.toString(16).padStart(2, "0")).join("");
  const digest = await pbkdf2Hash(password, saltHex);
  return `150000$${saltHex}$${digest}`;
}

// #下面代码实现的功能：验证密码是否正确
async function verifyPassword(password, packed) {
  try {
    const [iterationsRaw, saltHex, expected] = String(packed || "").split("$");
    const digest = await pbkdf2Hash(password, saltHex, Number(iterationsRaw));
    return digest === expected;
  } catch {
    return false;
  }
}

// #下面代码实现的功能：查询会话信息
export async function getSession(request, env) {
  const rawToken = parseCookies(request)[SESSION_COOKIE_NAME];
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
  return { sessionId: row.id, userId: row.user_id, username: row.username, csrfToken: row.csrf_token };
}

// #下面代码实现的功能：写入登录失败日志
async function logFailure(env, ip, username, reason) {
  await env.DB.prepare("INSERT INTO login_failure_logs (created_at, ip, username, reason) VALUES (?, ?, ?, ?)")
    .bind(Date.now(), ip, username || "", reason)
    .run();
}

// #下面代码实现的功能：读取限流记录
async function getLoginLimit(env, ip, username) {
  return env.DB.prepare("SELECT * FROM login_limits WHERE ip = ? AND username = ?").bind(ip, username).first();
}

// #下面代码实现的功能：更新限流记录
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

// #下面代码实现的功能：执行分钟级限流与锁定判断
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

// #下面代码实现的功能：记录一次失败登录并判断是否进入锁定
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

// #下面代码实现的功能：登录成功后重置失败计数
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

// #下面代码实现的功能：提供 CSRF token
export function handleCsrf() {
  const token = randomToken(18);
  return {
    payload: { csrfToken: token },
    cookies: [buildCookie(CSRF_COOKIE_NAME, token, { maxAge: 3600, httpOnly: false })],
    status: 200,
  };
}

// #下面代码实现的功能：注册接口业务逻辑
export async function handleRegister(request, env) {
  if (!requireCsrf(request)) return { error: "CSRF 校验失败", status: 403 };
  let payload;
  try {
    payload = await request.json();
  } catch {
    return { error: "请求格式错误", status: 400 };
  }

  const [username, usernameErr] = validateUsername(payload?.username);
  if (usernameErr) return { error: usernameErr, status: 400 };
  const passwordErr = validatePassword(payload?.password);
  if (passwordErr) return { error: passwordErr, status: 400 };

  const passwordHash = await hashPassword(payload.password);
  try {
    await env.DB.prepare("INSERT INTO users (username, password_hash, created_at) VALUES (?, ?, ?)")
      .bind(username, passwordHash, new Date().toISOString())
      .run();
  } catch {
    return { error: "用户名已存在", status: 409 };
  }

  return { payload: { ok: true, message: "注册成功，请登录", username }, status: 200 };
}

// #下面代码实现的功能：登录接口业务逻辑
export async function handleLogin(request, env) {
  if (!requireCsrf(request)) return { error: "CSRF 校验失败", status: 403 };
  let payload;
  try {
    payload = await request.json();
  } catch {
    return { error: "请求格式错误", status: 400 };
  }

  const [username, usernameErr] = validateUsername(payload?.username);
  if (usernameErr) return { error: usernameErr, status: 400 };
  const password = String(payload?.password || "");
  const ip = ipFromRequest(request);

  const limiter = await enforceRateLimit(env, ip, username);
  if (limiter.blocked) {
    await logFailure(env, ip, username, limiter.status === 423 ? "locked" : "rate_limited");
    return {
      error: limiter.status === 423 ? "登录失败次数过多，已临时锁定" : "登录过于频繁，请稍后再试",
      payload: { lockRemainingSeconds: limiter.remainingSeconds },
      status: limiter.status,
    };
  }

  const row = await env.DB.prepare("SELECT id, username, password_hash FROM users WHERE username = ?").bind(username).first();
  if (!row || !(await verifyPassword(password, row.password_hash))) {
    const remain = await markLoginFailure(env, ip, username, limiter.current, "invalid_credentials");
    if (remain > 0) return { error: "登录失败次数过多，已临时锁定", payload: { lockRemainingSeconds: remain }, status: 423 };
    return { error: "用户名或密码错误", status: 401 };
  }

  await markLoginSuccess(env, ip, username, limiter.current);
  const token = randomToken(32);
  const csrfToken = randomToken(18);
  const tokenHash = await sha256Hex(token);
  const hours = Number(env.SESSION_TTL_HOURS || DEFAULT_SESSION_HOURS);
  const expiresAt = Date.now() + hours * 3600 * 1000;

  await env.DB.prepare("INSERT INTO sessions (token_hash, user_id, csrf_token, expires_at, created_at) VALUES (?, ?, ?, ?, ?)")
    .bind(tokenHash, row.id, csrfToken, expiresAt, Date.now())
    .run();

  return {
    payload: { ok: true, user: { id: row.id, username: row.username }, csrfToken },
    status: 200,
    cookies: [
      buildCookie(SESSION_COOKIE_NAME, token, { maxAge: hours * 3600, httpOnly: true }),
      buildCookie(CSRF_COOKIE_NAME, csrfToken, { maxAge: hours * 3600, httpOnly: false }),
    ],
  };
}

// #下面代码实现的功能：登出当前会话
export async function handleLogout(request, env) {
  const session = await getSession(request, env);
  if (session) await env.DB.prepare("DELETE FROM sessions WHERE id = ?").bind(session.sessionId).run();
  return {
    payload: { ok: true },
    status: 200,
    cookies: [
      buildCookie(SESSION_COOKIE_NAME, "", { maxAge: 0, httpOnly: true }),
      buildCookie(CSRF_COOKIE_NAME, "", { maxAge: 0, httpOnly: false }),
    ],
  };
}

// #下面代码实现的功能：登出所有设备
export async function handleLogoutAll(request, env) {
  const session = await getSession(request, env);
  if (!session) return { error: "请先登录", status: 401 };
  if (!requireCsrf(request, session)) return { error: "CSRF 校验失败", status: 403 };
  await env.DB.prepare("DELETE FROM sessions WHERE user_id = ?").bind(session.userId).run();
  return {
    payload: { ok: true },
    status: 200,
    cookies: [
      buildCookie(SESSION_COOKIE_NAME, "", { maxAge: 0, httpOnly: true }),
      buildCookie(CSRF_COOKIE_NAME, "", { maxAge: 0, httpOnly: false }),
    ],
  };
}

// #下面代码实现的功能：返回当前登录用户信息
export async function handleMe(request, env) {
  const session = await getSession(request, env);
  if (!session) return { payload: { authenticated: false }, status: 200 };
  return {
    payload: { authenticated: true, user: { id: session.userId, username: session.username }, csrfToken: session.csrfToken },
    status: 200,
  };
}
