<!--
这个文件实现什么功能：提供 Dear 项目的整体介绍、使用说明与一体化启动教程。
它负责什么：帮助主理人/开发者快速理解项目定位、完成环境配置、启动服务并完成基础验证。
它不负责什么：不替代后端源码注释、不定义接口协议细节、不承诺生产运维 SLA。
对外暴露什么：一份可直接照着执行的 Markdown 文档（项目介绍 + 使用说明 + 启动步骤 + 常见问题）。
依赖哪些关键模块：server.py、backend/http_handler.py、backend/agent_core.py、.env 配置项、index.html。
-->

# Dear 项目介绍与使用启动教程

## 1. 项目介绍

Dear 是一个面向休学 / 迷茫 / 焦虑青少年的陪伴型 AI 对话产品。当前 MVP 以「小墨」为核心角色，强调：

- 极度安全
- 零评判
- 零说教
- 用生活化细节与镜像共情提供陪伴

当前仓库是 **VPS 直跑 Python 服务** 的形态：

- 前端：`index.html`（单页聊天界面）
- 后台：`admin.html`（主理人后台管理界面）
- 后端：`server.py` + `backend/`（认证、会话、聊天、主 agent 核心）
- 存储：SQLite（默认 `dear.db`）

---

## 2. 你会用到的核心文件

- `server.py`：服务入口（加载环境变量、初始化数据库、启动 HTTP 服务）
- `backend/agent_core.py`：主 agent 核心层（人格/安全/场景/定制的主要入口）
- `backend/http_handler.py`：接口路由层（`/api/auth/*`、`/api/chat`、静态页面）
- `backend/auth.py`：注册/登录/会话管理
- `backend/admin_auth.py`：后台管理员登录与后台会话
- `backend/admin_service.py`：后台概览、用户与会话管理
- `index.html`：登录与聊天页面
- `admin.html`：后台管理页面
- `.env`：运行时配置（模型地址、API Key、端口等）

---

## 3. 启动前准备

### 3.1 环境要求

- Linux / macOS / WSL（推荐）
- Python 3.10+（当前环境可用 Python 3.12）

### 3.2 配置环境变量

在项目根目录（`/home/tong/Dear`）执行：

```bash
cp /home/tong/Dear/.env.example /home/tong/Dear/.env
```

然后编辑 `/home/tong/Dear/.env`，至少配置以下项：

```env
API_URL=https://api.openai.com/v1
API_KEY=sk-xxxxxxxxxxxxxxxxxxxxxxxx
MODEL_NAME=gpt-4o
HOST=0.0.0.0
PORT=8080
SESSION_TTL_HOURS=168
COOKIE_SECURE=false
ADMIN_USERNAME=dear_admin
ADMIN_PASSWORD=change_me_now
ADMIN_SESSION_TTL_HOURS=12
```

> 生产环境如已走 HTTPS，建议把 `COOKIE_SECURE=true`。
> 后台管理员账号通过 `.env` 托管，修改后台账号后需要重启服务。

---

## 4. 一条命令启动

在项目根目录执行：

```bash
python3 /home/tong/Dear/server.py
```

正常启动后会监听：

- `http://0.0.0.0:8080`

---

## 5. 使用说明（从 0 到可聊天）

1. 浏览器打开：`http://服务器IP:8080/`（本机可用 `http://127.0.0.1:8080/`）
2. 进入登录页后先注册账号，再登录
3. 登录成功后进入聊天页，即可与小墨对话
4. 页面支持：
   - `Enter` 发送
   - `Shift + Enter` 换行
   - 退出当前会话 / 下线全部设备
5. 聊天记录会按账号缓存在当前浏览器（本地缓存）

### 5.1 主理人后台

1. 确认 `.env` 已设置 `ADMIN_USERNAME` 与 `ADMIN_PASSWORD`
2. 重启服务
3. 浏览器打开：`http://服务器IP:8080/admin`
4. 使用管理员账号登录后，可查看：
   - 用户总览
   - 活跃会话列表
   - 按用户下线全部设备
   - 主 agent 版本与层配置只读巡检

---

## 6. 启动验证（推荐）

> 当前服务不支持 `HEAD /`，所以建议用 `GET` 验证。

### 6.1 首页验证

```bash
curl -i http://127.0.0.1:8080/
```

期望：HTTP 状态码 `200`。

### 6.2 健康检查

```bash
curl -i http://127.0.0.1:8080/healthz
```

期望：HTTP 状态码 `200`。

---

## 7. 常见问题排查

### 7.1 报错：`OSError: [Errno 98] Address already in use`

说明端口（默认 8080）已被占用。

先查占用进程：

```bash
ss -ltnp | grep ':8080'
```

可选方案：

- 结束占用进程后重启服务
- 或临时改端口启动：

```bash
PORT=8090 python3 /home/tong/Dear/server.py
```

### 7.2 页面打开但聊天失败

重点检查：

- `.env` 中 `API_URL / API_KEY / MODEL_NAME` 是否正确
- VPS 是否能访问上游模型服务
- 服务端日志是否有上游请求报错

### 7.3 登录后很快掉线

重点检查：

- `SESSION_TTL_HOURS` 是否设置过小
- 反向代理与 `COOKIE_SECURE` 是否匹配（HTTP 场景下不应开 `COOKIE_SECURE=true`）

---

## 8. 部署建议（简版）

- 开发/测试：直接 `python3 server.py`
- 线上：建议使用 `systemd` 或 `supervisor` 托管进程
- Cloudflare 推荐只做域名映射/代理，业务逻辑留在 VPS 后端

---

## 9. 给主理人的快速检查清单

- [ ] `.env` 已配置并保存
- [ ] `python3 server.py` 可启动
- [ ] 首页 `GET /` 返回 200
- [ ] `GET /healthz` 返回 200
- [ ] 可完成注册、登录、发送消息、退出登录
