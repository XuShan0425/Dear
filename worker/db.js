// #下面代码实现的功能：初始化 D1 数据库表结构
export async function ensureSchema(env) {
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

// #下面代码实现的功能：执行轻量数据清理
export async function lightweightCleanup(env) {
  const now = Date.now();
  await env.DB.prepare("DELETE FROM sessions WHERE expires_at <= ?").bind(now).run();
  await env.DB.prepare("DELETE FROM login_limits WHERE updated_at <= ?").bind(now - 7 * 24 * 3600 * 1000).run();
}
