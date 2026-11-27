# AGENTS.md

本文件为在本仓库中运行 OpenCode 会话提供精简指引，仅收录那些非显而易见、容易踩坑的仓库专属事实。

## 仓库结构

这是一个 AI 设备日志诊断平台的单体仓库（monorepo）。

- `backend/` — FastAPI 后端服务（Python 3.12）。应用入口对象为 `app.main:app`。
- `apps/web/` — Vue 3 + TypeScript + Vite + Element Plus 前端界面（中文界面），目前是唯一已实现的前端客户端。
- `cli/` — Python SDK 及 `diag` 命令行工具（`src/` 布局，详见 `cli/pyproject.toml`）。
- 插件系统已移除（按产品决策）：不再提供插件 SDK/管理；如需专用解析器，直接扩展 `backend/app/services/parser/`。
- `deploy/` — Docker Compose 编排（postgres + redis + milvus + minio + backend + worker + frontend + prometheus + grafana；ollama 在 `gpu` profile 下），访问地址为 `http://localhost`。嵌入服务可用 `docker-compose.bge.yml` 在后端镜像内加载，或用 `docker-compose.embedding.yml` 起独立 TEI 服务。
- `docs/` — 大量规格文档（SAD、API、Agent、测试、编码规范等）。部分早期文档仍写有插件/多端/Elasticsearch 等规划性内容，以当前代码与 `docs/16-Implementation/` 为准。
- `apps/desktop`（Tauri）与 `apps/mobile`（Flutter）目前仅为占位目录，尚未实现。

## 后端命令（在 `backend/` 目录下运行）

- 安装依赖：`pip install -r requirements.txt`
- 开发服务器：`uvicorn app.main:app --reload`（默认端口 8000）
- 测试：`pytest` — 配置见 `pytest.ini`（`pythonpath = .`，`testpaths = tests`）。
  - 运行单个测试：`pytest tests/test_parser.py::test_name` 或 `pytest -k "expr"`。
  - 测试无需任何外部服务：`tests/conftest.py` 会自动创建内存版 SQLite 数据库，强制 `MILVUS_ENABLED=false`、`EMBEDDING_PROVIDER=hash`、`EMBEDDING_HASH_FALLBACK=true`，并关闭 Reranker 与 Celery 异步。默认 `LLM_PROVIDER=mock`，因此无需 API Key 或网络。
- 数据库迁移：使用 Alembic，位于 `backend/migrations`。Docker 部署在启动时自动执行 `alembic upgrade head`。`alembic.ini` 中硬编码了本地 Postgres 地址，因此若要本地手动执行迁移，需要先运行一个 Postgres 实例。

## 前端命令（在 `apps/web/` 目录下运行）

- `npm install` 后执行 `npm run dev`（Vite 开发服务器）。
- Vite 开发代理将 `/api` 转发至 `http://localhost:8000`，因此本地开发时需让后端运行在 8000 端口。
- `npm test` 运行 Vitest（`vitest run`，jsdom 环境，用例位于 `src/__tests__/`）；`npm run build` 构建；未配置 lint/typecheck 脚本，可用 `npx vue-tsc --noEmit` 手动类型检查。

## 架构与约定（以约定方式强制执行，详见 `docs/08-Coding/Coding-Standard.md`）

- 分层结构：API 路由 → Service 服务层 → Repository 仓储 → DB 数据库。路由中不得包含业务逻辑或直接写 SQL，请使用 SQLAlchemy ORM。
- LLM 调用**必须**经由 Provider 抽象层（`services/providers/`：DeepSeek / Mock / OpenAI 兼容），不得直接调用 SDK。默认 Provider 为 `mock`。
- 提示词（Prompt）以版本化文件形式存放于 `services/prompts/`，并通过提示词加载器加载 — 严禁在代码中硬编码提示词字符串。
- 无插件机制：新增日志格式直接在 `backend/app/services/parser/` 扩展 `BaseParser` 并注册到 `ParserRegistry`。
- 后端配置来源于 `.env`（模板在 `backend/.env.example`）。切勿提交 `.env` 或任何密钥。生产环境中 `SECRET_KEY` 必须是随机的 64 字符字符串。Settings 中 `MILVUS_ENABLED` / `MINIO_ENABLED` 默认为 `false`，但 `deploy/docker-compose.yml` 实际注入为 `true`，且设置 `EMBEDDING_HASH_FALLBACK=false`（无 BGE/API 时向量检索直接报错，不降级哈希）。默认向量集合为 `knowledge_chunks_v3`（1024 维、BGE-large）。

## 工具链注意事项

- 编码规范中*推荐*使用 Black / Ruff / MyPy / Bandit，但这些工具均未在本仓库安装或配置（不在 `requirements.txt` 中，也无配置文件）。不要假设 `ruff` / `black` / `mypy` 可用 — 它们在此处并未接入。
- 工具版本需锁定：`requirements.txt` 中固定为 `pytest==8.3.3`。仓库中存在 pytest 9.x 的缓存，请始终使用锁定版本。
