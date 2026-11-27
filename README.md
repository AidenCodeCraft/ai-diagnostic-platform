# AI Diagnostic Platform

面向设备日志的 AI 诊断平台：上传日志 → 解析与 AI 分析 → 生成报告；同时提供带知识库检索（RAG）的多轮对话式诊断界面。

> 状态（2026-11）：v1.0 功能已完成并可用；当前只有 **Web 前端**（`apps/web`）已实现。桌面端（Tauri）与移动端（Flutter）仍为规划，尚未实现。插件系统已按产品决策移除，不再提供插件 SDK/管理。

## 核心能力

- **日志处理**：多格式日志上传（≤100 MB）、解析、错误事件提取、分析流水线与异步任务。
- **AI 分析**：AI 诊断 Agent、规则与 Prompt 模板、分析报告（Markdown / PDF 下载）。
- **对话式诊断**：会话持久化、SSE 流式输出、Function Calling、多 Agent 协同、截图识别（图像上传 + OCR/视觉模型）。
- **知识库 RAG**：章节级切分、BM25 关键词召回 + Milvus 向量召回的 RRF 融合；本地 BGE 语义嵌入（1024 维）；知识导入、标准化、质量校验、图片管理。
- **平台能力**：多租户（组织 / 项目）、RBAC 权限、登录防爆破、管理后台、Bug 案例、黄金集回归、Prometheus 指标。
- **对象存储**：日志原文件与知识库图片存入 MinIO，未启用时回退本地目录。

## 技术栈

| 层 | 技术 |
|---|---|
| 后端 | Python 3.12、FastAPI、SQLAlchemy 2.0、Alembic、Pydantic v2、Celery（配置就绪） |
| AI / RAG | Provider 抽象层（Mock / DeepSeek / OpenAI 兼容）、sentence-transformers + BGE、rank-bm25、tiktoken |
| 前端 | Vue 3 + TypeScript + Vite + Element Plus + Pinia + vue-router + vue-i18n；Markdown（marked / v-md-editor）、PDF（jsPDF） |
| 数据 | PostgreSQL 16（主库）、Milvus 2.4（向量库）、Redis 7（缓存 / Broker）、MinIO（对象存储） |
| 运维 | Docker Compose、Nginx、Prometheus + Grafana；GitHub Actions 测试与黄金集回归 |
| CLI | `cli/` — Python SDK（`ai_diagnostic`）与 `diag` 命令 |

## 仓库结构

```
backend/        FastAPI 应用、服务层、Repository、数据模型、Prompt、Alembic 迁移、测试
apps/web/       Vue 3 前端（对话、知识库、报告、管理后台）
apps/mobile/    移动端占位目录（规划：Flutter）
apps/desktop/   桌面端占位目录（规划：Tauri）
cli/            Python SDK 与命令行工具
deploy/         Docker Compose、K8s 清单、监控配置、部署说明
docs/           规格、设计、API、测试、编码规范、验证报告
```

新增日志格式请扩展 `backend/app/services/parser/` 的 `BaseParser` 并注册到 `ParserRegistry`；无插件机制。LLM 调用必须经由 `backend/app/services/providers/` 抽象层，Prompt 以版本化文件形式放在 `backend/app/services/prompts/`，不得硬编码。

## 快速开始（Docker Compose）

```bash
cd deploy
docker compose up -d --build
```

访问 <http://localhost>（Nginx 前端），后端 API 在 <http://localhost:8000>，`/api/v1` 为统一前缀。基础 compose 默认启动 PostgreSQL、Redis、Milvus、MinIO、backend、worker、frontend、Prometheus、Grafana；Ollama 位于 `gpu` profile 下，按需启用。

```bash
curl http://localhost:8000/health                 # 服务健康
curl http://localhost:8000/api/v1/vector/health   # 向量服务与 embedding provider
```

默认 `LLM_PROVIDER=mock`，无需 API Key 即可跑通界面；生产需改用 `deepseek` 并配置 `DEEPSEEK_API_KEY`。默认 `MILVUS_ENABLED=true`、`EMBEDDING_HASH_FALLBACK=false`，因此未配置 embedding 时向量搜索会直接报错，而不是静默降级为哈希向量。

### 容器内启用本地 BGE 语义嵌入

当前生产口径：collection `knowledge_chunks_v3`、**1024 维**、模型 `BAAI/bge-large-zh-v1.5`。

```powershell
# 前置：宿主机已缓存模型（HF 缓存根目录，其下含 hub/models--BAAI--bge-large-zh-v1.5）
$env:HF_CACHE_DIR = "$env:USERPROFILE\.cache\huggingface"
docker compose -f deploy/docker-compose.yml -f deploy/docker-compose.bge.yml up -d --build backend worker
```

该覆盖文件会设置 `INSTALL_ML=true`（镜像安装 torch / sentence-transformers，体积 +2 GB 以上）、`EMBEDDING_PROVIDER=local`、`EMBEDDING_LOAD_TIMEOUT=180`、离线变量，并只读挂载 HF 缓存。验收：`/api/v1/vector/health` 返回 `embedding_provider=BGEEmbedder`、`embedding_dimension=1024`、`is_semantic=true`。

`deploy/docker-compose.embedding.yml` 提供另一种形态：把 embedding 拆为独立 TEI HTTP 服务，后端保持精简镜像；模板已按 `BAAI/bge-large-zh-v1.5` / 1024 维配置，与 `knowledge_chunks_v3` 对齐。两种覆盖文件不要同时叠加。切换 embedding 后执行 `POST /api/v1/vector/reindex-all` 重建向量。

## 本地开发

```powershell
# 后端（Python 3.12，依赖锁定见 requirements.txt）
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000

# 前端（Vite 开发服务器，/api 代理到 http://localhost:8000）
cd apps/web
npm install
npm run dev
```

配置模板为 `backend/.env.example`（复制为 `backend/.env`）；Docker 部署时以 `deploy/docker-compose.yml` 注入的环境变量为准。生产环境务必修改 `SECRET_KEY`（随机 64 字符）与 MinIO 默认口令；切勿提交 `.env` 或密钥。可选 ML 依赖单独安装在 `backend/requirements-ml.txt`。

常用命令：

| 操作 | 命令 |
|---|---|
| 后端测试 | `cd backend && ..\.venv\Scripts\python.exe -m pytest -q` |
| 单个测试 | `..\.venv\Scripts\python.exe -m pytest tests/test_parser.py::test_name` |
| 前端测试 | `cd apps/web && npm test` |
| 前端类型检查 | `npx vue-tsc --noEmit`（仓库未配置 typecheck 脚本） |
| 前端构建 | `npm run build` |
| 黄金集回归 | `cd backend && ..\.venv\Scripts\python.exe -m pytest tests/regression -m golden -q`（需自托管 runner 与外部服务） |

测试无需外部服务：`tests/conftest.py` 使用内存 SQLite、强制 `EMBEDDING_PROVIDER=hash` 并关闭 Milvus / Reranker / Celery 异步。最新实测：后端 **948 passed / 20 skipped**；前端 Vitest **80 passed / 17 files**。

## 关键配置

| 变量 | 默认（Settings） | Compose 默认值 | 说明 |
|---|---|---|---|
| `LLM_PROVIDER` | `mock` | `mock` | `mock` / `deepseek` / `openai` 兼容 Provider |
| `DATABASE_URL` | `postgresql://ai:ai@localhost:5432/diagnostic` | `...@postgres:5432/diagnostic` | 主库 |
| `MILVUS_ENABLED` | `false` | `true` | 向量检索开关 |
| `MILVUS_COLLECTION` / `MILVUS_DIM` | `knowledge_chunks_v3` / `1024` | 同默认 | 集合与向量维度 |
| `EMBEDDING_PROVIDER` | `auto` | `auto`（BGE 覆盖文件为 `local`） | `auto` / `local`(`bge`) / `api` / `hash` |
| `EMBEDDING_MODEL` | `BAAI/bge-large-zh-v1.5` | 同默认 | 本地语义模型（1024 维） |
| `EMBEDDING_HASH_FALLBACK` | `true` | `false` | 无 BGE/API 时是否静默降级为哈希向量 |
| `MINIO_ENABLED` | `false` | `true` | 对象存储开关 |
| `PROMETHEUS_METRICS_ENABLED` | `false` | `true` | `/metrics` 指标输出 |
| `RERANKER_ENABLED` | `false` | `false` | Cross-Encoder 精排，默认关闭（黄金集实测变差） |

## 文档

- `docs/02-SAD/Software-Architecture.md` — 软件架构
- `docs/04-API/OpenAPI.md` — API 说明
- `docs/09-Development/Development-Roadmap.md` — 开发路线图
- `docs/16-Implementation/Production-Deployment-Guide.md` — 生产部署指南
- `docs/20-Audit/` — 分阶段验证报告（带日期的历史快照，数值仅代表当时环境）
- `AGENTS.md` — 仓库约定与易踩坑事项
- `deploy/README.md` — 部署与故障排查

部分设计与规划文档早于当前实现（如插件、多端、Elasticsearch 等描述），以本 README、`docs/16-Implementation/` 及代码/配置为准。

## License

Apache-2.0
