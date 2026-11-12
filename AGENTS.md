# AGENTS.md

本文件为在本仓库中运行 OpenCode 会话提供精简指引，仅收录那些非显而易见、容易踩坑的仓库专属事实。

## 仓库结构

这是一个 AI 设备日志诊断平台的单体仓库（monorepo）。

- `backend/` — FastAPI 后端服务（Python 3.12）。应用入口对象为 `app.main:app`。
- `apps/web/` — Vue 3 + TypeScript + Vite + Element Plus 前端界面（中文界面），目前是唯一已实现的前端客户端。
- `cli/` — Python SDK 及 `diag` 命令行工具（`src/` 布局，详见 `cli/pyproject.toml`）。
- 插件系统已移除（按产品决策）：不再提供插件 SDK/管理；如需专用解析器，直接扩展 `backend/app/services/parser/`。
- `deploy/` — Docker Compose 编排（postgres + redis + backend + frontend），访问地址为 `http://localhost`。
- `docs/` — 大量规格文档（SAD、API、插件、Agent、测试、编码规范等）。在猜测约定前请先阅读这些文档。
- `apps/desktop`（Tauri）与 `apps/mobile`（Flutter）目前仅为占位目录，尚未实现。

## 后端命令（在 `backend/` 目录下运行）

- 安装依赖：`pip install -r requirements.txt`
- 开发服务器：`uvicorn app.main:app --reload`（默认端口 8000）
- 测试：`pytest` — 配置见 `pytest.ini`（`pythonpath = .`，`testpaths = tests`）。
  - 运行单个测试：`pytest tests/test_parser.py::test_name` 或 `pytest -k "expr"`。
  - 测试无需任何外部服务：`tests/conftest.py` 会自动创建内存版 SQLite 数据库，并强制 `MILVUS_ENABLED=false`。默认 `LLM_PROVIDER=mock`，因此无需 API Key 或网络。
- 数据库迁移：使用 Alembic，位于 `backend/migrations`。Docker 部署在启动时自动执行 `alembic upgrade head`。`alembic.ini` 中硬编码了本地 Postgres 地址，因此若要本地手动执行迁移，需要先运行一个 Postgres 实例。

## 前端命令（在 `apps/web/` 目录下运行）

- `npm install` 后执行 `npm run dev`（Vite 开发服务器）。
- Vite 开发代理将 `/api` 转发至 `http://localhost:8000`，因此本地开发时需让后端运行在 8000 端口。
- **未配置** `test` / `lint` / `typecheck` 等 npm 脚本。`vue-tsc` 作为开发依赖存在，可用于手动类型检查（`npx vue-tsc --noEmit`），但不要假设 `npm test` 可用。

## 架构与约定（以约定方式强制执行，详见 `docs/08-Coding/Coding-Standard.md`）

- 分层结构：API 路由 → Service 服务层 → Repository 仓储 → DB 数据库。路由中不得包含业务逻辑或直接写 SQL，请使用 SQLAlchemy ORM。
- LLM 调用**必须**经由 Provider 抽象层（`services/providers/`：DeepSeek / Mock / OpenAI 兼容），不得直接调用 SDK。默认 Provider 为 `mock`。
- 提示词（Prompt）以版本化文件形式存放于 `services/prompts/`，并通过提示词加载器加载 — 严禁在代码中硬编码提示词字符串。
- 无插件机制：新增日志格式直接在 `backend/app/services/parser/` 扩展 `BaseParser` 并注册到 `ParserRegistry`。
- 后端配置来源于 `.env`（请将 `.env.example` 复制为 `.env`）。切勿提交 `.env` 或任何密钥。生产环境中 `SECRET_KEY` 必须是随机的 64 字符字符串；`MILVUS_ENABLED` / `MINIO_ENABLED` 默认关闭。

## 工具链注意事项

- 编码规范中*推荐*使用 Black / Ruff / MyPy / Bandit，但这些工具均未在本仓库安装或配置（不在 `requirements.txt` 中，也无配置文件）。不要假设 `ruff` / `black` / `mypy` 可用 — 它们在此处并未接入。
- 工具版本需锁定：`requirements.txt` 中固定为 `pytest==8.3.3`。仓库中存在 pytest 9.x 的缓存，请始终使用锁定版本。
