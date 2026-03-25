# Changelog

All notable changes to this project will be documented in this file.

The format is based on Keep a Changelog, and versioning is currently maintained as milestone-style project history.

## [Unreleased]

### Added
- 新增 VPS 部署形态下的后台管理页面与后台接口。
- 新增主 agent 核心层 `backend/agent_core.py`，集中管理人格层、风格层、安全层与版本号。
- 新增项目协作规范 `AGENTS.md`。
- 新增项目说明与启动文档 `PROJECT_GUIDE.md`。
- 新增外部聊天 API 适配入口 `backend/external_chat_api.py`。

### Changed
- 项目从 Cloudflare Worker 业务逻辑逐步迁移到 VPS Python 服务架构。
- 聊天编排逻辑改为通过 agent core 统一组装消息。
- 首页与聊天交互页面做了较大幅度调整。
- `.env.example` 补充了后台与部署相关配置示例。
- `README.md` 更新为 VPS 部署模式说明。

### Removed
- 移除旧的 Worker 业务文件与 `wrangler.toml` 主流程依赖。

### Notes
- 这是为后续重构 Dear 回复系统（记忆、场景、数据清洗、策略层）建立的 Git 基线版本。
- 从本次开始，建议每次功能改动都同步更新本文件，按 `Added / Changed / Fixed / Removed` 维护。
