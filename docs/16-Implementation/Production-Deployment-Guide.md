# 生产部署与 CI Runner 配置手册

> 适用对象：负责把这套平台部署到正式环境的人。
> 本文只讲**怎么装、怎么配、怎么验**；功能设计与验收口径见
> [`Deployment-Verification-Checklist.md`](./Deployment-Verification-Checklist.md)（V1~V7）与
> [`Knowledge-RAG-Quality-Roadmap.md`](./Knowledge-RAG-Quality-Roadmap.md)。
>
> **纪律**：生产环境改动前必须先获得确认；本文命令默认在测试环境执行。

---

# 一、生产部署

## 1. 主机与外部依赖

| 组件 | 版本/规格 | 说明 |
| --- | --- | --- |
| Docker + Docker Compose v2 | 24+ | `deploy/docker-compose.yml` 编排 postgres/redis/milvus/minio/backend/frontend/worker |
| PostgreSQL | 15+ | 业务库；`alembic upgrade head` 由容器启动时执行 |
| Redis | 7+ | Celery broker(`/1`) 与 result backend(`/2`)，同时是缓存 |
| Milvus | **2.4+** | 向量库；集合 `knowledge_chunks_v3`（本地实测 2.4.0 可用） |
| MinIO | 最新 | 日志与预处理产物；桶保持**私有**，访问走预签名（TTL 900s） |
| CPU/内存 | 4C/8G 起步 | 私有 BGE-large-zh（1024 维）常驻约 1.3GB；reranker 若开启再加 ~1.1GB |
| GPU | 可选 | 有 GPU 时 embedding 吞吐提升明显；无 GPU 也能跑（CPU 约 4~6 块/秒） |

> 若使用外部托管 PostgreSQL/Redis/MinIO，跳过对应容器，只改 `.env` 指向即可。

## 2. 配置（`.env`）

两个位置，别搞混：

| 文件 | 谁读它 | 放什么 |
| --- | --- | --- |
| `deploy/.env` | `docker compose` 的 `${VAR:-默认}` 插值 | 部署级变量（DB/Redis/Milvus/MinIO/密钥/上传上限） |
| `backend/.env` | 本地直跑后端（pydantic `env_file=".env"`，相对 CWD） | 本地开发/调试用 |

首次部署：`cp backend/.env.example deploy/.env`，再按下面逐项确认（**模板里没有的键补上**）：

### 2.1 必填

| 变量 | 说明 |
| --- | --- |
| `SECRET_KEY` | JWT 签名密钥，**必须是随机 64 字符**：`python -c "import secrets;print(secrets.token_urlsafe(48))"` |
| `DATABASE_URL` | `postgresql://user:pass@host:5432/diagnostic` |
| `DEEPSEEK_API_KEY` | 问答与截图识别共用；也可在管理后台「模型配置」里按模型配。截图识别会从 `llm.models[]` 中按 `deepseek-flash` → `isDefault` → deepseek 条目的顺序取 Key/BaseURL（后台值优先于环境变量） |
| `REDIS_URL` | `redis://host:6379/0` |

### 2.2 关键功能开关

| 变量 | 生产建议值 | 原因 |
| --- | --- | --- |
| `MILVUS_ENABLED` | `true` | 关掉会退化为关键词检索 |
| `MILVUS_COLLECTION` | `knowledge_chunks_v3` | v3 才有 `chunk_type/source/ts`，日志块与知识块才隔离得开 |
| `EMBEDDING_PROVIDER` | `local` | 私有 BGE，不外传文档 |
| `EMBEDDING_LOAD_TIMEOUT` | `1800` | 首次加载模型要下载/读盘，默认 30s 会失败 |
| `HF_HOME` | 持久化目录 | 模型缓存（约 1.5GB），容器重建不重下 |
| `MINIO_ENABLED` | `true` | 多机 worker 必须走对象存储，本地盘读不到别人的产物 |
| `MINIO_BUCKET` | `diagnostic-logs` | 桶私有，代码走 `presigned_get()` |
| `CELERY_ASYNC_INGEST` | `true` | 上传即返回，重活交给 worker |
| `CELERY_VISIBILITY_TIMEOUT` | `3600` | Redis 不设会重复投递长任务 |
| `MAX_UPLOAD_MB` | `100` | 单文件上限（含边界值 100×1024×1024 字节） |
| `LOG_INDEX_MAX_CHUNKS` | `300` | 单份日志入向量库的证据块上限；CPU 上 2000 块要 8 分钟 |
| `RERANKER_ENABLED` | **`false`** | 黄金集实测开启后 recall@5 1.000→0.889、MRR 0.849→0.733、耗时 9.5× |
| `RATE_LIMIT_ENABLED` | 按需 | 公网部署建议开启 |
| `DEEPSEEK_VISION_MODEL` | `deepseek-flash`（一般不用改） | 截图识别（OCR + 图像理解）用的模型；OCR 本身不依赖模型名，视觉兜底才用 |

> ⚠️ **不要**把 `MILVUS_COLLECTION` 留成 `v2`：v2 schema 没有 `chunk_type`，
> 检索无法强制过滤，日志报错文本会污染知识召回。

## 3. 首次部署步骤

```bash
# 1) 代码与配置
git clone <repo> && cd ai-diagnostic-platform
cp backend/.env.example backend/.env    # 按 §2 填写

# 2) 启动依赖 + 应用（首次会拉镜像）
cd deploy && docker compose up -d --build
docker compose ps                        # 等 postgres/redis/milvus/minio 都 healthy

# 3) 数据库迁移（容器启动时已自动执行，手工确认一次）
docker compose exec backend alembic upgrade head
#    容器启动日志里应看到 "alembic upgrade head" 无报错

# 4) 健康检查
curl -s http://localhost:8000/health              # {"status":"ok"}
curl -s http://localhost:8000/api/v1/logs/pipeline/health | head   # 需要管理员 token

# 5) 预热 embedding（首次加载 ~1.5GB 模型，别等第一个用户触发）
docker compose exec backend python -c "
from app.services.knowledge.embedding import get_embedder
e = get_embedder(); print('DIM', e.dimension, 'PROVIDER', e.provider_name)
"
# 期望输出 DIM 1024（若出现 hash 兜底说明模型没加载上，见 §8）

# 6) 回填知识库（把已上传文档切章节写入 Milvus；内容改动后必须重跑）
docker compose exec backend python -c "
from app.database.session import create_session
from app.services.knowledge.reindex_service import run_reindex
db = create_session(); print(run_reindex(db).summary())
"
# 期望 total_chunks > 0、failed_docs = 0、skipped_folders = 目录节点数

# 7) 索引一致性检查（回填后必须是 0 漂移；日常也可作为巡检，漂移时退出码 1）
docker compose exec backend python -m scripts.check_knowledge_index
# 期望 "[index] ✓ 索引与内容一致"，且 expected 与 indexed 数量相等

# 8) 管理员账号：应用启动时自动 seed（日志里会打印 "Seed complete: 2 default users ensured"）
#    默认账号 admin / admin123 —— 首次登录后立刻改密码
docker compose logs backend | grep -i "seed complete"
```

### 3.1 本地 BGE（CPU 版，本机已启用）

生产镜像默认不带 torch；启用本地 `BAAI/bge-large-zh-v1.5`（1024 维）用 overlay 即可，文档不出内网：

```bash
# 0) requirements-ml.txt 已把 torch 固定在 CPU wheel（约 190MB），GPU 机器自行换 CUDA 版本
# 1) 构建 ML 镜像（backend 与 worker 都要）
export HF_CACHE_DIR=/path/to/huggingface          # Windows: C:/Users/<you>/.cache/huggingface
docker buildx build --load --provenance=false -f backend/Dockerfile \
  -t deploy-backend:latest --build-arg INSTALL_ML=true .
BUILDX_NO_DEFAULT_ATTESTATIONS=1 docker compose -f deploy/docker-compose.yml \
  -f deploy/docker-compose.bge.yml build worker
# 2) 启动（必须 --force-recreate，否则容器仍是 base 镜像的 EMBEDDING_PROVIDER=auto）
docker compose -f deploy/docker-compose.yml -f deploy/docker-compose.bge.yml \
  up -d --force-recreate backend worker
# 3) 回填与校验
docker compose exec backend python -m scripts.reindex_knowledge
docker compose exec backend python -m scripts.reindex_knowledge --verify
curl -s http://localhost:8000/api/v1/vector/health
# 期望：embedding_provider=BGEEmbedder、embedding_dimension=1024、is_semantic=true、milvus_available=true
```

实测（2026-11-27，CPU-only）：镜像 4.07GB；`embed_batch` 约 55ms/条；136 个知识块回填约 1 分钟；语义改写问法（如「设备日志里哪个字段能看出固件版本号」）可稳定召回《设备端 · 日志搜索版本号》。
两个已知坑：①`docker compose build` 可能因 attestation 不更新本地 tag，表现为容器里 `import torch` 失败，用上面的 `buildx --load` 或 `BUILDX_NO_DEFAULT_ATTESTATIONS=1`；②`RERANKER_ENABLED` 在 overlay 中默认 `false`（黄金集实测开启会掉点），需要对比时显式设 `true`。

**本机一键启动（可选）**：在 `deploy/` 下放两个本地文件（均已被 `.gitignore` 忽略）——`.env` 写 `HF_CACHE_DIR=...`，`docker-compose.override.yml` 写 `include: [docker-compose.bge.yml]` 并给 backend/worker 加 `build.provenance: false`。之后在 `deploy/` 目录直接执行 `docker compose up -d --build` 就会自动带上本地 BGE，不用每次加 `-f`。注意必须在 `deploy/` 目录执行；从仓库根目录用 `-f deploy/docker-compose.yml` 时 Compose 不会自动加载 override，会退回 `EMBEDDING_PROVIDER=auto` 的无 ML 镜像。

## 4. Worker 部署要点

worker 跑预处理链（`ingest` 队列）与向量化（`embed` 队列）：

```yaml
# deploy/docker-compose.yml 里的 worker 服务（核心参数）
command: celery -A app.worker.celery_app:celery_app worker -Q ingest,embed -c 2 --loglevel=INFO
```

| 事项 | 做法 |
| --- | --- |
| 队列拆分 | 规模上来后把 `embed` 单独一台机器：embed 会常驻 BGE 抢 CPU，和 ingest 混跑会拖慢上传链路（V5 实测：两 worker 同时加载 BGE，index 350s） |
| 并发度 | Linux prefork `-c 2~4`；**Windows 必须 `-P solo -c 1`**（默认池会报 `OSError(9, '句柄无效')`） |
| 任务回收 | `CELERY_MAX_TASKS_PER_CHILD=50`，避免长跑内存膨胀 |
| 超时 | `CELERY_TASK_TIME_LIMIT=900`；单文件 100MiB 实测全链 230s，留 4 倍余量 |
| 幂等 | 任务键 `{log_id}:{stage}:{chunk_no}`，重复投递不会重复执行 |
| 共享状态 | 产物写 MinIO（`ingest/{log_id}/...`），不要依赖本地盘 |

## 5. 前端

```bash
cd apps/web && npm ci && npm run build     # 产物 dist/
```

nginx 反代（`/api` → backend:8000）已在 `deploy/` 里配好；自建时注意：

- `/api/` 与 `/health` 都要转发，SSE/流式接口需 `proxy_buffering off`
- 上传体积：`client_max_body_size 128m`（后端上限 100MiB）
- 静态资源带 hash，可长期缓存；`index.html` 不缓存

## 6. 验收（对应 V1~V7）

| 编号 | 内容 | 命令/操作 | 期望 |
| --- | --- | --- | --- |
| V1 | 知识库检索 | 管理后台 → 质量回归，或 `pytest tests/regression -m golden` | recall@5 ≥0.85、MRR ≥0.70（当前基线 1.000 / 0.849） |
| V2 | 真实失败样本 | 提问「进出站日志中搜索什么」 | 命中《FAQ》第 5 节，不是《线路》第 1 节 |
| V3 | 日志问答 | 上传一份真实设备日志 + 提问 | 结论为 answered，引用里有日志块与知识章节 |
| V4 | 100MiB 大文件 | 上传 100×1024×1024 字节日志 | 上传 <30s、提问 <30s、六阶段全绿 |
| V5 | 多 worker | 两个 worker + >100MiB 分片 | 分片落在不同 worker，产物 MinIO 可读 |
| V6 | 精排 A/B | 见 checklist | 默认关闭；开启需有指标提升证据 |
| V7 | 观测 | `GET /api/v1/logs/pipeline/health` | 各阶段无失败、零命中率 <5%、`is_semantic=true` |

## 7. 备份与回滚

| 数据 | 备份方式 | 说明 |
| --- | --- | --- |
| PostgreSQL | `pg_dump` 每日 | 业务数据 + 黄金集 + 检索轨迹 |
| Milvus | 可**重建**，不必备份 | 由 `run_reindex` 从 DB 文档重新生成；重建前确认文档都在 DB |
| MinIO | 生命周期策略 | 原始日志 30~90 天；`ingest/` 产物可随日志一起过期 |
| 配置 | `.env` 不入库，单独密钥管理 | 改配置后 `docker compose up -d` 重启生效 |

回滚：镜像回退到上一 tag → `alembic downgrade -1`（仅当本次带迁移）→ 重启。
**集合 schema 变更（v2→v3）不做静默兼容**：换集合名 + 重建，而不是原地升级。

## 8. 常见故障

| 现象 | 原因 | 处理 |
| --- | --- | --- |
| worker 启动即退出：`VersionMismatch: Redis transport requires redis-py 6.1+` | `kombu` 漂到 5.7 与 `redis==5.0.8` 冲突 | 锁 `kombu==5.4.2`（已在 `requirements.txt`） |
| embedding 是 `HashingEmbedder` | 模型没加载上，静默降级 | 看日志；确认 `sentence-transformers` 已装、`EMBEDDING_LOAD_TIMEOUT=1800`、`HF_HOME` 可写 |
| 上传成功但预处理一直 `pending` | worker 没连上 broker / 队列名不对 | `docker compose logs worker`；确认 `-Q ingest,embed` 与 `task_routes` 一致 |
| 分片任务报 `WinError 32` | Windows 上多任务抢同一临时文件 | 已修（落地文件按 pid 隔离）；自建 worker 需更新到最新 commit |
| 检索结果里混进日志报错文本 | 查询没按 `chunk_type` 过滤 | 检查代码是否走了 `search(..., chunk_types=[CHUNK_TYPE_SECTION])` |
| 大文件模板阶段极慢（十几分钟） | 逐行抢模板库文件锁 | 已修（批量 5000 行/次持锁 + 20 万行挖矿上限）；更新代码即可 |

---

# 二、CI 自托管 Runner（黄金集回归门禁）

`golden-regression` 需要真实 Milvus + BGE，跑在托管 runner 上太贵，所以走自托管。
它默认是 `skipped`（闸门 `GOLDEN_RUNNER_READY` 未设），不会显示成红叉。

## 1. 机器要求

| 项 | 要求 |
| --- | --- |
| OS | Linux x64（推荐）或 Windows x64 |
| CPU/内存 | 4C / 8G（BGE 常驻 1.3GB，Chromium 不参与） |
| 磁盘 | 20GB（Python 依赖 + 模型缓存 1.5GB + 报告） |
| 网络 | 能访问 GitHub + PostgreSQL + Milvus + MinIO（可以是同机 docker） |
| 依赖 | Python 3.12、`backend/requirements.txt`、Docker（跑 pg/milvus/minio） |

## 2. 注册 runner

```bash
# 在 GitHub: Settings → Actions → Runners → New self-hosted runner 取 token
mkdir -p /opt/actions-runner && cd /opt/actions-runner
curl -o actions-runner.tar.gz -L https://github.com/actions/runner/releases/download/v2.319.1/actions-runner-linux-x64-2.319.1.tar.gz
tar xzf actions-runner.tar.gz

./config.sh \
  --url https://github.com/<owner>/<repo> \
  --token <RUNNER_TOKEN> \
  --labels ai-diag \
  --name ai-diag-golden \
  --unattended

sudo ./svc.sh install && sudo ./svc.sh start
```

> `--labels ai-diag` 必须与 `.github/workflows/golden-regression.yml` 里的
> `runs-on: [self-hosted, ai-diag]` 一致，否则作业永远排队。

## 3. 准备运行环境（runner 机器上一次性）

```bash
python3.12 -m venv /opt/ai-diag-venv
/opt/ai-diag-venv/bin/pip install -r backend/requirements.txt

# 持久化模型缓存（CI 每次 checkout 都不该重下 1.5GB）
export HF_HOME=/opt/hf-cache
/opt/ai-diag-venv/bin/python -c "
from app.services.knowledge.embedding import get_embedder
print(get_embedder().dimension)
"   # 需在 backend/ 目录执行，期望 1024

# 依赖：pg / milvus / minio（compose 只起这三个即可）
cd deploy && docker compose up -d postgres redis milvus minio

# 若 workflow 保持 EMBEDDING_PROVIDER=api：另起一个 BGE HTTP 服务（bge-large-zh-v1.5，1024 维），
# 把地址填进 vars.EMBEDDING_API_URL；否则把 workflow 的 provider 改成 local 并预热模型缓存
```

把以下变量写进仓库 **Settings → Secrets and variables → Actions → Variables**：

Variables（`vars.*`，workflow 里就是这么取的）：

| 变量 | 值 | 说明 |
| --- | --- | --- |
| `GOLDEN_RUNNER_READY` | `true` | 设了才会在 push 时跑；否则 job 级 `if` 直接跳过 |
| `MILVUS_HOST` / `MILVUS_PORT` | `127.0.0.1` / `19530` | 默认值同上，跨机时改 |
| `MILVUS_COLLECTION` | `knowledge_chunks_v3` | 别用 v2 |
| `EMBEDDING_API_URL` | 例如 `http://127.0.0.1:8080` | ⚠️ workflow 里 `EMBEDDING_PROVIDER=api`，指向自托管 BGE HTTP 服务；若想让 runner 直接用本地模型，需把 workflow 改成 `local` |
| `MINIO_ENDPOINT` / `MINIO_BUCKET` | `127.0.0.1:9000` / `diagnostic-logs` | 回归要读产物时用 |

Secrets：`DEEPSEEK_API_KEY`（workflow 里名就是 `secrets.DEEPSEEK_API_KEY`）。

> 数据库连接不在 workflow 的 env 里：回归默认用 `DATABASE_URL` 环境变量（未设则落在
> `tests/conftest.py` 的内存 SQLite）。自托管 runner 上建议在机器级环境变量里固定
> `DATABASE_URL`，指向装有真实知识库的那套 Postgres。

## 4. 启用与验证

```bash
# 1) 设变量后，push 任意提交，或在 Actions 页面手动 dispatch golden-regression
# 2) 本地等价命令（runner 上就是这样跑的）
cd backend
DATABASE_URL=$GOLDEN_DATABASE_URL MILVUS_ENABLED=true MILVUS_COLLECTION=knowledge_chunks_v3 \
EMBEDDING_PROVIDER=local EMBEDDING_LOAD_TIMEOUT=1800 RERANKER_ENABLED=false \
pytest tests/regression -m golden -q
```

期望：`1 passed`，并生成 `backend/reports/golden_report.json`
（recall@5 ≥ `REGRESSION_RECALL_AT_5`、MRR ≥ `REGRESSION_MRR`，默认 0.85 / 0.70）。

## 5. 门禁规则（不可绕过）

- 任一项低于门槛或**单次下降 >2pp** → 阻断合并
- 只允许**改代码**或把样本标 `superseded`，**不允许下调阈值**
- 报告中每条失败都要带「期望 doc/section」与「实际 top5」，便于判断是检索退化还是样本写错

## 6. 排障

| 现象 | 原因 | 处理 |
| --- | --- | --- |
| job 一直 `skipped` | `GOLDEN_RUNNER_READY` 未设或不为 `true` | 在 Variables 里设为 `true` |
| job 一直 `queued` | runner 没有 `ai-diag` 标签 / 未启动 | `./svc.sh status`；核对 `--labels` |
| `Milvus 不可用` | runner 连不上 Milvus | 检查 `GOLDEN_MILVUS_HOST`、防火墙、容器端口 |
| 每次跑都重新下载模型 | `HF_HOME` 未持久化 | 设成固定目录并保证写权限 |
| 结果比本地差很多 | runner 的集合是旧的（v2/条数不符） | 在 runner 上重跑 `run_reindex`，确认 `292` 块量级 |
