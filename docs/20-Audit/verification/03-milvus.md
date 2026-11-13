# Milvus 真实向量链路验证（compose 修复 + pymilvus 实连 + VectorService 两处 bug 修复）

- **日期**：2026-11-12
- **执行**：Agent Team 成员 `milvus-vector`
- **关联任务**：`task-3` — Milvus 真实向量链路验证（修复 compose 服务 + pymilvus 实连 insert/search + API）
- **状态**：✅ 完成（Milvus 服务 v2.4.0 内嵌 etcd 正常启动；pymilvus 2.5.4 ↔ server 2.4.0 全链路实测通过；API 端到端通过；全量 pytest 无回归）

## 1. 背景与结论

缺口背景：`deploy/docker-compose.yml` 中 milvus 服务使用 `milvusdb/milvus:v2.3.12`，
容器长期 `unhealthy`，日志持续输出 `etcd ... localhost:2379 connection refused`；
pymilvus 固定 2.5.4 但从未对真实 Milvus 服务做过 insert/search 验证；后端
`VectorService` 在容器内实际一直处于 keyword 回退状态。本任务同时定位并修复了
**4 个独立问题**（1 个 compose 配置缺失、1 个 healthcheck 假阴性、1 个依赖版本冲突、
2 个 VectorService 代码 bug）。

| # | 验证项 | 结论 |
|---|--------|------|
| 1 | compose milvus 服务启动修复（内嵌 etcd + local storage + curl healthcheck） | ✅ `ai-diagnostic-milvus` 镜像 `milvusdb/milvus:v2.4.0`，启动约 12s，`Up (healthy)` |
| 2 | `http://localhost:9091/healthz` / gRPC 19530 | ✅ healthz HTTP 200 body=OK；`Test-NetConnection 19530` = True |
| 3 | pymilvus 2.5.4 真连 server 2.4.0（create→index→load→insert→flush→search→delete→drop） | ✅ 兼容，临时 collection 全链路通过，search score 见 §7 |
| 4 | pymilvus 2.5.4 依赖 `pkg_resources` 与 setuptools>=81 冲突（venv + Docker 镜像双复现） | ✅ 根因定位；`setuptools==80.9.0` 修复，镜像内 `import pymilvus` 成功 |
| 5 | `VectorService` 无索引 load 报 `code=700`、`Hit.get()` TypeError 两处 bug | ✅ 已修复（§8），修复后 available=true、search 真实命中 |
| 6 | API 端到端：`/api/v1/vector/{health,embed,index,search,status}` | ✅ 真实容器验证全部通过（§9）：vector_only 命中 score=0.377964，hybrid 融合 2 条 |
| 7 | `knowledge_docs` collection 实体数 > 0 | ✅ API index 后 pymilvus query 确认数据真实写入（num_entities>0） |
| 8 | 新增测试默认 skip / 真实模式 | ✅ 默认 3 skipped；`RUN_REAL_MILVUS=1` → **3 passed**（33.5s） |
| 9 | verify 脚本可重复运行 | ✅ `backend/scripts/verify/milvus_e2e.py` 完整模式 **PASS=26 FAIL=0** |
| 10 | 全量 pytest 回归（基线 466 passed / 1 skipped） | ✅ **473 passed, 11 skipped**（28.68s），无回归（增量来自 teammates 新增的默认 skip 用例） |

## 2. 环境与版本信息

| 项目 | 值 |
|------|-----|
| 仓库 / 部署目录 | `G:\ai-diagnostic-platform` / `deploy/`（compose 项目名 `deploy`，卷前缀 `deploy_*`） |
| Milvus 镜像（修复后） | `milvusdb/milvus:v2.4.0`，镜像 ID `9500220e24ba`（本地已有镜像，无需联网拉取） |
| Milvus 镜像（旧） | `milvusdb/milvus:v2.3.12`，镜像 ID `ed82ec4b3da9`（已不再使用） |
| Milvus server 版本 | `v2.4.0`（`utility.get_server_version()` 实测） |
| pymilvus 客户端 | **2.5.4**（`backend/requirements.txt:14`；venv 与 Docker 镜像一致） |
| setuptools | **80.9.0**（`backend/requirements.txt:15` 已由 Lead 固定；修复 pymilvus 的 pkg_resources 依赖） |
| Embedding | `EmbeddingService` → `HashingEmbedder`（dim=512，本地哈希词形嵌入；镜像内无 torch/sentence-transformers，`EMBEDDING_PROVIDER=auto` 自动回退） |
| 本地 venv | `G:\ai-diagnostic-platform\.venv`，Python 3.12.13，pytest 8.3.3 |
| 后端镜像 / 容器 | `deploy-backend:latest` = `15b6c836e52b`（2026-11-12 17:39 构建）；backend 容器 17:40 起 `Up (healthy)` |
| Milvus 容器 | `ai-diagnostic-milvus`，2026-11-12 17:22 创建，`Up (healthy)`；端口 `19530`（gRPC）、`9091`（HTTP/metrics） |
| Milvus 资源占用（空载） | CPU ≈ 7.7%，内存 ≈ 178 MiB / 7.6 GiB；数据目录 `/var/lib/milvus` ≈ 273 MB（其中内嵌 etcd ≈ 123 MB，含 WAL） |
| 后端 Milvus 配置 | `MILVUS_ENABLED=true, MILVUS_HOST=milvus, MILVUS_PORT=19530, MILVUS_COLLECTION=knowledge_docs, MILVUS_DIM=${MILVUS_DIM:-512}, EMBEDDING_PROVIDER=${EMBEDDING_PROVIDER:-auto}, EMBEDDING_HASH_FALLBACK=true` |

## 3. 问题根因分析

### 3.1 根因 A：compose 未开启内嵌 etcd（服务一直 unhealthy 的直接原因）

旧 compose（`deploy/docker-compose.yml`，修复前）milvus 服务只有下列「调优类」env：

```yaml
environment:
  ETCD_AUTO_COMPACTION_MODE: revision
  ETCD_AUTO_COMPACTION_RETENTION: "1000"
  ETCD_QUOTA_BACKEND_BYTES: "4294967296"
  ETCD_SNAPSHOT_COUNT: "50000"
```

这些参数**不是内嵌开关**。Milvus 未开启 `ETCD_USE_EMBED=true` 时会按默认配置去连接
**外部 etcd**（`localhost:2379`），而本 compose 并未部署 etcd 服务 → 启动时无限重试：

```text
{"level":"warn","logger":"etcd-client","caller":"v3@v3.5.5/retry_interceptor.go:62",
 "msg":"retrying of unary invoker failed",
 "target":"etcd-endpoints://0xc00183a380/localhost:2379","attempt":0,
 "error":"rpc error: code = DeadlineExceeded ... dial tcp [::1]:2379: connect: connection refused"}
```

**补充实测（重要）**：旧镜像 v2.3.12 本身**也支持**内嵌 etcd（镜像内同样存在
`/milvus/configs/advanced/etcd.yaml` 与 `/usr/bin/curl`）。用 v2.3.12 补齐下面 4 个 env 后
同样可正常启动（临时端口 19532 实测 healthz 200）：

```powershell
docker run -d --rm --name milvus-v2312-embed-test `
  -e ETCD_USE_EMBED=true -e ETCD_DATA_DIR=/var/lib/milvus/etcd `
  -e ETCD_CONFIG_PATH=/milvus/configs/advanced/etcd.yaml -e COMMON_STORAGETYPE=local `
  -p 19532:19530 milvusdb/milvus:v2.3.12 milvus run standalone
# => host healthz 19092 -> 200（服务正常）
```

→ 结论：**根因是 compose 缺少内嵌 etcd 必需的 4 个 env，而不是 v2.3.12 不支持**（compose
注释「使用 etcd 内嵌模式」与实现不符）。本次仍升级到 v2.4.0，动机是：与 pymilvus 2.5.4
版本更接近、官方 standalone_embed 写法即 2.4.x、且该镜像本地已存在。

### 3.2 根因 B：healthcheck 用 wget，而镜像内只有 curl（假阴性）

旧 healthcheck：`wget -q -O /dev/null http://localhost:9091/healthz || exit 1`。
实测两个镜像内**均无 wget**（`/usr/bin/wget: No such file or directory`），只有 `/usr/bin/curl`。
因此即便 Milvus 已正常监听，healthcheck 也永远失败 → 容器永久 `unhealthy`。

### 3.3 根因 C：pymilvus 2.5.4 依赖 pkg_resources，setuptools>=81 已移除该模块

- `pymilvus==2.5.4` 的 `client/__init__.py:6` 仍 `from pkg_resources import ...`，
  而 setuptools 81+（本环境 83/84）已彻底移除 `pkg_resources`。
- 复现（venv 与重建前 Docker 镜像均相同）：

  ```text
  >>> import pymilvus
  ModuleNotFoundError: No module named 'pkg_resources'
  ```

- 后果：`backend/app/services/knowledge/vector_service.py` 模块级 `try/except ImportError`
  会把 pymilvus 视为「未安装」→ `_milvus_available=False` → 永远 keyword 回退，
  `/api/v1/vector/health` 恒为 `milvus_available=false`（实际 Milvus 完全正常）。
- 修复：`backend/requirements.txt` 固定 `setuptools==80.9.0`（80.9.0 仍带 pkg_resources，
  仅有 deprecation warning；官方 warning 原话：*pin to Setuptools<81*）。**注意 83.0.0 无效**。
- 需重建 backend/worker 镜像并重启容器才生效（`pip install -r requirements.txt` 在镜像构建阶段）。

### 3.4 根因 D：VectorService 两处代码 bug（导致即使 Milvus 可用，API 仍失败）

**D1 — `_ensure_collection()` 先 load 后建索引（Milvus 2.4+ 直接报错）**

旧代码顺序：`Collection(...)` → `collection.load()` → `create_index("embedding", ...)`。
Milvus 2.4+ 禁止在向量字段无索引时 load collection，报：

```text
[VectorService] Failed to ensure collection: <MilvusException: (code=700, message=index not found[collection=knowledge_docs])>
```

异常被 `except` 捕获后 `self._connected=False` → 进程内单例永久不可用；且被 create 出来的
空 collection 没有索引，后续每次初始化都在 `load()` 处失败 → `/vector/health` 永远 false。
（实测：修复前 `knowledge_docs` 存在、`indexes=[]`、`load()` 报 code=700、`num_entities=0`。）

**D2 — `search()` 结果格式化调用 `Hit.get(field_name, default)`（pymilvus 2.5.4 的 get 无 default 参数）**

旧代码：

```python
"id": hit.entity.get("doc_id", 0),
"content": hit.entity.get("content", ""),
```

pymilvus 2.5.4 `Hit.get(self, field_name)` 只接受 1 个参数，因此抛：

```text
[VectorService] Search error: Hit.get() takes 2 positional arguments but 3 were given
```

又被 `except Exception` 吞掉只打日志 → **即使向量已成功写入，search 永远返回 `[]`**。
这是与 D1 同等致命的 bug（API `use_hybrid=false` 会表现为 total_hits=0）。

## 4. compose 改动（修复前后）

> 说明：`deploy/docker-compose.yml` 工作区还有其它任务/Lead 的未提交改动，
> 本节只列**本任务负责的 milvus / worker 相关行**。

### 4.1 milvus 服务（`deploy/docker-compose.yml` 约 L65-L95）

```diff
   milvus:
-    image: milvusdb/milvus:v2.3.12
+    image: milvusdb/milvus:v2.4.0
     container_name: ai-diagnostic-milvus
     restart: always
     command: ["milvus", "run", "standalone"]
     ports:
       - "19530:19530"
       - "9091:9091"
     environment:
-      ETCD_AUTO_COMPACTION_MODE: revision
-      ETCD_AUTO_COMPACTION_RETENTION: "1000"
-      ETCD_QUOTA_BACKEND_BYTES: "4294967296"
-      ETCD_SNAPSHOT_COUNT: "50000"
+      # 内嵌 etcd（必须显式开启；缺省会去连外部 etcd 的 localhost:2379）
+      ETCD_USE_EMBED: "true"
+      ETCD_DATA_DIR: /var/lib/milvus/etcd
+      ETCD_CONFIG_PATH: /milvus/configs/advanced/etcd.yaml
+      # 本地存储，不依赖 minio/S3
+      COMMON_STORAGETYPE: local
     volumes:
       - milvus_data:/var/lib/milvus
     healthcheck:
-      test: ["CMD-SHELL", "wget -q -O /dev/null http://localhost:9091/healthz || exit 1"]
+      test: ["CMD-SHELL", "curl -sf http://localhost:9091/healthz || exit 1"]
       interval: 20s
       timeout: 15s
       retries: 10
       start_period: 120s
```

关键点：
1. 4 个内嵌 etcd env 来自官方 `standalone_embed.sh`；`COMMON_STORAGETYPE=local` 让 Milvus 数据落
   `/var/lib/milvus/data`，**不再依赖 MinIO/S3**（旧调优项 `ETCD_*` 是外部 etcd 的参数，内嵌模式下
   由 EtcdConfig 默认值接管，已清理，避免误导）。
2. healthcheck 改用镜像内真实存在的 `curl`。
3. 端口映射、`milvus_data` 卷挂载、网络 `ai-diagnostic-net` 均保持不变。

### 4.2 worker 服务（`deploy/docker-compose.yml` 约 L259-L264）

```diff
       MILVUS_COLLECTION: knowledge_docs
-      MILVUS_DIM: "1536"
+      # 与 backend 保持一致（默认 512，HashingEmbedder 输出维度）
+      MILVUS_DIM: "${MILVUS_DIM:-512}"
+      EMBEDDING_PROVIDER: "${EMBEDDING_PROVIDER:-auto}"
+      EMBEDDING_DIM: "${MILVUS_DIM:-512}"
+      EMBEDDING_HASH_FALLBACK: "true"
```

原因：worker 旧值 1536 与 backend 的 `${MILVUS_DIM:-512}`、`EMBEDDING_DIM` 不一致，
一旦 worker 未来真正做索引会出现维度错配（`VectorService` 直接 return 0）。现统一为 512。

## 5. 数据卷处理

- 旧卷 `deploy_milvus_data` 由 **v2.3.12** 创建（该容器从未 healthy，因此不可能有业务数据；
  实际内容仅为 etcd 连接失败的稀疏 WAL/日志）。
- Milvus 元数据不保证 2.3 → 2.4 直接复用，且无业务价值 → **直接删除重建**（任务已明确允许）。
- 操作记录（只删除 milvus 卷，其它卷未动）：

```powershell
docker rm -f ai-diagnostic-milvus              # 删除旧容器
docker volume rm deploy_milvus_data            # 旧卷（2.3.12 元数据，丢弃）
docker compose -f deploy/docker-compose.yml up -d milvus
# => Volume deploy_milvus_data Created
# => Container ai-diagnostic-milvus Started
```

- 当前卷内数据：`/var/lib/milvus` ≈ 273 MB（其中内嵌 etcd `/var/lib/milvus/etcd` ≈ 123 MB，
  含 WAL；`/var/lib/milvus/data` 为本地对象存储文件）。
- 升级/重建若需保留向量数据：必须先按官方版本升级路径升级，不能直接跨版本挂旧卷；
  生产建议定期备份 `milvus_data` 卷（standalone）或使用外部 etcd + S3/MinIO（可水平扩展）。

## 6. 启动与健康检查（命令 + 真实输出）

```powershell
# 1) 校验 compose 配置
cd G:\ai-diagnostic-platform\deploy
docker compose config --quiet            # => compose config OK

# 2) 启动
docker compose up -d milvus

# 3) 容器状态与端口（真实输出）
docker ps --filter 'name=ai-diagnostic-milvus' --format '{{.Names}} {{.Image}} {{.Status}} {{.Ports}}'
# ai-diagnostic-milvus milvusdb/milvus:v2.4.0 Up 12 seconds (healthy) 0.0.0.0:9091->9091/tcp, [::]:9091->9091/tcp, 0.0.0.0:19530->19530/tcp, [::]:19530->19530/tcp

# 4) host 侧健康检查（判定标准）
(Invoke-WebRequest -Uri http://localhost:9091/healthz -UseBasicParsing).StatusCode   # => 200
(Invoke-WebRequest -Uri http://localhost:9091/healthz -UseBasicParsing).Content      # => OK
(Test-NetConnection -ComputerName 127.0.0.1 -Port 19530).TcpTestSucceeded             # => True
```

内嵌 etcd 启动证据（`docker logs ai-diagnostic-milvus` 关键行，节选）：

```text
{"level":"info","caller":"embed/etcd.go:306","msg":"starting an etcd server","etcd-version":"3.5.5",
 "data-dir":"/var/lib/milvus/etcd", ... "listen-client-urls":["http://localhost:2479"], ...}
---Milvus Proxy successfully initialized and ready to serve!---
[INFO] [proxy/service.go:684] ["start Proxy http server"]
```

启动耗时：**约 12 秒**（`start_period: 120s` 足够；首次冷启动略长）。

## 7. pymilvus 2.5.4 ↔ Milvus server 2.4.0 兼容性实测

| 操作（pymilvus 2.5.4 → server 2.4.0） | 结果 |
|------|------|
| `connections.connect` + `utility.get_server_version()` | ✅ 返回 `v2.4.0`，连接耗时 0.08–0.75s |
| `utility.has_collection` / `list_collections` / `drop_collection` | ✅ 正常 |
| `Collection(name, schema)` + `create_index(IVF_FLAT, IP, nlist=128)` | ✅ 正常 |
| `collection.load()`（有索引） | ✅ 正常 |
| `insert`（INT64 主键 + FLOAT_VECTOR dim=512） | ✅ 5 条写入，`num_entities` 正确 |
| `flush` + `num_entities` | ✅ 一致 |
| `search`（IP / nprobe=16 / output_fields / limit） | ✅ 命中，自身向量 score=1.0；真实 API 场景 score=0.377964 |
| `delete(expr)` + `query` 验证 | ✅ 删除后 query 为空（`num_entities` 统计值不立即下降，属 Milvus 语义，见 §9 备注） |
| `drop_collection` | ✅ 清理成功 |
| `Collection.indexes` 读取 | ✅ 返回 `Index` 对象，可读到 `field_name=embedding` |
| `Hit.get(field_name)` | ✅ 可用（**注意 2.5.4 不接受 default 参数**，见根因 D2） |

**结论：pymilvus 2.5.4 与 server v2.4.0 的 gRPC 协议兼容，create/insert/flush/search/delete
全链路可用，未发现版本不兼容错误。** 唯一与版本相关的是 pymilvus 自带的
`pkg_resources` 依赖（根因 C，属 setuptools 问题而非 server 问题）与 `Hit.get` 签名差异（D2）。
后续 Docker 镜像站可用时建议把 server 升级到 v2.5.x，与客户端 minor 版本完全对齐。

## 8. VectorService 修复与真连验证

### 8.1 代码改动（`backend/app/services/knowledge/vector_service.py`）

**改动 1：`_ensure_collection()` 重排 + 新增幂等 `_ensure_vector_index()`**

```python
# 修复后核心顺序（伪代码）：
if not utility.has_collection(self._COLLECTION_NAME):
    self._collection = Collection(name, schema)      # 新建
else:
    self._collection = Collection(name)              # 已存在：先读 schema 维度
    self._dim = self._read_collection_dim() or self._dim
self._ensure_vector_index()                          # ① 幂等：无 embedding 索引则 create_index(IVF_FLAT/IP/nlist=128)
self._collection.load()                              # ② 有索引后再 load
```

`_ensure_vector_index()` 通过遍历 `collection.indexes`（`index.field_name == "embedding"`）
判断索引是否已存在；对历史遗留的「已创建但无索引」collection 会自动补建索引（自愈）。

**改动 2：`search()` 结果格式化去掉 `Hit.get` 的 default 参数**

```python
# 修复前（pymilvus 2.5.4 下抛 TypeError，search 永远返回 []）
"id": hit.entity.get("doc_id", 0),
"content": hit.entity.get("content", ""),

# 修复后
"id": int(hit.entity.get("doc_id") or 0),
"score": float(hit.score),
"content": hit.entity.get("content") or "",
```

### 8.2 venv 真连验证（真实 Milvus server v2.4.0，EMBEDDING_PROVIDER=hash / dim=512）

修复前损坏态（旧 backend 创建的无索引空 collection）：

```text
collections: ['knowledge_docs']
num_entities: 0
indexes: []
load error: <MilvusException: (code=700, message=index not found[collection=knowledge_docs])>
```

修复后逐项验证（venv 直接调用 `VectorService`，连 localhost:19530）：

```text
[A] 修复后首次初始化（自愈旧 collection）
available = True
connected = True
collection_info.num_entities = 0

[B] index_document / search / delete_document
chunks_indexed = 1
num_entities(after index) = 1
search("USB 超时") = [(987654, 0.437595, 'USB 设备超时无响应，检查线缆与驱动；必要时更换 USB ')]
delete_document = True
pymilvus query("doc_id == 987654") -> data: []      # 确认真实删除

[C] 第二次初始化（幂等，已有索引导航）
available = True

[D] 删除旧空 collection，走全新创建路径
fresh available = True
fresh indexes = [('embedding', 'embedding',
                  {'metric_type': 'IP', 'index_type': 'IVF_FLAT', 'params': {'nlist': 128}})]
search on empty collection = []                     # 空库不报错
num_entities = 0
FINAL: available = True
```

## 9. API 端到端验证（真实运行中的 backend 容器，新镜像）

前置：Lead 重建镜像并 `up -d --no-deps backend worker` 重启，backend 容器 `Up (healthy)`。

| # | 请求 | HTTP | 关键返回 |
|---|------|------|----------|
| 1 | `GET /api/v1/vector/health` | 200 | `milvus_available=true, milvus_enabled=true`；`collection.name=knowledge_docs, dim=512`；`embedding_provider=EmbeddingService` |
| 2 | `POST /api/v1/vector/embed` `{"text":"USB 设备超时"}` | 200 | `dimension=512`，`norm=1.0`（HashingEmbedder 生效） |
| 3 | `POST /api/v1/vector/index` `{"doc_id":987654,"content":"USB 设备超时无响应，检查线缆与驱动；必要时更换 USB 端口。"}` | 200 | `chunks_indexed=1, success=true` |
| 4 | `POST /api/v1/vector/search` `{"query":"USB 超时","top_k":5,"use_hybrid":false}` | 200 | `strategy=vector_only, total_hits=1`；`results[0] = {id:987654, score:0.37796446681022644, source:"vector"}` |
| 5 | `GET /api/v1/vector/status` | 200 | `vector_service_available=true, milvus_enabled=true` |
| 6 | `POST /api/v1/vector/search` `use_hybrid=true` | 200 | `strategy=hybrid, total_hits=2`（keyword 命中 doc_id=11 `source=keyword` + vector 命中 987654 `source=vector`，融合排序） |
| 7 | pymilvus 侧确认 | — | `knowledge_docs` 可 query 到 doc_id=987654（1 条）；`num_entities>0` |
| 8 | 清理 | 200 | `DELETE /api/v1/vector/index/987654` → `{"success":true}`；随后 pymilvus `query("doc_id == 987654")` → `[]` |

`verify` 脚本完整模式原始输出（节选）：

```text
[PASS] pymilvus 连接 Milvus  — localhost:19530, 耗时 0.59s
[INFO] 服务端版本  — v2.4.0
[PASS] 创建临时 collection + IVF_FLAT/IP 索引  — milvus_verify_tmp
[PASS] insert + flush  — num_entities=3
[PASS] search 命中  — id=9876540002 doc_id=987654 score=0.400000, ...
[PASS] delete 表达式删除并 query 确认  — 剩余 0 条
[PASS] knowledge_docs 向量维度与配置一致  — dim=512, 期望=512
[PASS] GET /api/v1/vector/health 返回 200  — HTTP 200
[PASS] milvus_available=true  — milvus_available=True, collection={'name': 'knowledge_docs', ...}
[PASS] embed dimension=512  — 512
[PASS] chunks_indexed>0  — chunks_indexed=1
[PASS] strategy=vector_only  — vector_only
[PASS] 纯向量搜索有命中  — total_hits=1
[PASS] 纯向量搜索 Top1 命中测试文档  — id=987654, score=0.37796446681022644
[PASS] knowledge_docs 中可查到测试向量  — 1 条
[PASS] knowledge_docs 实体数 > 0  — num_entities=3
[PASS] 混合搜索返回合法 strategy  — hybrid
------------------------------------------------------------------------------
汇总: PASS=26 FAIL=0 SKIP=0 INFO=4
结论: PASS（真实向量链路验证通过）
```

backend 容器日志（真实运行）：

```text
[VectorService] Collection 'knowledge_docs' exists (dim=512), ensuring index
[VectorService] Connected to Milvus at milvus:19530
[VectorService] Indexed doc 987654: 1 chunks
[VectorService] Search completed: embed=0.00s search=0.01s hits=1
[VectorService] Deleted vectors for doc 987654
```

### 备注

- **`num_entities` 语义**：Milvus 的 `num_entities` 是统计值，`delete` + `flush` 后不会立即
  下降（需 compaction），因此「删除是否生效」用 `query("doc_id == X")` 验证（实测为空）。
- **`embedding_provider` 名称**：`/api/v1/vector/health` 返回 `EmbeddingService`（`EmbeddingService`
  是包装类，其内部激活实现是 `HashingEmbedder`）。任务预期值 `HashingEmbedder` 与实际返回的
  包装类名不同，但 dim=512 + norm=1.0 + 日志 `EMBEDDING_PROVIDER=hash，使用哈希嵌入兜底`
  证明实际就是 HashingEmbedder；如需显示内部实现名，可把路由改为读取
  `embedder.provider_name`（本次未改该文件，非阻塞项）。
- API 请求体为中文时，PowerShell `Invoke-WebRequest` 默认编码会把中文变 `?`；**取证据时须用
  UTF-8 字节体**（或用本项目 `verify` 脚本 / httpx / curl），否则 hash 嵌入结果会失真。
- api 端到端测试数据已清理：`knowledge_docs` 现存活动实体为 0（`query` 为空），但统计值
  `num_entities=3`（历史 delete 未 compaction），属正常现象。

## 10. 测试、脚本与全量回归

### 10.1 新增集成测试（默认跳过）

`backend/tests/integration/services/test_milvus_real.py`：

- 门槛：`RUN_REAL_MILVUS=1` 才执行；否则模块级 `pytestmark.skipif` 跳过（默认 3 skipped，不污染基线）。
- 自动 skip：pymilvus 导入失败（如 setuptools 未固定）或 Milvus 不可连接时 skip 而非失败。
- 用例：
  1. `test_real_connection` — 真实连接 + 版本/collection 列表读取；
  2. `test_insert_flush_search_and_cleanup` — insert → flush → search（Top1 自身 score>0.99）
     → delete 表达式 → query 确认删除；临时 collection 随机名，`finally` 中 drop；
  3. `test_knowledge_docs_collection_if_present` — 业务 collection 存在时校验维度 512；
     兼容旧 bug 遗留的无索引 collection（skip 而非误报）。

```powershell
cd G:\ai-diagnostic-platform\backend
..\.venv\Scripts\python.exe -m pytest tests/integration/services/test_milvus_real.py -v
# 默认：3 skipped
$env:RUN_REAL_MILVUS='1'; ..\.venv\Scripts\python.exe -m pytest tests/integration/services/test_milvus_real.py -v
# 真实：3 passed in 33.50s
```

### 10.2 可复现验证脚本

`backend/scripts/verify/milvus_e2e.py`（可重复运行，临时 collection 即测即清）：

```powershell
# 仓库根目录 / backend 目录均可
G:\ai-diagnostic-platform\.venv\Scripts\python.exe backend\scripts\verify\milvus_e2e.py
# 只测 pymilvus 直连（后端未就绪时）
G:\ai-diagnostic-platform\.venv\Scripts\python.exe backend\scripts\verify\milvus_e2e.py --skip-api
```

覆盖：pymilvus 直连（版本/collection）→ 临时 collection create/index/insert/flush/search/
delete/drop → `knowledge_docs` 维度 → API 全链路（health/embed/index/search×2）→
pymilvus 侧确认实体 → 清理。退出码：0=通过（API 不可达按 SKIP）/1=有 FAIL/2=前置不满足。

### 10.3 全量 pytest 回归

```powershell
cd G:\ai-diagnostic-platform\backend
..\.venv\Scripts\python.exe -m pytest -q
# 473 passed, 11 skipped, 1 warning in 28.68s
```

- 基线：466 passed / 1 skipped；本次 **473 passed / 11 skipped**，**无回归**。
- 增量说明：passed +7、skipped +10 来自本任务与 teammates（minio/pdf 等）新增的默认 skip
  真实集成用例（`test_milvus_real.py` 默认 3 skipped 即在此列），默认全量测试仍不依赖任何外部服务。

## 11. 可复现命令清单（汇总）

```powershell
# ── Milvus 服务 ──
cd G:\ai-diagnostic-platform\deploy
docker compose config --quiet
docker compose up -d milvus
docker ps --filter 'name=ai-diagnostic-milvus' --format '{{.Names}} {{.Image}} {{.Status}} {{.Ports}}'
(Invoke-WebRequest -Uri http://localhost:9091/healthz -UseBasicParsing).StatusCode   # 200
(Test-NetConnection -ComputerName 127.0.0.1 -Port 19530).TcpTestSucceeded            # True

# ── pymilvus 直连 + API 端到端（可重复）──
cd G:\ai-diagnostic-platform
.venv\Scripts\python.exe backend\scripts\verify\milvus_e2e.py

# ── 真实集成测试（默认跳过）──
cd backend
$env:RUN_REAL_MILVUS='1'; ..\.venv\Scripts\python.exe -m pytest tests/integration/services/test_milvus_real.py -v
Remove-Item Env:RUN_REAL_MILVUS

# ── 全量回归 ──
..\.venv\Scripts\python.exe -m pytest -q

# ── 镜像/依赖修复（Lead 执行）：requirements.txt setuptools==80.9.0 后重建 ──
docker compose -f G:\ai-diagnostic-platform\deploy\docker-compose.yml build backend worker
docker compose -f G:\ai-diagnostic-platform\deploy\docker-compose.yml up -d --no-deps backend worker
docker exec ai-diagnostic-backend python -c "import pymilvus, setuptools; print(pymilvus.__version__, setuptools.__version__)"
```

## 12. 生产建议

1. **资源**：standalone 空载实测 ≈ 178 MiB / 7% CPU，但索引构建/查询/数据增长会明显上涨；
   生产建议至少 4C/8G 起，并为 `/var/lib/milvus` 预留 SSD 空间（含 etcd WAL 与本地对象存储）。
2. **内嵌 etcd 仅适合单机/开发**：生产规模或高可用请切换 Milvus Cluster（3 节点外部 etcd +
   MinIO/S3 + Pulsar/Kafka），并将 `COMMON_STORAGETYPE` 改为 `remote`（配 `MINIO_*`/S3）。
   单机时务必持久化 `milvus_data` 卷并备份 `/var/lib/milvus/etcd`（元数据）与
   `/var/lib/milvus/data`（对象数据）。
3. **不要随意升级挂旧卷**：Milvus 跨 minor 升级需按官方升级路径（先备份、逐版本升级），
   本次为无业务数据的一次性环境，直接重建卷。
4. **版本对齐**：pymilvus 与 Milvus server 尽量保持同 minor；当前 client 2.5.4 / server 2.4.0
   实测兼容，镜像站可用后建议升级 server 到 2.5.x。若升级 pymilvus，注意重新评估
   `pkg_resources` 依赖（届时可移除 `setuptools==80.9.0` 的 pin）。
5. **healthcheck / 监控**：使用镜像内存在的 `curl -sf http://localhost:9091/healthz`；
   监控 `9091/healthz`、`9091/metrics` 与容器内存，`start_period` 不要低于 60s。
6. **网络与安全**：19530 gRPC 默认无认证（`MILVUS_USER/PASSWORD` 为空），生产应只在内网暴露，
   或开启 Milvus 认证/网络策略；不要将 19530 直接暴露公网。
7. **Embedding 与维度**：当前 `EMBEDDING_PROVIDER=auto` + 无 torch → HashingEmbedder(dim=512)。
   生产切换 BGE/API embedding 时必须保证 `EMBEDDING_DIM == MILVUS_DIM`，否则 VectorService 会
   因维度不匹配直接返回 0/空（collection 维度过期需删表重建）。HashingEmbedder 是词形哈希、
   非语义，仅用于本地/测试链路验证。
8. **worker 容器健康检查**：`backend/Dockerfile` 的 `HEALTHCHECK` 对所有镜像生效，但 worker 命令
   不是 HTTP 服务，容器会显示 `unhealthy`（假阴性，本次未改动）。建议为 worker 覆盖 healthcheck
   （如 `CMD pgrep -f "python -c"`）或从镜像中拆分注释。
9. **MinIO 依赖**：Milvus 采用 `COMMON_STORAGETYPE=local` 后与 MinIO 完全解耦（MinIO 仅服务
   日志/图片对象存储）；若生产想复用 MinIO 作为 Milvus 对象存储，需改 remote 模式并配置凭据，
   同时注意 Milvus 对 S3 兼容性的要求。

## 13. 遗留问题 / 备注

> 2026-11-12 晚更新：以下 1、2、5 已在「§7 遗留问题治理」中修复（详见
> [Environment-Real-Verification.md §7](../Environment-Real-Verification.md)）。

1. ~~`worker` 容器 `unhealthy`~~ → **已修复**：compose 为 worker 显式 `healthcheck.disable=true`
   （镜像 HEALTHCHECK 仅适用于 backend 的 HTTP /health，worker 为 keep-alive 占位进程）。
2. ~~`/api/v1/vector/health` 的 `embedding_provider` 显示包装类 `EmbeddingService`~~ → **已修复**：
   路由改用 `get_embedder().provider_name`，返回真实 provider（容器内默认 `HashingEmbedder`，
   启用 BGE 镜像/配置时为 `BGEEmbedder`）。另同步修复 `_ensure_embedding` 硬编码 10s 超时 +
   永久降级 latch（改读 `settings.EMBEDDING_LOAD_TIMEOUT`、超时后下次调用可继续加载/回填、失败可重试，
   新增 10 个单测）。
3. v2.5.4 Milvus 镜像拉取：Docker Hub 直连被墙、镜像站（docker.1ms.run 429 / docker.xuanyuan.me
   403）失败，本次使用本地既有 v2.4.0；待网络条件允许可平滑升级并与 pymilvus 2.5.4 完全对齐。
4. `knowledge_docs` 当前无活动数据（测试向量已清理），统计值 `num_entities=3` 为 delete 未 compaction
   的历史统计，属 Milvus 正常语义；后续索引真实文档后会自动增长。
5. ~~本次未修改 `backend/requirements.txt` 与 `vector.py`~~ → 已在治理轮补齐：
   `requirements.txt` 固定 `setuptools==80.9.0` + `reportlab==5.1.0`；`vector.py` provider 名修复；
   `vector_service.py` 超时/重试修复。均未执行 `git commit`（由人工审阅提交）。
