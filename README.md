# Dear · 小墨 MVP（VPS 部署模式）

Dear 当前采用 **VPS 托管服务 + Cloudflare 仅做公网域名映射（DNS/代理）** 的部署方式。

## 部署目标

- Python 服务只在 VPS 上运行（`server.py`）。
- Cloudflare 不再承载 Worker 业务逻辑，只负责域名映射到 VPS。
- 主 agent 核心在后端 Python 模块集中维护。

---

## 1) VPS 启动

### 环境变量（`.env`）

最少需要：

```env
API_URL=你的上游模型 API 根地址
API_KEY=你的上游模型密钥
MODEL_NAME=你的模型名
HOST=0.0.0.0
PORT=8080
SESSION_TTL_HOURS=168
COOKIE_SECURE=false
ADMIN_USERNAME=dear_admin
ADMIN_PASSWORD=change_me_now
ADMIN_SESSION_TTL_HOURS=12
```

> 生产环境建议把 `COOKIE_SECURE=true`，并通过 HTTPS 访问。
> 后台管理台账号由 `.env` 中的 `ADMIN_USERNAME` / `ADMIN_PASSWORD` 托管，修改后需重启服务。

### 启动服务

```bash
python3 server.py
```

启动后默认监听：`http://0.0.0.0:8080`

---

## 2) Cloudflare 域名映射（仅映射，不跑 Worker）

1. 在 Cloudflare DNS 中添加 `A` 记录（或 `AAAA`）指向 VPS 公网 IP。
2. 需要 CDN/隐藏源站时可开启橙云代理；需要直连调试可关闭代理。
3. 将站点域名流量转发到 VPS 端口（通常结合 Nginx/Caddy 做 80/443 -> 8080 反向代理）。

---

## 3) API 接口（VPS 当前实现）

### 认证相关

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/auth/me` | 查询登录状态 |
| POST | `/api/auth/register` | 注册 |
| POST | `/api/auth/login` | 登录 |
| POST | `/api/auth/logout` | 登出当前会话 |
| POST | `/api/auth/logout_all` | 下线当前账号所有设备 |

### 后台管理相关

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/admin` | 后台管理页面 |
| GET | `/api/admin/me` | 查询后台登录状态与配置状态 |
| POST | `/api/admin/login` | 后台管理员登录 |
| POST | `/api/admin/logout` | 后台管理员登出 |
| GET | `/api/admin/dashboard` | 查询后台概览数据 |
| GET | `/api/admin/users` | 查询后台用户列表 |
| GET | `/api/admin/sessions` | 查询当前活跃会话 |
| POST | `/api/admin/users/logout_all` | 按用户下线全部设备 |

### 聊天相关

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/chat` | 发起聊天 |

### 健康检查

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/healthz` | 服务健康状态 |

---

## 4) 文件说明

- `server.py`：VPS 启动入口
- `backend/http_handler.py`：HTTP 路由与响应处理
- `backend/auth.py`：认证与会话逻辑
- `backend/chat.py`：聊天服务（调用主 agent 核心层）
- `backend/agent_core.py`：主 agent 核心层（人格/安全/定制/版本入口）
- `backend/db.py`：SQLite 存储与会话清理
- `backend/admin_auth.py`：后台管理员鉴权与后台会话
- `backend/admin_service.py`：后台概览、用户与会话管理服务
- `index.html`：前端页面
- `admin.html`：后台管理页面

---

## 5) 主 agent 后续优化入口

- 人格层 / 安全层 / 定制层：编辑 `backend/agent_core.py` 的 `AGENT_CORE_LAYERS`
- 版本层：编辑 `backend/agent_core.py` 的 `AGENT_CORE_VERSION`
- 消息组装入口：`build_agent_messages`
