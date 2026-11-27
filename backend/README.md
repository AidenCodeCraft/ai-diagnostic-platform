# Backend

FastAPI 服务，入口为 `app.main:app`。提供日志上传/解析/分析、报告、知识库 RAG、多轮对话（SSE）与管理 API，统一前缀 `/api/v1`。

## 运行

```bash
pip install -r requirements.txt
cp .env.example .env          # 按需修改；Docker 部署由 compose 注入环境变量
uvicorn app.main:app --reload --port 8000
```

需要容器内/本地真实 BGE 语义嵌入时，额外安装可选 ML 依赖（torch + sentence-transformers，体积较大）：

```bash
pip install -r requirements-ml.txt
```

## 测试

```bash
python -m pytest -q
python -m pytest tests/test_parser.py::test_name
python -m pytest -k "expr"
python -m pytest tests/regression -m golden -q   # 黄金集回归，需外部服务
```

配置见 `pytest.ini`（`pythonpath = .`、`testpaths = tests`）。普通测试无需任何外部服务：`tests/conftest.py` 使用内存 SQLite，强制 `EMBEDDING_PROVIDER=hash`、`EMBEDDING_HASH_FALLBACK=true`，关闭 Milvus、Reranker 与 Celery 异步。当前实测 **948 passed / 20 skipped**。

## 目录

```
app/
  api/         路由层（auth / admin / chat / diagnostics / knowledge / quality / system）
  services/    业务逻辑（parser、providers、prompts、knowledge、rag、chat 等）
  models/      SQLAlchemy 模型
  schemas/     Pydantic 模型
  database/    会话与连接管理
  core/        Settings 配置
migrations/    Alembic 迁移
tests/         单元与集成测试
scripts/       验证与运维脚本
```

## 约定

- LLM 调用必须经 `app/services/providers/` 抽象层；Prompt 放在 `app/services/prompts/`，禁止硬编码。
- 分层：API 路由 → Service → Repository → DB；路由中不写业务逻辑或裸 SQL。
- 新增日志格式扩展 `app/services/parser/` 的 `BaseParser` 并注册到 `ParserRegistry`；无插件机制。
- 向量集合默认 `knowledge_chunks_v3`（1024 维，模型 `BAAI/bge-large-zh-v1.5`）；`EMBEDDING_DIM`、`MILVUS_DIM` 与集合维度必须一致。
