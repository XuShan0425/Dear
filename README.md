# Dear · 小墨 MVP

一个极简、治愈风格的 AI 聊天前端，支持 VPS 和 Cloudflare Workers。

## 本次升级（重点）

- Worker 端改为 **D1 真实用户体系**（注册 / 登录 / 登出 / 会话）。
- 登录增加 **按 IP + 用户名分钟级限流**。
- 连续失败 **10 次锁定 10 分钟**，前端弹出限时提示。
- 增加 **登录失败日志**（时间 / IP / 用户名 / 原因）。
- 增加 **后台管理界面**（查看登录失败日志）。
- 增加 **CSRF Token** 校验（登录、注册、聊天、登出等 POST 接口）。
- 聊天记录改为 `xiaomo_history_${username}`。
- 登出支持“是否清理当前用户本地缓存”。
- 支持 **主动下线所有设备**（按 user_id 清 session）。

---

## Worker（推荐，D1 版）

### 1) 配置 D1

创建 D1 数据库后，填入 `wrangler.toml`：

```toml
[[d1_databases]]
binding = "DB"
database_name = "dear-auth"
database_id = "你的 D1 database_id"
```

### 2) 设置 Secret

```bash
npx wrangler secret put API_URL
npx wrangler secret put API_KEY
npx wrangler secret put MODEL_NAME
npx wrangler secret put SESSION_TTL_HOURS
```

### 3) 部署

```bash
npx wrangler deploy
```

---

## VPS（现状）

- VPS 仍可运行 `server.py`（SQLite 版本）。
- 当前“D1 真实用户体系”主要在 Worker 端实现。

---

## 后台管理界面

前端右上角有“后台”按钮。

默认后台账号（按你的需求）：
- 用户名：`Tong`
- 密码：`15010190`

> 建议上线后改为环境变量并定期轮换。

---

## API 接口表

### 认证相关

| 方法 | 路径 | 说明 | 成功 | 常见错误 |
|---|---|---|---|---|
| GET | `/api/auth/csrf` | 获取 CSRF Token 并写入 cookie | 200 | - |
| POST | `/api/auth/register` | 注册 | 200 | 400 参数错误 / 403 CSRF / 409 用户名已存在 |
| POST | `/api/auth/login` | 登录 | 200 | 400 参数错误 / 401 凭证错误 / 403 CSRF / 423 锁定 / 429 频率过高 |
| GET | `/api/auth/me` | 查询登录状态 | 200 | - |
| POST | `/api/auth/logout` | 登出当前会话 | 200 | 403 CSRF |
| POST | `/api/auth/logout_all` | 下线当前账号所有设备 | 200 | 401 未登录 / 403 CSRF |

### 聊天相关

| 方法 | 路径 | 说明 | 成功 | 常见错误 |
|---|---|---|---|---|
| POST | `/api/chat` | 发起聊天 | 200 | 400 参数错误 / 401 未登录 / 403 CSRF / 502 上游失败 |

### 管理后台

| 方法 | 路径 | 说明 | 成功 | 常见错误 |
|---|---|---|---|---|
| POST | `/api/admin/login` | 管理员登录 | 200 | 401 账号密码错误 |
| GET | `/api/admin/login-failures` | 查看登录失败日志 | 200 | 401 未授权 |

---

## Worker / VPS 差异说明

| 功能 | Worker（D1） | VPS（SQLite） |
|---|---|---|
| 用户注册/登录 | ✅ 真实用户体系 | ✅ SQLite 用户体系 |
| 分钟级限流 + 锁定 | ✅ | ❌（待同步） |
| CSRF Token | ✅ | ❌（待同步） |
| 管理后台失败日志 | ✅ | ❌（待同步） |
| 主动下线所有设备 | ✅ | ✅ |

---

## 本地调试

```bash
cp .dev.vars.example .dev.vars
npx wrangler dev
```

## 文件说明

- `index.html`：登录 + 聊天 + 后台管理 UI
- `worker.js`：Worker 路由入口
- `worker/*.js`：按功能模块拆分（auth/chat/admin/db/utils/constants）
- `server.py`：VPS 启动入口
- `backend/*.py`：VPS 后端模块（auth/chat/db/http_handler/constants/env_utils）
- `wrangler.toml`：Worker + D1 绑定
