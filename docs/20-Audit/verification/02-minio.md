# MinIO 真实对象存储链路验证

- **日期**：2026-11-12
- **执行**：Agent Team 成员 `minio-storage`
- **关联任务**：`task-2` — MinIO 真实对象存储链路验证（SDK 直连 + 后端 API 端到端）
- **状态**：SDK / 存储类真连 ✅；本地干跑 API ✅；部署 API 端到端 ✅ **PASS=49 FAIL=0**（已解析日志 DELETE 500 P1 已定位、修复（task-6）、重启后复验 204，`log_events`/`logs` 行清空、MinIO 对象删除，历史残留已清理）；新增默认 skip 集成测试 ✅；删除回归测试 7 passed ✅；回退单测/全量 pytest 无回归 ✅

## 1. 背景与结论

缺口背景：MinIO 已在 `deploy/docker-compose.yml` 中定义、后端容器也注入了
`MINIO_ENABLED=true`，但此前**从未有真实对象写入/读取证据**，只验证过
`MINIO_ENABLED=false` 的本地回退分支；`backend/app/services/diagnostics/log_storage.py`
是本次新增的日志对象存储抽象，`knowledge/image_storage.py` 的 MinIO 分支同样缺少真连证据。

本次完成：

| # | 验证项 | 结论 |
|---|--------|------|
| 1 | host 侧 S3 SDK 真连：bucket 检查/自动创建、put/stat/get/presign/remove | ✅ 28 项检查 27 PASS、1 SKIP（API 部分单独执行），对象 4368B，ETag 与 md5 一致，预签名 GET 200 |
| 2 | 部署网络路径（backend 容器内 → `minio:9000`） | ✅ 容器内按 compose env 真连：put/get/stat/remove 全通，ETag==md5 |
| 3 | `LogStorage` 类真连（save→`minio://` / materialize 下载 / delete） | ✅ 引用 `minio://diagnostic-logs/logs/793e...log`，size=216、ETag 一致、下载逐字节一致、删除后 NoSuchKey |
| 4 | `KnowledgeImageStorage` 类真连（save/get_bytes/presign_url/delete） | ✅ 对象写入 `knowledge-images`，size=112、ETag 一致、预签名 URL HTTP 200、删除后 NoSuchKey |
| 5 | 新代码 + 真实 MinIO 的 HTTP API 端到端（本地干跑预演） | ✅ upload→`minio://`（499B, etag=a3fa81d1）、SDK 核对一致、parse event_count=6、delete 后 NoSuchKey；图片 API 201→GET 字节一致→预签名 200；PASS=49 FAIL=0 |
| 6 | Docker 部署容器 API 端到端（修复后复验） | ✅ **PASS=49 FAIL=0**：日志 upload→`minio://`、SDK 核对、parse/materialize、**DELETE→204 + 对象删除 + `log_events`/`logs` 行清空**；图片链路全通过。修复前曾实测 FAIL=2（P1 DELETE 500，见 §4.6.2；已修复，见 §4.6.3） |
| 7 | 新增集成测试默认 skip（`RUN_REAL_MINIO=1` 门槛） | ✅ 默认 5 skipped；开启后 5 passed in 0.74s |
| 8 | 本地回退分支不回归（`tests/unit/services/test_log_storage.py`） | ✅ 2 passed |
| 9 | 全量 pytest 基线（backend） | ✅ 466 passed / 8 skipped（新增 7 个 skip 均为默认 skip 用例，原 466 passed / 1 skipped 基线无回归） |
| 10 | 可复现脚本 `backend/scripts/verify/minio_storage_e2e.py` | ✅ 可重复运行，打印 bucket/key/size/etag/HTTP 证据 |

> **关键发现（详见 §6）**：
> 1. MinIO 初始**只有 `knowledge-images` bucket，`diagnostic-logs` 不存在**；而 `LogStorage.save()`
>    既不自动创建 bucket，上传失败还会**静默回退本地路径**——“MinIO 看似启用，日志实际仍写本地
>    且不报错”。本次验证脚本会自动创建 bucket 后才通过；生产环境需要显式初始化 bucket
>    （或给 `LogStorage` 加 `make_bucket`）。
> 2. 部署实测发现**已解析日志 `DELETE /api/v1/logs/{id}` 返回 500**（`log_events` 外键无级联），
>    且 MinIO 对象在 DB commit 前被删除 → **对象已删、记录仍在、file_path 悬空**（P1）。
>    已修复（task-6：`delete_log` 先删 `log_events`、DB 成功后再删对象，不改 schema）并在
>    第三次重启后复验：**DELETE→204、events/logs 行清空、对象删除，PASS=49 FAIL=0**（§4.6.3）。

## 2. 服务、SDK 与配置

### 2.1 compose 中的 MinIO 服务

`deploy/docker-compose.yml:93-117` 已定义 MinIO（无需本次改动）：

```yaml
  # MinIO — 对象存储（日志文件 / 附件）
  # Web Console: http://localhost:9001
  minio:
    image: minio/minio:latest
    container_name: ai-diagnostic-minio
    restart: always
    command: server /data --console-address ":9001"
    environment:
      MINIO_ROOT_USER: minioadmin
      MINIO_ROOT_PASSWORD: minioadmin
    ports:
      - "9000:9000"   # S3 API
      - "9001:9001"   # Web Console
    volumes:
      - minio_data:/data
    healthcheck:
      test: ["CMD", "curl", "-sf", "http://localhost:9000/minio/health/live"]
```

启动方式（仓库根目录）：

```powershell
docker compose -f deploy/docker-compose.yml up -d minio
# 或随整套服务启动：
docker compose -f deploy/docker-compose.yml up -d
```

### 2.2 运行状态与版本（实测）

```text
container : ai-diagnostic-minio  status=running  health=healthy  image=minio/minio:latest
version   : minio version RELEASE.2025-09-07T16-13-09Z (commit-id=07c3a429bfed433e49018cb0f78a52145d4bedeb)
health    : GET http://localhost:9000/minio/health/live => 200
endpoints : S3 API http://localhost:9000 ；Console http://localhost:9001
```

### 2.3 Python SDK

| 项目 | 值 |
|------|-----|
| 依赖声明 | `backend/requirements.txt:16` → `minio>=7.2.0  # 知识库图片/日志对象存储（MinIO）`（该行原已存在，本次仅更新注释） |
| 项目 venv | `G:\ai-diagnostic-platform\.venv\Scripts\python.exe`，Python 3.12.13 |
| 已安装版本 | **minio 7.2.20**（另 requests 2.34.2 / httpx 0.27.2，用于 HTTP 校验） |
| 镜像内版本 | `deploy-backend:latest` 内 `minio 7.2.20`（`docker run --rm --entrypoint python ...` 实测） |
| 安装命令 | `pip install -r backend/requirements.txt`（或单独 `pip install "minio>=7.2.0"`） |

### 2.4 后端环境变量配置

`deploy/docker-compose.yml:193-199`（backend 与 worker 两处相同）：

```yaml
      # ── MinIO ──────────────────────────────────────
      MINIO_ENABLED: "true"
      MINIO_ENDPOINT: minio:9000          # 容器内网地址；host 侧验证用 localhost:9000
      MINIO_ACCESS_KEY: minioadmin
      MINIO_SECRET_KEY: minioadmin
      MINIO_BUCKET: diagnostic-logs
      MINIO_SECURE: "false"
```

配置项全表（`backend/app/core/config.py:54-66`，`backend/.env.example:57-63` 有前 6 项）：

| 环境变量 | 默认值 | compose 部署值 | 说明 |
|----------|--------|----------------|------|
| `MINIO_ENABLED` | `False` | `true` | 总开关；false 时走本地文件系统回退 |
| `MINIO_ENDPOINT` | `localhost:9000` | `minio:9000` | 不含 scheme；后端容器内必须用 compose 服务名 |
| `MINIO_ACCESS_KEY` | `minioadmin` | `minioadmin` | ⚠️ 默认口令，生产必须改 |
| `MINIO_SECRET_KEY` | `minioadmin` | `minioadmin` | ⚠️ 同上 |
| `MINIO_BUCKET` | `diagnostic-logs` | `diagnostic-logs` | 日志对象 bucket |
| `MINIO_SECURE` | `False` | `false` | 是否 HTTPS |
| `MINIO_KNOWLEDGE_BUCKET` | `knowledge-images` | **未显式注入**（用默认值） | 知识库图片 bucket，建议 compose 显式化 |
| `KNOWLEDGE_IMAGE_DIR` | `data/knowledge_images` | 未注入 | MinIO 关闭时图片本地目录 |
| `IMAGE_URL_TTL_SECONDS` | `3600` | 未注入 | `presign_url` 默认有效期 |
| `MAX_IMAGE_SIZE_MB` | `10` | 未注入 | 图片上传大小上限 |

### 2.5 bucket 现状（实测）

```text
验证前 list_buckets(): ['knowledge-images']          # diagnostic-logs 不存在
首次 ensure_bucket()：bucket diagnostic-logs exists=False (created just now)
第二次运行后：      buckets=['diagnostic-logs', 'knowledge-images']
```

## 3. 验证方法与门槛

### 3.1 可复现脚本

[`backend/scripts/verify/minio_storage_e2e.py`](../../../backend/scripts/verify/minio_storage_e2e.py)

```powershell
# 仓库根目录（host 侧直连 localhost:9000）
G:\ai-diagnostic-platform\.venv\Scripts\python.exe backend\scripts\verify\minio_storage_e2e.py

# 后端尚未重启/不可达时，仅做 SDK 与存储类直连：
G:\ai-diagnostic-platform\.venv\Scripts\python.exe backend\scripts\verify\minio_storage_e2e.py --skip-api

# 指定其他 API 根地址（如本地干跑的 uvicorn 127.0.0.1:18080）：
G:\ai-diagnostic-platform\.venv\Scripts\python.exe backend\scripts\verify\minio_storage_e2e.py --api-base http://127.0.0.1:18080
```

脚本行为：自动 ensure `diagnostic-logs` / `knowledge-images` 两个 bucket → SDK 直连
put/stat/get/presign/remove → 后端 `LogStorage`、`KnowledgeImageStorage` 类真连 →
（可选）HTTP API 端到端；退出码 0=全部通过、1=存在 FAIL、2=MinIO 不可达。
所有测试对象默认清理（`--keep` 可保留）。

幂等/降级已验证：

```text
# 连续第二次运行：bucket 已存在，仍 PASS
SUMMARY: PASS=27 FAIL=0 SKIP=1 TOTAL=28   RESULT: PASS

# 后端不可达时：API 部分 SKIP 并提示，SDK 部分照常 PASS，退出码 0
[SKIP] HTTP API 端到端 — 后端不可达: http://localhost:59999/health
SUMMARY: PASS=27 FAIL=0 SKIP=1 TOTAL=28   RESULT: PASS

# 部署 API 全量运行（DELETE 修复后，§4.6.3）
SUMMARY: PASS=49 FAIL=0 SKIP=0 TOTAL=49   RESULT: PASS
```

### 3.2 集成测试（默认 skip）

[`backend/tests/integration/services/test_minio_real.py`](../../../backend/tests/integration/services/test_minio_real.py)

```powershell
cd backend
# 默认：整模块 5 skipped，不污染全量 pytest
G:\ai-diagnostic-platform\.venv\Scripts\python.exe -m pytest tests/integration/services/test_minio_real.py -v

# 显式开启真实 MinIO（连不上会自动 skip 而非 fail）
$env:RUN_REAL_MINIO="1"
G:\ai-diagnostic-platform\.venv\Scripts\python.exe -m pytest tests/integration/services/test_minio_real.py -v
Remove-Item Env:\RUN_REAL_MINIO
```

门槛设计：未设置 `RUN_REAL_MINIO=1` → 整模块 skip；设置了但 `localhost:9000` 连不上 →
fixture 内 `pytest.skip`（不 fail CI）。连接参数用 `MINIO_VERIFY_ENDPOINT`（默认
`localhost:9000`），**不依赖 Docker 内网名 `minio:9000`**。

### 3.3 回退分支单测

```powershell
cd backend
G:\ai-diagnostic-platform\.venv\Scripts\python.exe -m pytest tests/unit/services/test_log_storage.py -v
```

## 4. 真实验证证据

### 4.1 host 侧 S3 SDK 直连（全部 PASS）

```text
connected endpoint=localhost:9000 buckets=['diagnostic-logs', 'knowledge-images']

=== 0. bucket 存在性检查 / 自动创建 ===
[PASS] bucket diagnostic-logs — exists=True        # 首次运行: exists=False (created just now)
[PASS] bucket knowledge-images — exists=True

=== 1. S3 SDK 直连：put/stat/get/presign/remove ===
object_key=verify/20261112-164331-ac42c5eb-binary.bin bytes=4368
          sha256=e3b4035c04408cc04bff8bd9630454e1a571f50f80b9e7e6f33c98b1e78dec88
[PASS] put_object — bucket=diagnostic-logs key=verify/...-binary.bin size=4368
[PASS] stat_object size — stat.size=4368 expected=4368
[PASS] stat_object etag == md5(payload) — etag=c1bbf5d68c823ce130063c09acbe526c
[PASS] stat_object content_type — application/octet-stream
[PASS] get_object 逐字节一致 — sha256=e3b4035c...
[PASS] presigned_get_object HTTP 200 — status=200
[PASS] presigned GET 内容逐字节一致 — body_sha256=e3b4035c...
presigned_url=http://localhost:9000/diagnostic-logs/verify/...-binary.bin?... (query omitted)
[PASS] remove_object 后 stat 报 NoSuchKey — code=NoSuchKey
```

| 证据 | 值 |
|------|-----|
| bucket | `diagnostic-logs`（自动创建）、`knowledge-images`（已存在） |
| object key | `verify/20261112-164331-ac42c5eb-binary.bin` |
| size | 4368 bytes（含 NUL 的二进制，验证字节保真） |
| ETag | `c1bbf5d68c823ce130063c09acbe526c`（= payload md5） |
| SHA-256 | `e3b4035c04408cc04bff8bd9630454e1a571f50f80b9e7e6f33c98b1e78dec88`（put 前 = get 后 = 预签名 GET 后） |
| 预签名 GET | HTTP 200，内容逐字节一致 |
| remove 后 stat | `NoSuchKey` |

### 4.2 部署网络路径验证（backend 容器内 → `minio:9000`）

在**运行中的** `ai-diagnostic-backend` 容器内（旧镜像也可执行，仅用容器已有 minio SDK 与容器
环境变量），按后端实际部署配置（`MINIO_ENDPOINT=minio:9000`）真连验证：

```text
endpoint= minio:9000 buckets= ['diagnostic-logs', 'knowledge-images']
key= verify/container-net-cef952c241ca4dccbd4ec27a2516b239.bin
size= 35  etag= 21e23ccb241fb821a99c0465d64ebd33  md5= 21e23ccb241fb821a99c0465d64ebd33  bytes_match= True
after_remove= NoSuchKey
```

证据：容器内 `Minio("minio:9000", ...)` 可列 bucket、put/get/stat/remove 全通，ETag==md5、
删除后 NoSuchKey。说明 **compose 中后端 env（`MINIO_ENDPOINT=minio:9000` + 凭据）本身可用**，
重启后新代码走同一客户端配置即可。

### 4.3 后端 `LogStorage` 类真连（host 侧，settings 指向 localhost:9000）

```text
=== 2. 后端 LogStorage 类真连（save/materialize/delete） ===
[PASS] LogStorage.remote_available — enabled=True bucket=diagnostic-logs
[PASS] LogStorage.save 返回 minio:// 引用
       — minio://diagnostic-logs/logs/793ede5c3d494b018d3c037c58ddf584_minio_e2e_logstorage.log
[PASS] MinIO 对象大小与本地一致 — stat.size=216 local=216
[PASS] MinIO ETag == md5(payload) — f93deb3b85750a3d05a54a5d71c2fda8
[PASS] materialize 下载内容逐字节一致
       — C:\Users\EDY\AppData\Local\Temp\diag_logs\793ede5c3d494b018d3c037c58ddf584_minio_e2e_logstorage.log
[PASS] LogStorage.delete 后 stat 报 NoSuchKey — code=NoSuchKey
```

说明：该段直接实例化后端生产类 `app.services.diagnostics.log_storage.LogStorage`，
`save()` 返回 `minio://diagnostic-logs/logs/<uuid>_<filename>`；`materialize()` 从 MinIO
下载到 `%TEMP%\diag_logs\`；`delete()` 调用 `remove_object`。**即后端解析/分析所依赖的
下载链路在真实 MinIO 上可用**（API 级证据见 §4.5（本地干跑）/ §4.6（部署））。

### 4.4 后端 `KnowledgeImageStorage` 类真连

```text
=== 3. 后端 KnowledgeImageStorage 类真连（save/get_bytes/presign_url/delete） ===
[PASS] KnowledgeImageStorage.use_minio — bucket=knowledge-images
[PASS] save 返回 storage_key — verify/89d6b71c9bb7447d8a3482e80e8375b3.png
[PASS] MinIO 对象大小一致 — stat.size=112 local=112
[PASS] MinIO ETag == md5(payload) — a8f6661d3ed5b5802c7f5f575e37671c
[PASS] get_bytes 逐字节一致 — sha256=f901602f8a64de8a37c6db3f115a320d63efb078aa432bcb72843b509aa821da
[PASS] presign_url 生成预签名 URL
       — http://localhost:9000/knowledge-images/verify/89d6b71c...png?X-Amz-Algorithm=AWS4-HMAC-SHA256&...
[PASS] presign_url 预签名 URL HTTP 200 — status=200
[PASS] 预签名 URL 内容一致 — sha256=f901602f...
[PASS] delete 后 stat 报 NoSuchKey — code=NoSuchKey
```

### 4.5 本地干跑：新代码 + 真实 MinIO 的 HTTP API 端到端（✅ 预演）

在 Docker 容器重启前，用工作区**新代码**在 host 起临时 uvicorn（`127.0.0.1:18080`，SQLite
文件库、`MILVUS_ENABLED=false`、mock LLM、`MINIO_ENDPOINT=localhost:9000`），跑同一脚本的
完整 API 链路（`--api-base http://127.0.0.1:18080`），结果 **PASS=49 FAIL=0 SKIP=0**：

```text
=== 4a. 日志 API 端到端（upload → parse → delete） ===
POST /logs/upload => 200，log_id=1
  file_path = minio://diagnostic-logs/logs/c83ca6f802ba4165b47912e781c94cbe_minio_e2e_sample.log
  size=499 status=uploaded
[PASS] 响应 file_path 为 minio://<bucket>/logs/...
[PASS] MinIO 中对象存在且大小一致 — size=499 local=499
[PASS] MinIO 对象 ETag == md5(上传文件) — a3fa81d1993498b7a6ac0a337efa3dfd
[PASS] GET /logs/{id} 返回 200 / file_path 一致
[PASS] POST /logs/{id}/parse 返回 200（materialize 从 MinIO 下载成功）
       status=completed source_type=generic event_count=6 error_count=1
[PASS] 解析事件数与样例日志行数一致 — event_count=6 expected=6
[PASS] parse-status 为 parsed — {"log_id":1,"status":"parsed"}
[PASS] DELETE /logs/{id} 返回 204
[PASS] 删除后 MinIO 对象消失（NoSuchKey） — stat code=NoSuchKey

=== 4b. 知识库图片 API 端到端（upload → get → presign） ===
POST /knowledge/images => 201
  {"id":1,"doc_id":null,"url":"/api/v1/knowledge/images/1","mime_type":"image/png",...}
  storage_key = da/91/da9133cfba18b15749d4a2f689145fd8f8d69b2c5686f1771daa5a6e37bc34be.png
[PASS] knowledge-images 对象存在且大小一致 — size=118 local=118
[PASS] knowledge-images 对象 ETag == md5(payload) — fda45778d417d6e844ce9cc8c399634a
[PASS] GET /knowledge/images/{id} 返回 200（从 MinIO 读回）
[PASS] API 返回图片字节与上传一致 — sha256=da9133cf...
[PASS] API 返回 Content-Type=image/png
[PASS] knowledge-images 预签名 URL HTTP 200 / 内容一致
[PASS] KnowledgeImageStorage.presign_url HTTP 200

SUMMARY: PASS=49 FAIL=0 SKIP=0 TOTAL=49
RESULT: PASS
```

> 这段证明：**新代码 + 真实 MinIO 的完整 HTTP 链路（日志 upload→parse→delete、
> 图片 upload→get）已工作**；与部署端到端的差异仅在于运行载体（本地 uvicorn vs
> Docker 容器/新镜像），部署端到端见 §4.6。

### 4.6 Docker 部署端到端

#### 4.6.1 重启前（旧镜像）实测现状

运行中容器 `ai-diagnostic-backend`（created 2026-11-12 14:13，镜像 `sha256:6e3a0d2e...`）是
**旧镜像**：容器内 `import app.services.diagnostics.log_storage` 报 `ModuleNotFoundError`。
对 `http://localhost:8000` 跑完整脚本（`SUMMARY: PASS=38 FAIL=2 TOTAL=40`）得到两条关键事实：

```text
=== 4a. 日志 API 端到端（upload → parse → delete） ===
[PASS] POST /logs/upload 返回 200 — {"id":1,...,"file_path":"/app/data/raw/minio_e2e_sample.log","size":499,...}
[FAIL] 响应 file_path 为 minio://<bucket>/logs/... — /app/data/raw/minio_e2e_sample.log
  => 旧部署服务“MINIO_ENABLED=true”但日志仍写容器本地路径，MinIO 日志链路未生效（与新代码走查
     log_storage 缺失一致）；脚本已 DELETE /logs/1（复验 GET => 404，无残留）。

=== 4b. 知识库图片 API 端到端（upload → get → presign） ===
[PASS] POST /knowledge/images 返回 201 — image_id=57, url=/api/v1/knowledge/images/57
[PASS] knowledge-images 对象存在且大小一致 — size=118 local=118
[PASS] knowledge-images 对象 ETag == md5(payload) — 5a1ae1e8763806e5cb18ab60d4e6e9ae
[PASS] GET /knowledge/images/{id} 返回 200（从 MinIO 读回）
[PASS] API 返回图片字节与上传一致 / Content-Type=image/png
[PASS] knowledge-images 预签名 URL HTTP 200 / 内容一致
[PASS] KnowledgeImageStorage.presign_url HTTP 200
```

> 即：**知识库图片的部署端到端在旧镜像上已真实通过**（upload→MinIO 对象存在且 ETag 一致→
> API 读回字节一致→预签名 GET 200）；**日志链路**需新镜像重启后才生效（§4.6.2）。
> 本次验证对象清理后复查：`diagnostic-logs` 0 个对象、`knowledge-images` 16 个既有对象
> （均为验证前已存在，无 `verify/` 残留）。

#### 4.6.2 修复前实测（2026-11-12 17:20，镜像 `5e74f47c`，`backend` 第二次重启）

重启确认：`ai-diagnostic-backend` 新容器 `image=sha256:5e74f47c2c41...`（包含 log_storage 模块），
`/health=200`；容器内 `MINIO_ENABLED=True endpoint=minio:9000 bucket=diagnostic-logs
remote_available=True`。对 `http://localhost:8000` 跑完整脚本：

```text
=== 0/1/2/3 SDK、LogStorage、KnowledgeImageStorage 章 ===
（与 §4.1–4.4 host 侧结果一致，全部 PASS；本次对象 verify/20261112-172040-acc3c6e0-binary.bin
 4368B / etag=08590e64261c8b497d4860740da98e04）

=== 4a. 日志 API 端到端（upload → parse → delete） ===
[PASS] POST /logs/upload 返回 200
       {"id":2,"file_path":"minio://diagnostic-logs/logs/c9b3e07004d442a6a9e89a468c289226_minio_e2e_sample.log","size":499,...}
[PASS] 响应 file_path 为 minio://<bucket>/logs/...
[PASS] MinIO 中对象存在且大小一致 — size=499 local=499
[PASS] MinIO 对象 ETag == md5(上传文件) — a3fa81d1993498b7a6ac0a337efa3dfd
[PASS] GET /logs/{id} 返回 200 / file_path 一致
[PASS] POST /logs/{id}/parse 返回 200（materialize 从 MinIO 下载成功）
       status=completed event_count=6 error_count=1 source_type=generic
[PASS] 解析事件数与样例日志行数一致 — event_count=6 expected=6
[PASS] parse-status 为 parsed — {"log_id":2,"status":"parsed"}
[FAIL] DELETE /logs/{id} 返回 204 — status=500 body={"detail":"Internal server error"}
[FAIL] 日志 API 端到端未全部通过 — DELETE /logs/{id} 返回 204: status=500

=== 4b. 知识库图片 API 端到端（upload → get → presign） ===
[PASS] POST /knowledge/images 返回 201 — {"id":58,...,"url":"/api/v1/knowledge/images/58","mime_type":"image/png"}
[PASS] knowledge-images 对象存在且大小一致 — size=118 local=118
[PASS] knowledge-images 对象 ETag == md5(payload) — 5ec83ed79d959d5ed587f72bed968365
[PASS] GET /knowledge/images/{id} 返回 200（从 MinIO 读回）
[PASS] API 返回图片字节与上传一致 — sha256=7ccb9303... / Content-Type=image/png
[PASS] knowledge-images 预签名 URL HTTP 200 / 内容一致
[PASS] KnowledgeImageStorage.presign_url HTTP 200

SUMMARY: PASS=47 FAIL=2 SKIP=0 TOTAL=49
RESULT: FAIL（仅 DELETE 两项失败）
```

**新增 P1 缺陷（部署实测复现，详见 §6）**：`DELETE /api/v1/logs/{id}` 对**已解析**日志返回
500（`log_events_log_id_fkey` 外键冲突），且 MinIO 对象在 DB commit 前就被删除：

```text
docker logs ai-diagnostic-backend（摘要）:
sqlalchemy.exc.IntegrityError: (psycopg2.errors.ForeignKeyViolation) update or delete on table
"logs" violates foreign key constraint "log_events_log_id_fkey" on table "log_events"
DETAIL:  Key (id)=(2) is still referenced from table "log_events".
[SQL: DELETE FROM logs WHERE logs.id = %(id)s]  parameters: {'id': 2}
  File "/app/app/services/diagnostics/log_service.py", line 148, in delete_log -> self.db.commit()

删除后实测状态：
GET  /api/v1/logs/2 => 200，status=parsed，file_path=minio://diagnostic-logs/logs/c9b3e070...log
SDK  stat 该 key   => NoSuchKey        ← 对象已被删除，但 DB 记录残留，引用悬空
对照：未解析过的日志（id=5）DELETE => 204，对象与记录均删除（证明仅“有 log_events 行”时触发）
```

即：**上传、MinIO 对象核对、parse/materialize、图片链路全部真实通过**；唯一失败项是
“已解析日志删除”，且暴露对象/数据库不一致（对象已删、记录仍在）的 P1 缺陷。
该残留 log id=2 记录随后作为证据保留，并在修复后清理（见 §4.6.3）。

#### 4.6.3 修复后复验（2026-11-12 17:40，镜像 `15b6c836`，`backend` 第三次重启）

**修复内容**（`backend/app/services/diagnostics/log_service.py::delete_log`，task-6）：
① 同一 DB 事务内先删该日志的 `log_events` 行、再删 `logs` 行并 commit；
② DB 成功后才执行 `LogStorage().delete()` 删 MinIO 对象/本地文件，失败仅 warning 不阻断；
③ 不改 schema/迁移（根因 `log_events.log_id` FK 无 ON DELETE CASCADE；后续可选方案：加
`ondelete="CASCADE"` + alembic 迁移）。
回归测试：新增 [`backend/tests/unit/services/test_log_delete_events.py`](../../../backend/tests/unit/services/test_log_delete_events.py)
（7 tests，含 service 层顺序保护 + API 层 DELETE 204/事件清空；见 §4.7）。

部署复验（重启确认 `image=sha256:15b6c836...`，容器内 `inspect.getsource(delete_log)` 已含新逻辑）：

```text
=== 4a. 日志 API 端到端（upload → parse → delete） ===
[PASS] POST /logs/upload 返回 200
       {"id":6,"file_path":"minio://diagnostic-logs/logs/7e2ddebcd35d4a73896973a76cc21849_minio_e2e_sample.log","size":499,...}
[PASS] MinIO 中对象存在且大小一致 — size=499 local=499 / ETag == md5 — a3fa81d1993498b7a6ac0a337efa3dfd
[PASS] POST /logs/{id}/parse 返回 200（materialize 从 MinIO 下载成功）— status=completed event_count=6
[PASS] parse-status=parsed
[PASS] DELETE /logs/{id} 返回 204 — status=204 body=（修复前此处为 500）
[PASS] 删除后 MinIO 对象消失（NoSuchKey）— stat code=NoSuchKey

=== 4b. 知识库图片 API 端到端 ===
[PASS] POST /knowledge/images 201（id=59）→ bucket 对象 size=118/ETag 一致 → GET 字节一致/Content-Type=image/png
[PASS] 预签名 URL HTTP 200 / 内容一致；KnowledgeImageStorage.presign_url 200

SUMMARY: PASS=49 FAIL=0 SKIP=0 TOTAL=49
RESULT: PASS
```

DB 层复核（`docker exec ai-diagnostic-postgres psql -U ai -d diagnostic`）：

```text
# 被删除的已解析日志 id=6
SELECT count(*) FROM logs WHERE id=6;              -- 0
SELECT count(*) FROM log_events WHERE log_id=6;    -- 0   ← log_events 同一事务清空
```

残留证据清理（修复后可正常走 API）：`DELETE /api/v1/logs/2`（历史悬空记录，事件 6 行）=> **204**；
复验 `GET /api/v1/logs/2 => 404`、`logs id=2 => 0`、`log_events log_id=2 => 0`。
`knowledge_images` 中验证残留 DB 行 id=57/58/59（`caption='minio_e2e'`, `doc_id=NULL`）已删除 3 行：
`remaining_minio_e2e=0`，`total_knowledge_images=16`（均为验证前既有图片，未误删）。
MinIO 复查：`diagnostic-logs` 无 `verify/` 残留（仅 PDF 验证任务的 `pdf_e2e_*.log`）、
`knowledge-images` 16 个既有对象、无 `verify/` 残留。

> ✅ **结论：修复后部署端到端 PASS=49 FAIL=0；已解析日志 DELETE→204、`log_events`/`logs` 行清空、
> MinIO 对象删除，历史不一致记录已清理。**

### 4.7 测试结果

```text
# 默认（未设置 RUN_REAL_MINIO）
tests/integration/services/test_minio_real.py::test_bucket_exists SKIPPED
... 共 5 skipped in 0.18s

# RUN_REAL_MINIO=1（真实 MinIO）
tests/integration/services/test_minio_real.py::test_bucket_exists PASSED
tests/integration/services/test_minio_real.py::test_sdk_put_get_stat_presign_remove PASSED
tests/integration/services/test_minio_real.py::test_log_storage_save_materialize_delete PASSED
tests/integration/services/test_minio_real.py::test_knowledge_image_storage_roundtrip PASSED
tests/integration/services/test_minio_real.py::test_disabled_storage_uses_local PASSED
============= 5 passed in 0.74s =============

# 回退分支单测（基线不回归）
tests/unit/services/test_log_storage.py::TestLocalLogStorage::test_local_passthrough PASSED
tests/unit/services/test_log_storage.py::TestLocalLogStorage::test_minio_reference_unavailable_raises PASSED
============= 2 passed in 1.60s =============

# 全量回归（backend 目录，task-2 阶段）
G:\ai-diagnostic-platform\.venv\Scripts\python.exe -m pytest -q
============= 466 passed, 8 skipped in 36.91s =============
# 基线为 466 passed / 1 skipped；新增 7 个 skip = 本文件 5 个 + tests/integration/api/test_report_pdf_api.py 2 个
# （另一 teammate 新增，均默认 skip），466 passed 不变 → 无回归。

# 删除 bug 修复新增回归测试（task-6）
G:\ai-diagnostic-platform\.venv\Scripts\python.exe -m pytest tests/unit/services/test_log_delete_events.py -v
============= 7 passed, 1 warning in 145.60s =============
# 指定回归集：test_log_delete_events.py + test_log_storage.py + tests/integration/api/
============= 125 passed, 2 skipped in 45.06s =============

# 修复后全量回归（backend 目录）
G:\ai-diagnostic-platform\.venv\Scripts\python.exe -m pytest -q
============= 473 passed, 11 skipped in 52.16s =============
# 473 = 原 466 + 新增 7（删除回归）；11 skipped 均为默认 skip 用例（minio/milvus/pdf 等真连测试，由其他任务新增），
# 0 failed / 0 error → 无回归。
```

## 5. 代码链路走读

### 5.1 日志：上传 → `minio://` → 解析下载 → 删除

| 阶段 | 代码位置 | 行为 |
|------|----------|------|
| 上传落本地暂存 | `backend/app/services/diagnostics/log_service.py:44-75` | `UploadFile` 分块写入 `UPLOAD_DIR`，大小超限 413，二进制 NUL 拒绝，`.zip/.gz` 自动解包 |
| 上传对象存储 | `log_service.py:78` → `log_storage.py:60-72` | `fput_object(bucket, "logs/<uuid>_<filename>")`，成功返回 `minio://<bucket>/<key>`；**失败仅 warning 并返回本地绝对路径** |
| 落库 | `log_service.py:80-93` | `Log.file_path` 存该引用 |
| 解析前物化 | `parsing_service.py:32/40/54`、`analysis_task_service.py:162`、`chat/agent_service.py:47` → `log_storage.py:74-95` | `minio://` 引用 → `fget_object` 到 `%TEMP%\diag_logs\<key名>`；MinIO 不可用时抛 `LogStorageError` |
| 删除 | `log_service.py:144-178` → `log_storage.py:97-112` | **（task-6 修复后）** 同一 DB 事务先删 `log_events` 再删 `logs` 并 commit；DB 成功后才 `LogStorage().delete()`（`minio://` → `remove_object`；本地路径 → `unlink`），对象删除失败仅 warning 不阻断。修复前顺序相反且不删 events → 已解析日志 DELETE 500 + 对象/记录不一致（§4.6.2）；修复后复验 §4.6.3 |

### 5.2 知识库图片

| 阶段 | 代码位置 | 行为 |
|------|----------|------|
| 编辑单图上传 | `backend/app/api/knowledge/__init__.py:228-242` → `services/knowledge/image_service.py:56-82` | `POST /api/v1/knowledge/images`（multipart `file`），sha256 内容寻址 `abcdef...png`（`sha[:2]/sha[2:4]/sha.ext`），`KnowledgeImageStorage.save` 写 MinIO，DB 记录 `KnowledgeImage`（`doc_id` 可空） |
| 文档内嵌图片 | `image_service.py:88-161` | data URI / http(s) / 本地相对路径 → 下载入库 → src 重写为 `/api/v1/knowledge/images/{id}` |
| 读取 | `knowledge/__init__.py:245-263` → `image_storage.py:94-109` | `GET /api/v1/knowledge/images/{id}`，后端用 `get_bytes()` 从 MinIO 全量读出后流式返回（不走预签名） |
| 预签名 | `image_storage.py:111-118` | 已实现 `presign_url()`，但**全仓库无调用点**（死代码，见 §6-P6） |
| 删除 | `image_storage.py:120-126` | 已实现，但**全仓库无调用点**；`DELETE` 图片 API 不存在 |

### 5.3 API 端点核对

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/api/v1/logs/upload` | multipart：`file`（必填）+ `project_id/upload_user_id/device/version/description`（可选） |
| `GET` | `/api/v1/logs/{id}` | 日志元数据 |
| `POST` | `/api/v1/logs/{id}/parse` | 触发解析（内部 `materialize()` 从 MinIO 下载） |
| `GET` | `/api/v1/logs/{id}/parse-status` | 解析状态 |
| `DELETE` | `/api/v1/logs/{id}` | 删库记录 + 删对象 |
| `POST` | `/api/v1/knowledge/images` | multipart `file`，201 返回 `{id, url, mime_type, ...}` |
| `GET` | `/api/v1/knowledge/images/{id}` | 从 MinIO 读字节返回 |

（`app.main` 统一挂载 `prefix="/api/v1"`；`app/api/router.py` 注册 `logs/parsing/knowledge` 路由。
`backend/app/api/knowledge/images.py` 不存在，图片端点位于 `app/api/knowledge/__init__.py`。）

## 6. 发现的问题与风险（本次未改业务代码，仅报告）

> 建议按 P1→P3 处理；P1 建议在本次审计收尾前至少由 Lead 决策是否修。

| 等级 | 问题 | 证据/影响 | 建议 |
|------|------|-----------|------|
| **P1**（✅ 已修复并复验） | 已解析日志的 `DELETE /api/v1/logs/{id}` 返回 **500**；且 MinIO 对象先删、DB commit 失败 → **记录引用悬空** | 部署实测（§4.6.2）：`DELETE /logs/2` → 500，容器 traceback `IntegrityError: log_events_log_id_fkey`；`log_event.py:14` 的 FK 无 `ondelete="CASCADE"`，旧 `log_service.py:144-148` 先 `LogStorage().delete()`（对象已删）再 `db.delete(log)+commit`（commit 失败）→ 实测删除后对象 `NoSuchKey` 而记录仍在（status=parsed），该日志无法再解析/分析；未解析日志 DELETE 正常（id=5→204），证明仅“存在 log_events 行”时触发。**修复（task-6）**：`delete_log` 同一事务先删 `log_events` 再删 `logs`，DB 成功后才删对象（失败仅 warning）；新增 7 个回归测试；重启后复验 DELETE→204、events/logs 清空、PASS=49 FAIL=0（§4.6.3） | 已按 ①②③ 实施（本次不改 schema/迁移）；后续可选：给 `log_events.log_id` 加 `ondelete="CASCADE"` + alembic 迁移 |
| **P1** | `diagnostic-logs` bucket 不会自动创建；上传失败**静默回退本地**且无告警 | ① 本次实测 MinIO 初始只有 `knowledge-images`，`diagnostic-logs` 不存在；② 实证（endpoint 指向不可用端口 `localhost:19999`）：`LogStorage.remote_available=True`（客户端创建不连接）、`save()` **不抛异常**返回本地路径、`caller_sees_error=False`，仅一条 warning 日志（`log_storage.py:66-72`）。结果是“MINIO_ENABLED=true 但日志实际存本地”，Docker 多副本/重启后文件不可见、备份策略失效 | ① `LogStorage._create_client` 或 `save` 中 `bucket_exists`/`make_bucket`（与 `KnowledgeImageStorage._get_minio` 对齐）；② 上传失败按配置决定 fail-fast 或至少暴露 metrics/health；③ compose 加 minio-init 服务或部署文档写明 `mc mb` |
| **P1** | `materialize()` 下载的临时文件从不清理 | `log_storage.py:89-95` 写 `%TEMP%\diag_logs\`，全仓库无 unlink；实证：本地干跑一次 parse 后 `%TEMP%\diag_logs\c83ca6f802..._minio_e2e_sample.log`（499B）残留，多次运行累积（现有 6 个副本）；每次 parse/analysis/chat 都会重新下载并留下副本（容器内 `/tmp`） | 解析完成 `finally` 清理，或用 `tempfile.NamedTemporaryFile(delete=False)` + 上下文管理；大日志（100MB）会成倍占用临时空间 |
| **P2** | 日志上传成功后本地暂存文件不删；删除日志时也不删本地暂存文件 | `log_service.py:78` 上传 MinIO 后未 `destination.unlink()`；`delete_log` 只处理 `file_path`（minio://）。实证：本地干跑 `DELETE /api/v1/logs/1` 返回 204 且 MinIO 对象已 NoSuchKey，但 `UPLOAD_DIR\minio_e2e_sample.log`（499B）仍残留；`upload_data` 卷持续增长 | 上传成功即删暂存文件；或明确保留 N 天后清理 |
| **P2** | MinIO 无生命周期/保留策略 | 日志与图片对象无限增长，`minio_data` 卷无上限；`docker-compose.yml` 无 `mc ilm` 初始化 | 用 `mc ilm rule add` 为 `diagnostic-logs` 设保留期（如 30/90 天），图片按业务；文档补充运维命令 |
| **P2** | 知识库图片对象无删除路径 → 孤儿对象 | `KnowledgeImageStorage.delete()` 无调用点；`KnowledgeService.delete()` 仅删 DB（FK `ondelete=CASCADE` 删记录），MinIO 对象永久残留；也没有 `DELETE /knowledge/images/{id}` 端点 | 删除文档/替换图片时调用 `storage.delete`；补管理端清理脚本 |
| **P2** | 预签名 URL 使用后端内部 endpoint，浏览器不可达 | `image_storage.py:116` 用 `MINIO_ENDPOINT`（容器内 `minio:9000`）签名；当前 API 不用预签名（走后端流式），一旦启用直连，前端拿到 `http://minio:9000/...` 必失败 | 增加 `MINIO_PUBLIC_ENDPOINT` 仅用于签名；或继续经后端流式端点（当前做法） |
| **P3** | 二进制/大小校验先全量读入内存 | `log_service.py:181` `path.read_bytes()[:8192]` 读了整个文件才切片；`knowledge/__init__.py:234` `file.file.read()` 先读满再判 `MAX_IMAGE_SIZE_MB` | 改 `f.read(8192)`；图片用分块计数或 `UploadFile.size` 预检 |
| **P3** | 两种存储类失败语义不一致 | `LogStorage` 静默回退本地；`KnowledgeImageStorage._get_minio` 抛异常→图片上传 500 | 统一策略并在 README/配置中说明 |
| **P3** | 上传成功但 DB commit 失败 → 对象孤儿 | `log_service.py:78` 与 `:92` 之间无补偿；图片同理（`image_service.py:68` → `:79`） | 事务失败时 try/except 删对象；或引入后台清理任务 |
| **P3** | `materialize` 并发写同一临时路径 | `log_storage.py:89` 目标名仅取 key 末段；同一日志被并发解析时两进程写同一文件 | 目标文件加 uuid 后缀或 `NamedTemporaryFile` |
| **P3** | bucket 自动创建并发竞态 | `KnowledgeImageStorage._get_minio` 中 `bucket_exists`+`make_bucket` 非原子，首次并发请求可能 `BucketAlreadyOwnedByYou` | 捕获该错误视为成功 |

## 7. 与本地回退分支的差异

| 维度 | `MINIO_ENABLED=false`（本地回退） | `MINIO_ENABLED=true`（MinIO 真链路） |
|------|-----------------------------------|--------------------------------------|
| 日志保存 | `file_path` = 本地绝对路径（`UPLOAD_DIR`） | `file_path` = `minio://<bucket>/logs/<uuid>_<name>` |
| 解析下载 | 直接读本地路径，无拷贝 | `materialize()` 下载到 `%TEMP%\diag_logs\`（临时副本，见 P1 清理问题） |
| 删除日志 | `unlink` 本地文件 | `remove_object` 删对象（本地暂存文件残留，见 P2） |
| 知识库图片 | 写 `KNOWLEDGE_IMAGE_DIR` 相对路径，`presign_url()` 返回 `None` | 写 `knowledge-images` bucket（自动建桶），`presign_url()` 返回预签名 URL |
| 依赖 | 无需 minio 包 | 需要 `minio>=7.2.0`；包缺失/连不上时日志链路静默回退、图片链路报错（语义不一致） |
| 多副本/持久化 | 文件绑定单容器卷，跨副本不可见 | 对象存储共享，可水平扩展（前提是 bucket 已初始化） |
| 测试 | `tests/unit/services/test_log_storage.py`（2 passed） | `tests/integration/services/test_minio_real.py`（默认 skip，`RUN_REAL_MINIO=1` 时 5 passed） |

## 8. 生产注意事项

1. **必须改默认口令**：compose 中 `MINIO_ROOT_USER/minioadmin`、`MINIO_ROOT_PASSWORD/minioadmin`
   是公开默认值；同时修改后端 `MINIO_ACCESS_KEY/MINIO_SECRET_KEY`。建议为后端创建**最小权限**
   service account（`mc admin user add` + 仅 `s3:GetObject/PutObject/DeleteObject/ListBucket` policy），
   不要直接用 root 凭据。
2. **TLS**：生产设 `MINIO_SECURE=true` 并通过挂载证书/反代提供 HTTPS；不要将 9000/9001 暴露公网
   （compose 当前 `-p 9000:9000 -p 9001:9001` 仅适合本地开发）。
3. **bucket 初始化**：compose 不会创建 bucket。部署脚本/init 容器中执行：
   ```powershell
   docker exec ai-diagnostic-minio mc alias set local http://localhost:9000 <user> <pass>
   docker exec ai-diagnostic-minio mc mb --ignore-existing local/diagnostic-logs local/knowledge-images
   ```
   否则首次日志上传会静默落本地（§6-P1）。
4. **生命周期/清理**：为日志对象设保留策略，例如
   `mc ilm rule add local/diagnostic-logs --expire-days 90`；同时清理 `/tmp/diag_logs`（§6-P1）。
5. **endpoint 区分**：容器内用 `minio:9000`；host 工具/CI 用 `localhost:9000`；若需前端直连
   预签名 URL，必须配置公网可达 endpoint（不要直接用 `MINIO_ENDPOINT` 签名）。
6. **容量与监控**：`minio_data` 卷需纳入磁盘告警；MinIO 本身提供
   `/minio/health/live` 与 Prometheus metrics，可接入现有 Prometheus。
7. **备份/版本**：按需开启 bucket versioning 或 `mc mirror` 到第二存储；`minio_data` 卷不可与
   postgres/redis 共用故障域。
8. **密钥管理**：`.env`/compose 中不要提交真实凭据；生产用 secret 管理（compose `secrets`/环境注入）。

## 9. 复现命令汇总

```powershell
# 0) 前置：MinIO 容器已启动（见 §2.1）且 venv 已装 minio
docker ps --filter name=ai-diagnostic-minio

# 1) host SDK + 存储类真连（可重复运行；--skip-api 用于后端未重启时）
cd G:\ai-diagnostic-platform
.\.venv\Scripts\python.exe backend\scripts\verify\minio_storage_e2e.py --skip-api

# 2) 集成测试（默认 skip）
cd backend
G:\ai-diagnostic-platform\.venv\Scripts\python.exe -m pytest tests/integration/services/test_minio_real.py -v
$env:RUN_REAL_MINIO="1"
G:\ai-diagnostic-platform\.venv\Scripts\python.exe -m pytest tests/integration/services/test_minio_real.py -v
Remove-Item Env:\RUN_REAL_MINIO

# 3) 回退分支单测
G:\ai-diagnostic-platform\.venv\Scripts\python.exe -m pytest tests/unit/services/test_log_storage.py -v

# 4) 后端重启后：完整 API 端到端（含日志 upload/parse/delete 与 knowledge-images）
cd G:\ai-diagnostic-platform
.\.venv\Scripts\python.exe backend\scripts\verify\minio_storage_e2e.py

# 可选：本地干跑（不依赖 Docker backend；工作区新代码 + SQLite + 真实 MinIO）
#   在 backend/ 起 uvicorn（环境变量见 §4.5），再以 --api-base http://127.0.0.1:18080 运行脚本
```

## 10. 遗留问题

1. **✅ 已解决：已解析日志 `DELETE /api/v1/logs/{id}` 500 + 对象/记录不一致**（§6-P1、§4.6.2）：
   根因 `log_events.log_id` FK 无级联 + 旧 `delete_log` 先删对象后 commit。已由 task-6 修复：
   `delete_log` 同一事务先删 `log_events` 再删 `logs`，DB 成功后才删对象（失败仅 warning）；
   新增 `tests/unit/services/test_log_delete_events.py`（7 tests）。第三次重启后复验：
   `minio_storage_e2e.py` **PASS=49 FAIL=0**、DELETE→204、`log_events`/`logs` 行清空、对象删除。
   后续可选强化：给 `log_events.log_id` 加 `ondelete="CASCADE"` + alembic 迁移（本次未改 schema）。
2. **✅ 验证残留已清理**（修复后复验阶段执行）：
   - 历史悬空记录 `logs.id=2`（旧对象已删）已通过修复后的 `DELETE /api/v1/logs/2` 清理：**204**，
     `GET => 404`，`logs/log_events` 计数均 0；
   - `knowledge-images` 验证残留 DB 行 id=57/58/59（`doc_id=NULL`、`caption='minio_e2e'`）已删除
     （`DELETE 3`），复验 `remaining_minio_e2e=0`、`total_knowledge_images=16`（均为验证前既有图片）；
   - MinIO 复查无 `verify/` 残留；`diagnostic-logs` 仅剩 PDF 验证任务（另一 teammate）的
     `pdf_e2e_*.log` 对象，不属于本任务；
   - 各轮验证的 MinIO 测试对象均由脚本自动清理。
3. **`diagnostic-logs` bucket 系验证脚本创建**：若部署环境卷被清理，recreate 后需重新初始化；
   建议按 §8.3 固化为 init 步骤（本次未改 compose）。
4. **§6 其余 P1/P2 问题未修**（本次只修 DELETE 500 一项；“静默回退本地+不自动建桶”“materialize
   临时文件不清理”“本地暂存/生命周期”“图片对象无删除路径”等建议优先排期）。
5. **全量 pytest 基线**：task-2 阶段 466 passed / 8 skipped；task-6 新增 7 个删除回归测试后全量
   **473 passed / 11 skipped / 0 failed**（skip 增量均为其他任务默认 skip 用例，无回归）。

## 附录 A：host 侧完整输出（`--skip-api`）

```text
MinIO E2E verification
  endpoint      = localhost:9000
  api_base      = http://localhost:8000
  log_bucket    = diagnostic-logs
  image_bucket  = knowledge-images
  skip_api      = True
connected endpoint=localhost:9000 buckets=['diagnostic-logs', 'knowledge-images']

=== 0. bucket 存在性检查 / 自动创建 ===
[PASS] bucket diagnostic-logs — exists=True
[PASS] bucket knowledge-images — exists=True

=== 1. S3 SDK 直连：put/stat/get/presign/remove ===
object_key=verify/20261112-164331-ac42c5eb-binary.bin bytes=4368 sha256=e3b4035c04408cc04bff8bd9630454e1a571f50f80b9e7e6f33c98b1e78dec88
[PASS] put_object — bucket=diagnostic-logs key=verify/20261112-164331-ac42c5eb-binary.bin size=4368
[PASS] stat_object size — stat.size=4368 expected=4368
[PASS] stat_object etag == md5(payload) — etag=c1bbf5d68c823ce130063c09acbe526c md5=c1bbf5d68c823ce130063c09acbe526c
[PASS] stat_object content_type — application/octet-stream
[PASS] get_object 逐字节一致 — sha256=e3b4035c04408cc04bff8bd9630454e1a571f50f80b9e7e6f33c98b1e78dec88
[PASS] presigned_get_object HTTP 200 — status=200
[PASS] presigned GET 内容逐字节一致 — body_sha256=e3b4035c04408cc04bff8bd9630454e1a571f50f80b9e7e6f33c98b1e78dec88
presigned_url=http://localhost:9000/diagnostic-logs/verify/20261112-164331-ac42c5eb-binary.bin?... (query omitted)
[PASS] remove_object 后 stat 报 NoSuchKey — code=NoSuchKey

=== 2. 后端 LogStorage 类真连（save/materialize/delete） ===
[PASS] LogStorage.remote_available — enabled=True bucket=diagnostic-logs
[PASS] LogStorage.save 返回 minio:// 引用 — minio://diagnostic-logs/logs/793ede5c3d494b018d3c037c58ddf584_minio_e2e_logstorage.log
[PASS] 引用 bucket 正确 — diagnostic-logs
[PASS] MinIO 对象大小与本地一致 — stat.size=216 local=216
[PASS] MinIO ETag == md5(payload) — f93deb3b85750a3d05a54a5d71c2fda8
[PASS] materialize 下载内容逐字节一致 — C:\Users\EDY\AppData\Local\Temp\diag_logs\793ede5c3d494b018d3c037c58ddf584_minio_e2e_logstorage.log
[PASS] LogStorage.delete 后 stat 报 NoSuchKey — code=NoSuchKey

=== 3. 后端 KnowledgeImageStorage 类真连（save/get_bytes/presign_url/delete） ===
[PASS] KnowledgeImageStorage.use_minio — bucket=knowledge-images
[PASS] 知识库 bucket 名 — knowledge-images
[PASS] save 返回 storage_key — verify/89d6b71c9bb7447d8a3482e80e8375b3.png
[PASS] MinIO 对象大小一致 — stat.size=112 local=112
[PASS] MinIO ETag == md5(payload) — a8f6661d3ed5b5802c7f5f575e37671c
[PASS] get_bytes 逐字节一致 — sha256=f901602f8a64de8a37c6db3f115a320d63efb078aa432bcb72843b509aa821da
[PASS] presign_url 生成预签名 URL — http://localhost:9000/knowledge-images/verify/89d6b71c9bb7447d8a3482e80e8375b3.png?X-Amz-Algorithm=AWS4-HMAC-SHA256&X-Am
[PASS] presign_url 预签名 URL HTTP 200 — status=200
[PASS] 预签名 URL 内容一致 — sha256=f901602f8a64de8a37c6db3f115a320d63efb078aa432bcb72843b509aa821da
[PASS] delete 后 stat 报 NoSuchKey — code=NoSuchKey
[SKIP] HTTP API 端到端 — --skip-api

========================================================================
SUMMARY: PASS=27 FAIL=0 SKIP=1 TOTAL=28
RESULT: PASS
```

## 附录 B：改动文件（写入范围内）

| 文件 | 任务 | 说明 |
|------|------|------|
| [`backend/scripts/verify/minio_storage_e2e.py`](../../../backend/scripts/verify/minio_storage_e2e.py) | task-2 | 可重复运行的 MinIO 端到端验证脚本（SDK + 存储类 + 可选 API），打印 key/size/etag/HTTP 证据 |
| [`backend/tests/integration/services/test_minio_real.py`](../../../backend/tests/integration/services/test_minio_real.py) | task-2 | 真实 MinIO 集成测试，默认 skip（`RUN_REAL_MINIO=1`），连接失败自动 skip |
| [`backend/app/services/diagnostics/log_service.py`](../../../backend/app/services/diagnostics/log_service.py) | task-6 | **修复** `delete_log()`：先删 `log_events` 再删 `logs` 并 commit，DB 成功后才删对象（失败仅 warning）；不改 schema/迁移 |
| [`backend/tests/unit/services/test_log_delete_events.py`](../../../backend/tests/unit/services/test_log_delete_events.py) | task-6 | 删除链路回归测试（7 tests：service 层顺序/失败保护 + API 层 DELETE 204/事件清空） |
| `docs/20-Audit/verification/02-minio.md` | task-2/6 | 本报告（含 P1 发现、修复与部署复验记录） |

未修改 `deploy/`、compose 或其他 teammate 文件；未 `git commit`；未重启容器（重启由 Lead 统一执行）。
