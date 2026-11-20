# 部署环境验证清单（P0/P1/P2 遗留项）

本地测试覆盖的是**逻辑正确性**（纯函数、状态机、假 Milvus、临时文件），
下面这些只能在真实环境验证。每项都给了命令、期望结果和"不通过时记录什么"，
验证完请把结果贴回对应条目。

> **V1/V2 已在 2026-11-19 确认**（详见下方「V1/V2 已确认前提」）。
>
> 共同前提：`backend/.env` 已按 `.env.example` 配置；
> `MILVUS_ENABLED=true`、`REDIS_URL` 可用、`MINIO_ENABLED=true`（如涉及存储项）。
> 所有命令在 `backend/` 目录下执行，使用部署环境的 Python 解释器。

---

## V1/V2 已确认前提（2026-11-19）

| 项 | 结论 |
| --- | --- |
| 现有数据 | 开发阶段，全部为测试数据，可删除重建 |
| 集合策略 | **不并行保留旧集合**，直接重建 `knowledge_chunks_v3` |
| Milvus 版本 | **v2.4.0**，支持 `chunk_type in [...]`，无需单值降级 |
| Embedding | 先用**本地 BGE**（`bge-large-zh-v1.5`，1024 维，CPU） |
| 知识库形态 | AI 润色的标准 Markdown；按标题切章、超长小节按段落切窗、过滤目录/前言 |
| 停服窗口 | 不需要；提问只使用「提问前已入库」的知识，增量不影响在途提问 |
| 部署现状 | 部署机尚未安装依赖/MinIO/Milvus；**测试环境可操作，生产改动需再确认** |
| 验收用例 | 提问「进出站日志中搜索什么」→ Top-3 章节标题须含「查看设备是否有进出站」（不限定文档：FAQ 与《线路》存在同内容副本，按文档名判定会把正确召回判失败） |

### 一条命令跑完 V1+V2

```bash
cd backend
python -m scripts.verify_v3_cutover   --question "进出站日志中搜索什么"   --expect-doc FAQ --expect-section "第 5 节"
```

输出 `reports/v3_cutover.json`，`verdict` 为 `ready` 才可切流量；脚本会断言：
所有命中 `chunk_type=section` 且 `source=knowledge`，并且验收用例命中《FAQ》第 5 节。

## V1 集合 v3 重建与回填（**破坏性，必须最先做**）

P2 把集合从 `knowledge_sections_v2` 升级为 `knowledge_chunks_v3`，
新增 `chunk_type / source / ts` 三个字段。Milvus 不能给已有集合加字段，必须重建。

```bash
export MILVUS_COLLECTION=knowledge_chunks_v3

python scripts/reindex_knowledge.py --check      # 1. 预检
python scripts/reindex_knowledge.py --dry-run    # 2. 只算不算写
python scripts/reindex_knowledge.py              # 3. 真正回填
python scripts/reindex_knowledge.py --verify     # 4. 抽样检索
```

| 检查点 | 期望 |
| --- | --- |
| `--check` | 报告 embedding 不是哈希（`provider=bge/api`）、维度 1024、集合 schema 兼容 |
| `--dry-run` | 输出待处理章节数，与知识库文档规模量级一致 |
| 回填 | 无 `维度不一致` / `schema 不兼容` / `哈希向量拒绝写入` 报错 |
| `--verify` | 每条查询都能召回，分数不是全 0（全 0 = 集合空或过滤写错） |

**不通过时的关键信息**：完整报错行、`MILVUS_COLLECTION` 实际值、集合 `num_entities`。

回滚：把 `MILVUS_COLLECTION` 改回旧集合名并重启 backend（代码会因字段缺失拒绝启动，
所以回滚必须同时回滚代码版本）。

---

## V2 Milvus 的 `chunk_type` 过滤语义

代码里用的是 `chunk_type in ["section"]`。这个表达式在本项目的 Milvus 版本上是否正确解析，
本地无法验证（用的是假 collection）。

```bash
python - <<'PY'
from app.services.knowledge.vector_service import VectorService, KNOWLEDGE_CHUNK_TYPES
svc = VectorService()
print("collection:", svc.collection_name, "dim:", svc.dimension, "schema_error:", svc.schema_error)
hits = svc.search("4G 注册失败", top_k=5, chunk_types=list(KNOWLEDGE_CHUNK_TYPES))
for h in hits:
    print(round(h["score"], 4), h["chunk_type"], h["source"], h["section"][:30])
PY
```

| 检查点 | 期望 |
| --- | --- |
| 返回行 | 每条 `chunk_type` 都是 `section`，没有 `error` / `template` |
| `source` | 都是 `knowledge`（日志块是 `log:<id>`） |
| 不报错 | 若报表达式语法错误，说明 Milvus 版本不支持该 `in` 写法，需改用 `chunk_type == "section"` |

**不通过时**：贴 Milvus 版本（`milvus-server --version` 或镜像 tag）+ 完整异常。

---

## V3 100MB 日志端到端

```bash
# 1. 造一条大文件或直接用真实日志
ls -lh /path/to/100mb.log

# 2. 通过 API 上传（走真实队列）
curl -s -F "file=@/path/to/100mb.log" -H "Authorization: Bearer <token>" \
     http://localhost:8000/api/v1/logs/upload | tee /tmp/upload.json

# 3. 轮询进度
LOG_ID=$(python -c "import json;print(json.load(open('/tmp/upload.json'))['id'])")
watch -n 5 "curl -s -H 'Authorization: Bearer <token>' \
  http://localhost:8000/api/v1/logs/\$LOG_ID/ingest-status"
```

| 检查点 | 期望 | 观测方式 |
| --- | --- | --- |
| 上传响应 | **秒级返回**（不等预处理） | 上传耗时 |
| 分片数 | ≈ 文件大小 / 50MB | `stages.prepare` + 日志 `chunks=N` |
| 各阶段 | `succeeded`，无 `failed` | `stages` 每项 `failed=0` |
| 内存峰值 | worker 容器 < 1GB（分片处理，不应整体读入） | `docker stats` |
| 产物 | `data/raw/_ingest/{LOG_ID}/` 下有 `normalized_*.jsonl.gz`、`templates.json`、`compressed.bundle.jsonl.gz` | `du -sh` |
| 证据块 | `index` 阶段 `error_chunks + template_chunks` > 0 且 ≤ 2000 | task summary |

**不通过时**：`ingest-status` 完整 JSON、worker 日志里第一个 `[ingest]` 报错行、
`docker stats` 峰值。

---

## V4 Drain3 模板质量抽样

模板聚类是"能用"还是"没用"，只能人工看。

```bash
python - <<'PY'
import json
p = "data/raw/_ingest/<LOG_ID>/templates.json"
data = json.load(open(p))
print("templates:", data["templates"], "lines:", data["total_lines"])
for tid, count in data["top"][:20]:
    print(count, tid)
PY
```

| 检查点 | 期望 |
| --- | --- |
| 模板数 / 行数 | 比值合理（10 万行日志模板数应在几十~几千，不是上万） |
| top20 | 同一类日志（如多次 `register failed ret=-1/-2`）应落在**同一模板** |
| 前缀 | 模板 id 以 `d` 开头（= Drain3 生效）；若是 `h:` 说明退化成哈希了 |

**不通过时**：`template_source()` 返回值 + top20 原文。

---

## V5 Reranker 实际增益（A/B）

P0 把 `bge-reranker-base` 接回了主路径，但**没有在真实样本上量化过**。

```bash
# A：关闭精排
RERANKER_ENABLED=false python -m pytest tests/regression -q -m golden

# B：开启精排
RERANKER_ENABLED=true  python -m pytest tests/regression -q -m golden
```

比对 `backend/reports/golden_report.json` 的 `recall_at_5` / `mrr`。

| 检查点 | 结论 |
| --- | --- |
| B 明显优于 A | 精排保留在主路径 |
| B ≈ A | 精排是"白付延迟"，考虑只在长候选（top_k>20）时启用 |
| B 更差 | 模型与语料不匹配，需换 `bge-reranker-large` 或关闭 |

前置：黄金集里有 ≥20 条已审核（`approved`）样本，否则回归会 skip。

---

## V6 MinIO 布局与预签名

```bash
python - <<'PY'
from app.services.diagnostics.log_storage import LogStorage
s = LogStorage()
print("remote_available:", s.remote_available, "bucket:", s.bucket)
url = s.presigned_get("minio://<bucket>/<key>")
print("ttl_seconds:", s.presign_ttl, "\nurl:", url[:120])
PY
```

| 检查点 | 期望 |
| --- | --- |
| 对象布局 | `logs/p{project_id}/{yyyymmdd}/{uuid}_{filename}` |
| 预签名 TTL | 900 秒（15 分钟），过期后返回 403 |
| 桶权限 | 匿名 GET 返回 403（桶必须私有） |
| 下载 | 预签名 URL 能拿到完整文件，大小与原文件一致 |

---

## V7 黄金集回归 CI（自托管 runner）

`.github/workflows/golden-regression.yml` 需要标签为 `ai-diag` 的自托管 runner，
且 runner 上能访问 Milvus / MinIO / BGE 模型 / DeepSeek key。

| 检查点 | 期望 |
| --- | --- |
| runner 在线 | GitHub → Settings → Actions → Runners 显示 Idle |
| 手动触发 | `workflow_dispatch` 跑通，报告 artifact 可下载 |
| push 触发 | 工作流已加 `push`；runner 就绪后把仓库变量 `GOLDEN_RUNNER_READY` 设为 `true` |
| 门槛 | recall@5 ≥0.85、hit@30 ≥0.90；**不通过时改代码或标 superseded，不允许调阈值** |

---

## 结果回填模板

```
V1 集合回填：通过 / 不通过（报错：）
V2 chunk_type 过滤：通过 / 不通过（Milvus 版本：）
V3 100MB 端到端：通过 / 不通过（分片数=, 峰值内存=, 总耗时=）
V4 Drain3 质量：通过 / 不通过（模板数/行数=, 是否 d 前缀=）
V5 精排 A/B：A= recall/MRR, B= recall/MRR, 结论=
V6 MinIO：通过 / 不通过（TTL=, 匿名 GET=）
V7 回归 CI：通过 / 不通过（runner=）
```

未通过项按"不通过时记录什么"补齐信息，我再据此定位——这些现象在本地无法复现，
缺失信息会导致只能靠猜。
