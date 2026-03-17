# Dear · 小墨 MVP

一个极简、治愈风格的 AI 聊天前端，适合直接部署到 VPS。

## 你只要改 3 行

复制示例配置：

```bash
cp .env.example .env
```

然后编辑 `.env` 里的这三行：

```env
API_URL=你的中转API地址
API_KEY=你的API密钥
MODEL_NAME=你的模型名
```

## 在 VPS 启动

```bash
python3 server.py
```

打开：`http://你的VPSIP:8080`

后续你建立樱花内网穿透后，把公网域名指向这个本机端口即可。

## 文件说明

- `index.html`：单文件前端（内联 CSS + JS）
- `server.py`：极简后端代理（从 `.env` 读取 API 设置、注入 system prompt）
- `.env.example`：环境变量模板

## 关键特性

- 自动注入隐藏的 `system` 提示词（前端不可见）
- 上下文记忆（localStorage）
- 仅保留聊天区 + 输入框，适合手机和电脑
