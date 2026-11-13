# 真实环境验证报告 — 四项缺口安装与实机验证

- **日期**：2026-11-12
- **执行**：Agent Team（Lead + 4 名验证成员：pdf-reportlab / minio-storage / milvus-vector / bge-embedding）
- **验证对象**：上一轮代码评审遗留的四项「环境/实机验证缺口」
- **单报告**：[01-PDF](verification/01-pdf-reportlab.md) · [02-MinIO](verification/02-minio.md) · [03-Milvus](verification/03-milvus.md) · [04-BGE](verification/04-bge.md)
- **结论**：**四项全部安装完成并实机验证通过**（PDF、MinIO、Milvus、BGE），过程中额外发现并修复 3 个部署级缺陷、1 个 P1 业务 bug（详见各节）。
- **2026-11-12 晚补充（§7 治理轮）**：原 §7 的 8 项遗留问题已全部治理——6 项代码/配置级修复并重建复验、1 项为人工提交操作、1 项 Docker 本地 BGE 方案落地（覆盖文件 + 文档）；治理后全量回归 **489 passed / 18 skipped / 0 failed**，`docker compose ps` 中 backend / milvus / minio / postgres / redis 全部 healthy，worker 不再误报 unhealthy。详见 §7。

---

## 0. 结论总览

| # | 缺口 | 需要安装/修复什么 | 实测结论 | 关键证据 |
|---|------|------------------|----------|----------|
| 1 | PDF 真实导出（reportlab） | `reportlab` 已写入 `backend/requirements.txt`；**Docker 部署必须重建镜像并重启容器**（旧镜像无依赖、无 `/pdf` 路由） | ✅ 部署端 `GET /reports/{id}/pdf` → **HTTP 200 / application/pdf / 3099 B / 1 页 / STSong-Light 中文** | 报告 01 |
| 2 | MinIO 实链路 | `minio` SDK + `minio` 服务（compose 已定义） + `MINIO_ENABLED=true`；`diagnostic-logs` bucket 需初始化 | ✅ SDK 直连、后端 LogStorage/ImageStorage、部署 API（上传→minio://→parse 下载→删除→对象清理）**PASS=49 / FAIL=0** | 报告 02 |
| 3 | Milvus 实链路 | **修复 compose**：v2.4.0 + 内嵌 etcd + local storage + curl healthcheck；**修复 pymilvus 依赖**：`setuptools==80.9.0`；**修复 VectorService 2 处代码 bug** | ✅ 服务 healthy、pymilvus 真实 insert/search、API `/vector/{health,embed,index,search}` 全绿（e2e PASS=26/FAIL=0，search 命中 score=0.378） | 报告 03 |
| 4 | BGE 本地模型 | `sentence-transformers`/`torch`（`requirements-ml.txt`）+ **模型下载（hf-mirror）** + 离线缓存部署 | ✅ 真实下载 13 文件/183 MiB、dim=512、语义相似度明显区分、`HF_HUB_OFFLINE=1` 可加载、**Milvus 联合检索 rank#1 score=0.7332** | 报告 04 |

**回归**：`backend` 全量 pytest **489 passed / 18 skipped / 0 failed**（基线 466 passed / 1 skipped；首轮验证 473/18，§7 治理轮新增 16 个单测）；`docker compose ps` 中 backend/milvus/minio/postgres/redis 均 healthy。

---

## 1. 验证环境总览

| 项目 | 值 |
|------|-----|
| 操作系统 | Windows 11 专业版 10.0.22631（PowerShell 7） |
| 项目 venv | `G:\ai-diagnostic-platform\.venv`，Python **3.12.13** |
| 关键依赖版本（实测） | reportlab **5.1.0**；minio **7.2.20**；pymilvus **2.5.4**；setuptools **80.9.0**（pymilvus 硬约束，见 §3.3）；sentence-transformers **5.7.0**；torch **2.13.0**；transformers **5.15.0**；pytest **8.3.3** |
| Docker | Docker **29.6.1** / Docker Compose **v5.3.0** |
| 部署容器（`deploy/docker-compose.yml`） | `ai-diagnostic-backend`（:8000 healthy）、`ai-diagnostic-frontend`（:80）、`ai-diagnostic-postgres`（healthy）、`ai-diagnostic-redis`（healthy）、`ai-diagnostic-milvus`（**v2.4.0** healthy）、`ai-diagnostic-minio`（固定 RELEASE tag，healthy）、prometheus/grafana；`ai-diagnostic-worker`（已禁 healthcheck，§7-1） |
| 网络约束 | pip 走清华源（可用）；**huggingface.co 不可达 → 用 `hf-mirror.com`**；**Docker Hub 直连不可达** → daemon 镜像站（`docker.1ms.run` / `docker.xuanyuan.me`），本次拉取 milvus v2.5.4 均失败（429/403），故使用本地已有 v2.4.0 |
| 服务地址 | 后端 API `http://localhost:8000`；MinIO S3 `http://localhost:9000` / Console `http://localhost:9001`；Milvus gRPC `localhost:19530` / healthz `http://localhost:9091/healthz` |

---

## 2. PDF 真实导出（reportlab）

### 2.1 缺口与真实根因

`GET /api/v1/reports/{report_id}/pdf` 依赖 reportlab（`report_service.py::export_pdf`），缺失时抛 `ReportExportUnavailable` → API 501。本轮实测发现**仅把依赖写入 requirements.txt 不够**：

1. 运行中的容器仍是**旧镜像**：既没装 reportlab，也没有 `/pdf` 路由（旧 OpenAPI 中不存在该 path）；
2. 必须 `docker compose build` 重建镜像 **并且重启容器**，接口才可用。

### 2.2 安装 / 验证步骤（可复制）

```powershell
# ① 本地 venv（requirements.txt 已固定 reportlab==5.1.0）
G:\ai-diagnostic-platform\.venv\Scripts\python.exe -m pip install "reportlab==5.1.0"
cd backend
G:\ai-diagnostic-platform\.venv\Scripts\python.exe -m pytest tests/unit/services/test_report_pdf.py -v
# => 1 passed, 1 skipped（skip 是「reportlab 缺失应回退」用例，已装依赖故按设计跳过；真实导出 PASS）

# ② Docker 部署镜像重建（backend/worker 共用 Dockerfile）
cd deploy
docker compose build backend worker
docker compose up -d --no-deps backend worker      # 关键：旧容器仍跑旧镜像，必须重启

# ③ 镜像/容器内依赖确认
docker run --rm --entrypoint python deploy-backend:latest -c "import reportlab; print(reportlab.Version)"
# => 5.1.0
docker exec ai-diagnostic-backend python -c "import reportlab; print(reportlab.Version)"

# ④ 部署端到端（真实 HTTP：upload → parse → analyses/run → reports → PDF）
cd ..\backend
G:\ai-diagnostic-platform\.venv\Scripts\python.exe scripts\verify\pdf_export_e2e.py
```

### 2.3 实测结果

- `deploy-backend:latest` / `deploy-worker:latest` 镜像内 reportlab = **5.1.0**；
- 部署端全链路 17/17 项校验通过：`POST /logs/upload`(log_id=3) → `POST /logs/3/parse`(8 events) → `POST /analyses/run`(200, completed, mock LLM) → `POST /reports/3`(report_id=1) → **`GET /reports/1/pdf` = HTTP 200**，`Content-Type: application/pdf`，`%PDF-1.3`，**3099 B / 1 页**，`Content-Disposition: attachment; filename="report_1.pdf"`；字体资源含 `['/F2','/STSong-Light','/Type0']`（CID 字体生效），pypdf 提取中文 **148 字符**；二次运行 3095 B 同样通过；
- 新增 API 级回归测试 `tests/integration/api/test_report_pdf_api.py`：默认 2 skipped，`RUN_REAL_PDF_API=1` 时 2 passed。

### 2.4 注意点

- 中文回退风险：`STSong-Light` 注册失败会静默回退 Helvetica（中文不可读），验证须同时断言「HTTP 200 + 字体资源出现 STSong」。
- `reportlab` 已固定为 `==5.1.0`（§7-3 治理），构建可复现。

---

## 3. MinIO 真实对象存储链路

### 3.1 服务与配置

compose 中 minio 服务（`deploy/docker-compose.yml`）已定义：S3 API `9000`、Console `9001`，默认账号 `minioadmin/minioadmin`；后端容器环境 `MINIO_ENABLED=true`、`MINIO_ENDPOINT=minio:9000`、`MINIO_BUCKET=diagnostic-logs`、`MINIO_SECURE=false`；知识库图片用 `MINIO_KNOWLEDGE_BUCKET=knowledge-images`。

### 3.2 安装 / 启动 / 验证步骤

```powershell
# ① SDK（已声明在 requirements.txt：minio>=7.2.0）
G:\ai-diagnostic-platform\.venv\Scripts\python.exe -m pip install "minio>=7.2.0"

# ② 启动服务（compose 中已定义；本次环境容器已运行）
cd deploy; docker compose up -d minio

# ③ 健康检查 + bucket 初始化（首次部署时 diagnostic-logs 不会自动创建！）
curl.exe -s -o NUL -w "%{http_code}`n" http://localhost:9000/minio/health/live   # => 200
# 由脚本自动 make_bucket：
cd ..\backend
G:\ai-diagnostic-platform\.venv\Scripts\python.exe scripts\verify\minio_storage_e2e.py --skip-api   # SDK/存储类直连
G:\ai-diagnostic-platform\.venv\Scripts\python.exe scripts\verify\minio_storage_e2e.py             # 含部署 API 端到端
```

### 3.3 实测结果

- **host SDK 直连**：`diagnostic-logs` 原不存在 → `make_bucket` 创建成功；put/stat/get/预签名 GET(200)/remove(→NoSuchKey) 全通，对象 4368 B、ETag=md5、sha256 前后一致；
- **存储类直连**：`LogStorage.save()` → `minio://diagnostic-logs/logs/...`，`materialize()` 下载逐字节一致，`delete()` 后对象消失；`KnowledgeImageStorage` 在 `knowledge-images` 写入/读取/预签名/删除全通；
- **部署 API 端到端**（新镜像重启后）：`POST /logs/upload` → `file_path=minio://diagnostic-logs/logs/…`（499 B，SDK 核对 ETag 一致）→ `POST /logs/{id}/parse` 200 / completed / event_count=6（**证明 materialize 从 MinIO 下载可用**）→ `DELETE /logs/{id}` **204**、对象 NoSuchKey；知识库图片 POST 201 → GET 字节一致 → 预签名 200；
- 汇总：`minio_storage_e2e.py` 完整部署 API 段 **PASS=49 / FAIL=0**；
- 集成测试 `tests/integration/services/test_minio_real.py`：默认 5 skipped，`RUN_REAL_MINIO=1` → 5 passed；本地回退单测保持 2 passed。

### 3.4 验证中发现并修复的 P1 bug（已回归）

真实链路验证发现：对**已解析**日志执行 `DELETE /api/v1/logs/{id}` 返回 **500**（`log_events.log_id` 外键无 CASCADE，`delete_log` 未先删事件；且 MinIO 对象在 DB commit 前被删 → 记录残留 + `file_path` 悬空、日志无法再解析）。

修复（`log_service.py::delete_log`，最小改动、不改 schema/迁移）：

1. 同一 DB 事务内先删 `log_events` → 再删 `logs` → `commit()`；
2. **DB 成功后**才删 MinIO 对象/本地文件，删除失败仅告警不阻断（避免「对象已删、DB 未删」的数据不一致）。

回归：新增 `tests/unit/services/test_log_delete_events.py` 7 tests 全过；修复后部署复验 **PASS=49 / FAIL=0**，历史残留 log id=2 与验证产生的图片 DB 行已清理。后续可选：给 `log_events.log_id` 加 `ondelete="CASCADE"` + alembic 迁移。

### 3.5 生产注意

- 必须修改默认口令 `minioadmin/minioadmin`；生产建议 `MINIO_SECURE=true` + TLS；
- `diagnostic-logs` bucket **已由 `LogStorage` 自动创建**（§7-2 治理：不存在→`make_bucket`，并发幂等兜底）；若后端运行用户无 `s3:CreateBucket` 权限，仍需由管理员预先创建（或授予权限），此时上传失败会回退本地并打 warning；
- `materialize()` 下载到系统临时目录且未清理、无对象生命周期策略，建议后续加 TTL/清理任务。

---

## 4. Milvus 真实向量链路

### 4.1 四个根因（按发现顺序）

| # | 根因 | 现象 | 修复 |
|---|------|------|------|
| A | compose 只配了 `ETCD_*` 调优项，**缺内嵌 etcd 开关** | 容器去连不存在的 `localhost:2379`，一直 unhealthy | 加 `ETCD_USE_EMBED=true / ETCD_DATA_DIR / ETCD_CONFIG_PATH / COMMON_STORAGETYPE=local` |
| B | healthcheck 用 `wget`，镜像内只有 `curl` | 即使服务正常 docker health 也永远失败（假阴性） | healthcheck 改 `curl -sf http://localhost:9091/healthz` |
| C | pymilvus 2.5.4 仍 `import pkg_resources`，setuptools≥81 已移除该模块 | `ModuleNotFoundError: No module named 'pkg_resources'`；`vector_service.py` 的 `except ImportError` 使 Milvus 永远走关键词回退 | `requirements.txt` 固定 **`setuptools==80.9.0`**，重建镜像 |
| D | `VectorService` 两处代码 bug | ① 先 `load()` 后 `create_index()` → `code=700 index not found`、单例永久不可用；② `Hit.get("doc_id", 0)` 在 pymilvus 2.5.4 抛 `TypeError` 被吞 → search 永远返回 `[]` | 改为「建/取 collection → 幂等补建 IVF_FLAT/IP 索引 → load」；`entity.get("doc_id") or 0` |

> 实测补充：v2.3.12 补齐同样内嵌 etcd env 也能启动（根因是配置缺失而非版本不支持）；本次仍升级 **v2.4.0**（贴近 pymilvus 2.5.4）。v2.5.4 镜像因 Docker Hub/镜像站受限未拉取，**pymilvus 2.5.4 ↔ server v2.4.0 兼容性已全链路实测通过**（create/index/load/insert/flush/search/delete/query/drop）。

### 4.2 compose 关键改动（`deploy/docker-compose.yml`）

```yaml
milvus:
  image: milvusdb/milvus:v2.4.0          # 原 v2.3.12
  command: ["milvus", "run", "standalone"]
  ports: ["19530:19530", "9091:9091"]
  environment:
    ETCD_USE_EMBED: "true"               # 原缺失 → 连不存在的 localhost:2379
    ETCD_DATA_DIR: /var/lib/milvus/etcd
    ETCD_CONFIG_PATH: /milvus/configs/advanced/etcd.yaml
    COMMON_STORAGETYPE: local            # 本地存储，不依赖 MinIO/S3
  volumes:
    - milvus_data:/var/lib/milvus
  healthcheck:
    test: ["CMD-SHELL", "curl -sf http://localhost:9091/healthz || exit 1"]  # 原 wget 镜像内不存在
# 同步修复 worker：MILVUS_DIM 1536 → "${MILVUS_DIM:-512}"，补 EMBEDDING_DIM/EMBEDDING_PROVIDER
```

数据卷：旧 `deploy_milvus_data`（2.3.12 元数据）不兼容，无真实业务数据，已删除重建。

### 4.3 安装 / 启动 / 验证步骤

```powershell
# ① 服务（compose 改动后）
cd deploy
docker compose config -q
docker rm -f ai-diagnostic-milvus; docker volume rm deploy_milvus_data   # 仅首次切换版本时；数据无价值需确认
docker compose up -d milvus
curl.exe -s -o NUL -w "%{http_code}`n" http://localhost:9091/healthz    # => 200
docker compose ps milvus                                                # => healthy

# ② pymilvus 依赖（关键坑：setuptools 必须 <81）
cd ..\backend
G:\ai-diagnostic-platform\.venv\Scripts\python.exe -m pip install "pymilvus==2.5.4" "setuptools==80.9.0"
# 部署镜像：requirements.txt 已加 setuptools==80.9.0，需重建并重启 backend/worker
cd ..\deploy; docker compose build backend worker; docker compose up -d --no-deps backend worker

# ③ pymilvus 真连 + API 端到端（可重复脚本）
cd ..\backend
G:\ai-diagnostic-platform\.venv\Scripts\python.exe scripts\verify\milvus_e2e.py
# 或只测直连：... scripts\verify\milvus_e2e.py --skip-api

# ④ 真实集成测试（默认 skip）
$env:RUN_REAL_MILVUS="1"; G:\ai-diagnostic-platform\.venv\Scripts\python.exe -m pytest tests/integration/services/test_milvus_real.py -v; Remove-Item Env:\RUN_REAL_MILVUS
```

### 4.4 实测结果

- 服务：`ai-diagnostic-milvus` = `milvusdb/milvus:v2.4.0`，**Up (healthy)**，启动约 12s；healthz 200 / gRPC 19530 可连；
- pymilvus 2.5.4 真连：临时 collection insert 5 条 → search 自身 score=1.0；delete/query 正常；
- VectorService（venv，hash embedding dim=512）：`index_document(987654)` chunks=1 → `search("USB 超时")` 命中 `(id=987654, score=0.4376)`；`delete_document` 后 query 为空；重复初始化 available=True（幂等）；
- **API 端到端（真实 backend 容器）**：`/vector/health` → `milvus_available=true`、collection `knowledge_docs`(dim 512)；`/vector/embed` → dimension=512、norm=1.0；`/vector/index` → chunks_indexed=1；`/vector/search`(use_hybrid=false) → `strategy=vector_only`、命中 id=987654、score=0.3780；`use_hybrid=true` → `strategy=hybrid`、融合 keyword+vector 2 条；测试向量已清理；
- 脚本 `milvus_e2e.py` 完整模式 **PASS=26 / FAIL=0**；`RUN_REAL_MILVUS=1` 集成测试 **3 passed**。

### 4.5 生产注意

- Milvus 是独立服务，`COMMON_STORAGETYPE=local` 仅适合单机/开发；生产多副本仍需 etcd + 对象存储（或 Zilliz Cloud）；
- `MILVUS_DIM` 必须与 embedding 维度一致（默认 512，对应 BGE-small-zh / 哈希兜底）；换 embedding 模型需重建 collection；
- `/vector/health` 的 `embedding_provider` 已返回真实 provider 名（`HashingEmbedder` / `BGEEmbedder` / `APIEmbedder`，§7-6 治理）。

---

## 5. BGE 本地模型真实下载与语义嵌入

### 5.1 安装 / 下载步骤（网络受限环境关键）

```powershell
# ① 本地 ML 依赖（Docker 镜像默认不装 torch/ST，见 backend/Dockerfile 注释）
G:\ai-diagnostic-platform\.venv\Scripts\python.exe -m pip install -r backend\requirements-ml.txt
#   requirements-ml.txt: sentence-transformers>=3.0.0（含 torch，约 2GB+）

# ② 模型下载 —— huggingface.co 被墙，用 hf-mirror
$env:HF_ENDPOINT = "https://hf-mirror.com"
G:\ai-diagnostic-platform\.venv\Scripts\python.exe -c "from huggingface_hub import snapshot_download; print(snapshot_download('BAAI/bge-small-zh-v1.5'))"
# => C:\Users\EDY\.cache\huggingface\hub\models--BAAI--bge-small-zh-v1.5\snapshots\<commit>
# 13 个文件、snapshot 183.34 MiB（safetensors + bin 双格式各 ~91.4 MiB）、repo 磁盘占用 274.73 MiB
# 实测下载耗时：481s~618s（hf-mirror，约 200KB/s；Win 符号链接降级为复制）

# ③ 复现验证脚本
cd backend
G:\ai-diagnostic-platform\.venv\Scripts\python.exe scripts\verify\bge_embedding_e2e.py
```

### 5.2 实测结果

- 模型：commit `7999e1d3359715c523056ef9478215996d62a620`；13 文件、snapshot 183.34 MiB；`safetensors`/`pytorch_model.bin` sha256 已记录（见报告 04）；重复 snapshot 校验 1.56s（已缓存）；
- 加载：`BGEEmbedder` 按 repo id 加载成功，**dimension=512**、health_check=True；进程内 import sentence-transformers(含 torch) 冷启动 138.8s（Windows Defender 首扫 torch DLL），同进程二次加载 12.3-15.4s；
- 语义质量（归一化向量，norm≈1.0，最大偏差 7.5e-8；batch 与单条 max|diff|=1.04e-7）：

  | 查询 | 相关句相似度 | 不相关句相似度 | 差值 |
  |------|-------------|----------------|------|
  | USB 设备超时无响应 | 0.7881 | 0.5461 | +0.2419 |
  | 内核 panic | 0.8108 | 0.5195 | +0.2913 |
  | 网络丢包 | 0.8713 | 0.5433 | +0.3280 |
  | 内存 OOM | 0.7219 | 0.4418 | +0.2802 |

- 性能：CPU 单条 ~137.9ms（首次含 warmup 326.3ms），batch 8 条 69.7ms（8.7ms/条）；
- **离线可复现**：子进程 `HF_HUB_OFFLINE=1` + 故意无效 `HF_ENDPOINT` 仍按 repo id 加载成功（dim=512、norm=1.0），证明模型真落盘、可离线部署；
- **与 Milvus 联合检索**（真实 Milvus v2.4.0 + pymilvus 2.5.4）：`VectorService.available=True`，`index_document(9999)` chunks=1 → `search("USB 超时")` **rank#1 = doc_id 9999、score 0.7332** → `delete_document(9999)` 后 query 为空。

### 5.3 部署注意（Docker）

- 后端镜像默认**不含** torch/sentence-transformers（`backend/Dockerfile` 注释、`requirements-ml.txt` 可选），容器内 `EMBEDDING_PROVIDER=local` 会静默回退哈希嵌入（dim 512，非语义）——这是默认精简镜像的行为；**已提供一键覆盖方案** [deploy/docker-compose.bge.yml](../../deploy/docker-compose.bge.yml)（§7-8）；
- 若需容器内本地 BGE：`pip install -r requirements-ml.txt` 重建镜像（镜像 +2GB+），并把 HF 缓存目录挂载进容器，或设 `HF_ENDPOINT=https://hf-mirror.com` 在线拉取；
- 离线部署：把 `~/.cache/huggingface/hub/models--BAAI--bge-small-zh-v1.5` 复制到镜像/挂载卷，设 `HF_HUB_OFFLINE=1`；首次加载慢时把 `EMBEDDING_LOAD_TIMEOUT`（默认 30s）调大（如 120s）；
- **缓存命中 ≠ 不联网**：transformers 对 repo id 会做 `find_adapter_config_file()` 元数据探测，hf 不可达时会挂起（实测 pytest 卡 7+ 分钟）；受限网络必须同时设 `HF_HUB_OFFLINE=1` + `TRANSFORMERS_OFFLINE=1`（或保持 `HF_ENDPOINT` 可达），验证脚本与集成测试已内置该保护；
- `BGEEmbedder` 与 `ETCD_*` 无关；`EMBEDDING_PROVIDER=auto` 顺序为 BGE → API → hash。

---

## 6. 一键复现 / 回归命令

```powershell
$PY = "G:\ai-diagnostic-platform\.venv\Scripts\python.exe"
cd G:\ai-diagnostic-platform\backend

# 四项真实验证脚本（均可重复运行，打印证据）
& $PY scripts\verify\pdf_export_e2e.py       # PDF（需 backend 容器运行且镜像含 reportlab）
& $PY scripts\verify\minio_storage_e2e.py    # MinIO（SDK + 部署 API）
& $PY scripts\verify\milvus_e2e.py           # Milvus（pymilvus 直连 + API）
& $PY scripts\verify\bge_embedding_e2e.py    # BGE（下载/加载/语义/离线/联合检索）

# 真实集成测试（默认 skip，不污染日常回归）
$env:RUN_REAL_PDF_API="1"; $env:RUN_REAL_MINIO="1"; $env:RUN_REAL_MILVUS="1"; $env:RUN_REAL_BGE="1"
& $PY -m pytest tests/integration/api/test_report_pdf_api.py tests/integration/services/test_minio_real.py tests/integration/services/test_milvus_real.py tests/integration/services/test_bge_real.py -v
Remove-Item Env:RUN_REAL_PDF_API,Env:RUN_REAL_MINIO,Env:RUN_REAL_MILVUS,Env:RUN_REAL_BGE

# 全量回归 + 部署状态
& $PY -m pytest -q
cd ..\deploy; docker compose ps
```

**本轮全量回归结果**：**489 passed, 18 skipped, 1 warning**（0 failed/error；跳过均为默认 skip 的真实环境用例与 reportlab 回退用例）。§7 治理轮新增 16 个单测（bucket 自动创建 6 + embedding 超时/重试 5 + provider 名 5），全量重复运行稳定。

**§7 治理轮验证命令（可选）**：

```powershell
docker ps --format "table {{.Names}}\t{{.Status}}"        # worker 不再 unhealthy
curl.exe -s http://localhost:8000/api/v1/vector/health    # embedding_provider 应为 HashingEmbedder / BGEEmbedder
cd deploy; docker compose config -q                       # 基础配置合法
$env:HF_CACHE_DIR="$env:USERPROFILE\.cache\huggingface"
docker compose -f docker-compose.yml -f docker-compose.bge.yml config -q   # 本地 BGE 覆盖配置合法
```

---

## 7. 遗留问题与建议（✅ 2026-11-12 晚已全部治理）

> 本节原有 8 项遗留，治理轮全部处理完毕：6 项完成代码/配置修复并**重建镜像 + 重启容器后实机复验**，
> 1 项为人工提交操作（见 #5），1 项 Docker 本地 BGE 方案已落地（见 #8）。
> 治理后全量 pytest **489 passed / 18 skipped / 0 failed**；`docker compose ps`：backend / milvus /
> minio / postgres / redis 全 healthy，worker 不再误报 unhealthy。

| # | 原遗留问题 | 治理结果 | 复验证据 |
|---|-----------|----------|----------|
| 1 | worker 容器 unhealthy（镜像 HEALTHCHECK 是 HTTP `/health`，不适用 keep-alive 进程） | ✅ **修复**：compose worker 服务设置 `healthcheck.disable: true`（backend 保持原 HTTP healthcheck） | `docker inspect ai-diagnostic-worker` → `{"Test":["NONE"]}`；`docker compose ps` → `Up`（无 unhealthy） |
| 2 | 首次部署 `diagnostic-logs` bucket 不自动创建，上传静默回退本地 | ✅ **修复**：`LogStorage._create_client()` 自动 ensure bucket（不存在→`make_bucket`；并发 `BucketAlreadyOwnedByYou/BucketAlreadyExists` 幂等兜底；失败 warning + 回退本地，保持既有语义）；`MINIO_ENABLED=false` 仍不连接 | 容器内真实 MinIO 验证：临时桶 `autocreate-verify-1fa11bce` 由 `LogStorage()` 自动创建（`remote_available=True`）后清理成功；`diagnostic-logs`/`knowledge-images` 对象数 2/16 保留；+6 单测 |
| 3 | `reportlab>=4.0.0` 未锁版本；pymilvus 与 setuptools 绑定未记录 | ✅ **修复**：`requirements.txt` 固定 `reportlab==5.1.0`；注释记录 `pymilvus==2.5.4` 必须搭配 `setuptools==80.9.0`（升级前需确认其已移除 pkg_resources 依赖） | 新镜像容器内：reportlab **5.1.0** / pymilvus **2.5.4** / setuptools **80.9.0** 均 import 成功 |
| 4 | Docker Hub 不可达、镜像站不稳定，镜像版本不可复现 | ✅ **治理**：移除最后一个浮动 tag——minio `:latest` → `:RELEASE.2025-09-07T16-13-09Z`（重建后 healthy、数据保留）；compose 头部新增「镜像版本策略」（digest 固定命令 + 已验证 minio digest + 内网 registry / save-load 离线方案）；`deploy/README.md` 新增「镜像版本与离线部署」章节 | `docker compose ps` minio 显示固定 tag；对象数 2/16 未丢 |
| 5 | 工作区未提交改动需人工审阅 | ⚠️ **部分人工项**：上一轮验证改动已由用户提交（HEAD `e0b1000`）；**本轮 §7 治理改动仍在工作区未提交**，需人工审阅后提交（本 Agent 未执行 git commit） | `git status` |
| 6 | `/api/v1/vector/health` 的 `embedding_provider` 返回包装类名 `EmbeddingService` | ✅ **修复**：路由改用 `get_embedder().provider_name` | 重建后真实 API：`{"milvus_available":true,"embedding_provider":"HashingEmbedder",...}`（启用 BGE 镜像/配置时为 `BGEEmbedder`） |
| 7 | **P2**：`VectorService._EMBEDDING_LOAD_TIMEOUT=10.0` 硬编码 + 超时永久 latch（BGE 冷加载 15.35s>10s 首次超时后进程内永久回退关键词） | ✅ **修复**：删除硬编码常量，改读 `settings.EMBEDDING_LOAD_TIMEOUT`（默认 30s，BGE 场景可 env 调 120）；删除永久 latch，改为线程安全共享加载线程——超时返回 False 但**下次调用可继续等待/读取回填**，线程失败允许重试（attempts 计数），并发调用共享同一加载线程 | +10 单测（超时回填/失败重试/settings 生效/4 并发单线程/常量移除）；全量 489 passed |
| 8 | Docker 后端镜像默认无 torch/ST，容器内本地 BGE 静默回退 hash | ✅ **方案落地**：新增 `deploy/docker-compose.bge.yml` 覆盖文件——Dockerfile `INSTALL_ML=true` 构建（`requirements-ml.txt`）+ `EMBEDDING_PROVIDER=local` + `EMBEDDING_LOAD_TIMEOUT=120` + `HF_HUB_OFFLINE=1/TRANSFORMERS_OFFLINE=1` + 只读挂载 `${HF_CACHE_DIR}`；默认 compose 不受影响 | 合并配置 `config -q` 通过；断言 `INSTALL_ML=true`、provider=local、timeout=120、offline=1/1、bind 挂载 `C:\Users\EDY\.cache\huggingface → /root/.cache/huggingface:ro`、负向未设置 HF_CACHE_DIR 时报错。**ML 镜像（+2GB）未在本机构建**（按任务约束），运行期验收清单见 [04-bge.md §5.3](verification/04-bge.md) |

### 7.1 §7 治理轮实现说明（供审阅）

- **worker health 语义**：worker 当前是 keep-alive 占位进程（Celery 待接入），不提供 HTTP 服务；与其伪造
  healthcheck 不如显式 disable，后续接入 Celery 后应改为真实存活探针（如 `celery inspect ping`）。
- **MinIO 自动建桶的资源开销**：每次 `LogStorage()` 实例化会做一次 `bucket_exists` 网络调用（分钟级 API 请求
  可接受）；若高频创建实例，可后续加进程级缓存（02-minio.md §6 P3）。
- **embedding 加载线程**：`_ensure_embedding()` 只保证"本次请求不无限阻塞"，不保证首次请求一定用上语义嵌入；
  容器内 BGE 冷启动建议用覆盖文件预热（`docker compose ... exec backend python -c "get_embedder()"`），
  或把 `EMBEDDING_LOAD_TIMEOUT` 调到 120。
- **BGE 覆盖文件**：采用 long-syntax bind 规避 Windows 盘符冒号解析问题；`HF_CACHE_DIR` 必填（不设直接报错），
  防止误挂空目录导致容器内重新联网下载。
- **未纳入本轮治理**：§4.5 的 `knowledge_docs.num_entities` 统计延迟（Milvus 语义）、v2.5.4 镜像拉取
  （网络受限）、聊天链路 project 过滤（非环境缺口）均维持原状。

---

## 8. 本次改动文件清单

**新增（验证资产）**

- `backend/scripts/verify/{pdf_export_e2e,minio_storage_e2e,milvus_e2e,bge_embedding_e2e}.py`
- `backend/tests/integration/api/test_report_pdf_api.py`
- `backend/tests/integration/services/{test_minio_real,test_milvus_real,test_bge_real}.py`
- `backend/tests/unit/services/test_log_delete_events.py`
- `docs/20-Audit/verification/{01-pdf-reportlab,02-minio,03-milvus,04-bge}.md`
- 本文件 `docs/20-Audit/Environment-Real-Verification.md`

**修改（依赖/部署/缺陷修复）**

- `backend/requirements.txt`：`setuptools==80.9.0`（pymilvus pkg_resources 约束）+ `reportlab==5.1.0`（固定版本）+ `minio>=7.2.0`
- `deploy/docker-compose.yml`：Milvus v2.4.0 内嵌 etcd + local storage、healthcheck 改 curl；worker `MILVUS_DIM` 对齐 512、补 `EMBEDDING_*`
- `backend/app/services/knowledge/vector_service.py`：索引/load 顺序修复、`Hit.get` 兼容修复
- `backend/app/services/diagnostics/log_service.py`：`delete_log()` 事务顺序与对象删除一致性修复

### 8.1 §7 治理轮新增/修改（2026-11-12 晚）

**新增文件**

- `deploy/docker-compose.bge.yml`：Docker 内本地 BGE 覆盖文件（`INSTALL_ML=true`、`local` 嵌入、120s 超时、`HF_HUB_OFFLINE/TRANSFORMERS_OFFLINE=1`、只读挂载 `${HF_CACHE_DIR}`）
- `backend/tests/unit/services/test_log_storage_bucket.py`（6 tests，默认无外部依赖）
- `backend/tests/unit/services/test_vector_service_embedding_load.py`（5 tests）
- `backend/tests/unit/services/test_vector_health_provider.py`（5 tests）

**修改文件**

- `backend/Dockerfile`：新增 `ARG INSTALL_ML=false`（true 时安装 `requirements-ml.txt`），COPY requirements-ml.txt
- `deploy/docker-compose.yml`：worker `healthcheck.disable: true`；minio 固定 `RELEASE.2025-09-07T16-13-09Z`；backend/worker `build.args.INSTALL_ML`；backend 透传 `EMBEDDING_LOAD_TIMEOUT` / `HF_ENDPOINT` / `HF_HUB_OFFLINE` / `TRANSFORMERS_OFFLINE`；头部「镜像版本策略」
- `backend/requirements.txt`：`reportlab==5.1.0`；pymilvus↔setuptools 升级约束注释
- `backend/app/services/diagnostics/log_storage.py`：`_ensure_bucket()` 首次连接自动建桶（并发幂等、失败回退本地）
- `backend/app/services/knowledge/vector_service.py`：embedding 加载超时改读 `settings.EMBEDDING_LOAD_TIMEOUT`，去除永久 latch（可续等/回填/失败重试、并发共享加载线程）
- `backend/app/api/knowledge/vector.py`：`embedding_provider` 改为 `get_embedder().provider_name`
- `deploy/README.md`：服务列表、验证命令、本地 BGE 部署、镜像版本与离线部署
- `backend/.env.example`：补充 HF 环境变量与 `EMBEDDING_LOAD_TIMEOUT` 说明（注：仓库 `.gitignore` 忽略 `.env.*`，该模板不入库）
- `docs/20-Audit/verification/{02-minio,03-milvus,04-bge}.md` 与 `Code-Review-RAG-LogAnalysis.md`：同步更新遗留项状态与证据
