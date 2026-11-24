# 知识库问答与检索质量优化路线（P1~P3）

Version: 1.0
Status: P0 已完成，P1~P3 按本文执行

---

# 目录

1. 背景与现状基线
2. P0 已完成（真向量基线）
3. P1 带日志提问主链路
4. P2 异步深度处理
5. P3 检索基础设施与运维
6. 定稿决策清单（不可随意变更）
7. 验收指标总表
8. 执行纪律

---

# 1. 背景与现状基线

## 1.1 问题

- Embedding 使用哈希兜底（`HashingEmbedder`），属于「词形哈希」而非语义向量，
  检索定位准确度存在硬天花板；且该兜底能通过健康检查，导致问题被长期掩盖。
- 集合按「整篇文档 + 512 维」建索引，长文档（FAQ 汇总）被长度归一化稀释，
  正确章节即使完全对题也排不进前列。
- Cross-Encoder 精排只挂在未被调用的 `RAGService` 上，线上回答从未做精排。

## 1.2 现状链路（P0 完成后）

```
提问 → 知识库检索（章节级 BM25 + 向量 → RRF → 精排 Top5）
     → 组装知识上下文 → DeepSeek 回答 → 落检索轨迹（retrieval_traces）
```

日志附件场景（P1 目标）目前尚未接通：附件只做解析，没有「按时间窗 + 知识库关键字定位」链路。

---

# 2. P0 已完成（真向量基线）

| 能力 | 实现位置 | 关键参数 |
| --- | --- | --- |
| 私有 BGE 语义嵌入 | `services/knowledge/embedding.py` | `bge-large-zh-v1.5`，1024 维，batch=32，CPU |
| 章节级集合 | `services/knowledge/vector_service.py` | `knowledge_chunks_v3`，`id/doc_id/chunk_index/content(8192)/title/section/content_hash/chunk_type/source/ts/embedding` |
| 索引与度量 | 同上 `build_index_params` | HNSW(M=32, efConstruction=256) + COSINE，查询 ef=64 |
| 章节级混合检索 | `services/knowledge/section_search.py` | BM25Plus + 向量 → RRF(k=60)，统一 `SectionChunk.key` 口径 |
| 精排 | `services/knowledge/rerank_service.py` | `bge-reranker-base`，候选取前 30，失败静默跳过 |
| 回填 | `services/knowledge/reindex_service.py` + `scripts/reindex_knowledge.py` | 四道守卫，断点续跑，`--verify` 抽样检索 |
| 检索轨迹 | `services/quality/trace_service.py` → `retrieval_traces` | 召回候选/结论分支/耗时/流水线版本 |
| 回归黄金集 | `services/quality/golden_sample_service.py` + `/quality/golden-samples` | 按提交人角色的审核链 + `sample_reviews` 审计 |

**P0 上线前置（必做，否则向量检索为空）**：重建集合 → 回填 → `--verify` → 切流量。

---

# 3. P1 带日志提问主链路

目标：用户在对话中提问并附上日志文件，系统「先查知识库要点 → 用要点关键字按时间窗定位日志 → 给出结论」。

## 3.0 进度

| 步骤 | 状态 | 落地位置 |
| --- | --- | --- |
| 1 槽位闸门 | ✅ | `chat/slot_gate.py` + `ChatService._check_log_slots` |
| 2 时间轴扫描 | ✅ | `diagnostics/log_timeline.py` |
| 3 候选时段 | ✅ | `diagnostics/error_windows.py` + `chat/time_gate.py` |
| 4 关键字定位 | ✅ | `chat/log_patterns.py` / `log_locator.py` / `log_evidence.py` |
| 5 回答组装 | ✅ | `chat/log_context.py` + `DiagnosticChatAgent._build_log_evidence_text` |
| 6 轨迹落库 | ✅ | `quality/trace_service.py`（含 patterns/blocks） |

## 3.1 步骤 1：槽位闸门

| 项 | 内容 |
| --- | --- |
| 输入 | 用户提问文本 + 附件 |
| 必填槽位 | 城市、设备名、现象描述、时间点（北京时间）、附件 |
| 处理 | LLM 结构化抽取 + 规则兜底（正则抓时间/型号）；相对时间（"昨天下午3点"）解析为北京时间绝对值并在回答首句复述 |
| 缺槽处理 | **一次性追问全部缺失项**，不允许默认"现在"；保存 `pending_context` 以便补答后续跑 |
| 验收 | 缺槽时正确追问率 100% |

## 3.2 步骤 2：时间轴扫描（与知识库检索并行）

| 项 | 内容 |
| --- | --- |
| 目的 | 校验「日志里到底有没有这个时间」，并产出偏移表让后续只读时间窗 |
| 处理 | 单遍流式扫描：解码 → 逐行抽时间戳 → 写 `manifest.json`（`min_ts/max_ts/hour_offsets/module_stats/template_topN`）+ 规范化中间态分片回写 MinIO |
| 自适应 | `>20MB` 建偏移表走 Range GET；`≤20MB` 整读一次内存匹配 |
| 时区 | 固定北京时间 +08:00，不做 UTC 推断 |
| 验收 | 100MB 扫描 P95 < 10s；时间不存在时 100% 直接告知 |

## 3.3 步骤 3：时间不匹配 → 候选时段卡片

| 项 | 内容 |
| --- | --- |
| 触发 | 用户时间点不在 `[min_ts, max_ts]` 内 |
| 呈现 | 3 个候选时段（异常聚集时段）+「其他」，每项带时段、错误计数、Top 模板摘要 |
| 选择后 | 时间窗收窄为「所选时段 ±5min」 |
| 兜底 | 最多两轮；仍未匹配 → 按日志覆盖范围做一次全局异常扫描并说明限制 |
| 验收 | 不重叠时正确提示率 ≥95%；候选卡片生成不阻塞首 token 预算 |

## 3.4 步骤 4：关键字定位（模式来自知识库）

| 项 | 内容 |
| --- | --- |
| 关键字来源 | **只来自知识库命中章节正文**；不维护独立错误关键字清单 |
| 抽取 | 输入问题 + Top5 章节 → 输出 `diagnosis_points` + `log_patterns`（`at_cmd/param_name/module_id/literal/regex`） |
| 约束 | 每条 pattern 必须能在章节原文溯源，禁止模型自造；带 `source_chunk` 以便引用 |
| 缓存 | 按 `(知识库版本 hash, 问题单元)` 缓存 |
| 匹配 | 只读时间窗分片 → 多模式并集 → 命中行扩 ±20 行 → 重叠合并 → Top30 块 |
| 零命中三态 | 全部未命中 → 明说「该时段无知识库所列关键点痕迹（列出关键点）」；部分命中 → 正常答 + 标注缺失项；知识库无条目 → 只给日志概览 |
| 验收 | 故障点在 Top30 块内 ≥90%；零命中必须给「关键点未命中」表述 |

## 3.5 步骤 5：回答组装

- 顺序：知识库要点 + 命中日志块（行号/时间/来源章节）+ 约束（不得超出命中证据）→ DeepSeek SSE
- 引用精确到「文档·章节 + 日志行号区间」
- 全绿时段必须给「设备正常」结论，不得输出「未找到相关内容」

## 3.6 步骤 6：轨迹落库

- 每次提问写 `retrieval_traces`（槽位/召回/pattern/日志块/耗时/结论分支）
- 无轨迹则黄金集无法标注、历史对话无法复盘 —— 这是 P1 的硬前置

---

# 4. P2 异步深度处理

目标：首答不等深度处理，但追问、聚合、审计需要完整产物。

## 4.0 进度

| 项 | 状态 | 落地位置 |
| --- | --- | --- |
| 队列骨架（可靠性四参数 + 双队列） | ✅ | `worker/celery_app.py` |
| 任务状态机 / 幂等 | ✅ | `worker/task_state.py` |
| 处理链路 prepare→parse→template→compress→finalize | ✅ | `worker/tasks.py` |
| 上传接线 + 进度查询 | ✅ | `LogService._enqueue_ingest`、`GET /logs/{id}/ingest-status` |
| Drain3 真实依赖与模板库持久化 | ✅ | `ingest_service.py`（`FilePersistence` → `_ingest/drain3_state.bin`） |
| 分块入 Milvus（`chunk_type=error/template`） | ✅ | `diagnostics/log_indexer.py` + `VectorService.index_log_chunks` |
| 产物入对象存储 | ✅ | `diagnostics/artifact_store.py`（`ingest/{log_id}/…`，MinIO 优先、本地兜底） |
| 模板库跨进程锁 | ✅ | `ingest_service._drain_file_lock`（O_CREAT 锁文件 + 陈旧锁清理） |

## 4.1 队列骨架

- Celery + Redis（`CELERY_BROKER_URL`/`RESULT_BACKEND` 已配置，`worker` 容器当前是 keep-alive 占位）
- 必设：`acks_late=True`、`prefetch_multiplier=1`、`visibility_timeout ≥ 单步最长耗时×2`、`task_time_limit` 兜底
- 队列分离：`parse/compress`（CPU，并发=核数/2）、`embed`（限并发 2）

## 4.2 任务拆分

`prepare`（解包归一化 + 切片）→ `parse_chunk ×N` → `template`（Drain3）→ `compress` → `chunk_embed` → `finalize`

## 4.3 幂等 / 重试 / 失败

- 任务键 `sha256(content_hash + pipeline_version + stage)`；DB 唯一约束 `(log_id, stage, chunk_no)` 做 claim
- 对象 key 与 Milvus pk 确定性，重跑覆盖写；**同文件跑两次产物 hash 必须一致**
- 只重试网络/5xx/429，指数退避 + jitter，上限 5 次；格式/编码类直接 failed
- 死信表 + 失败样本对象；管理端支持「从失败阶段重跑」

## 4.4 预处理顺序（固定）

解码解包 → 行级解析 → 噪声过滤 → 打码归一化 → Drain3 → 模板化压缩

| 步骤 | 关键规则 |
| --- | --- |
| 噪声过滤 | 心跳/健康检查/进度条 `\r`/连续同模板折叠(count)；异常行强制保留，**丢失率 0** |
| 打码归一化 | IP/端口/GUID/十六进制/数值/时间戳 → `<*>`；枚举值（运营商）与 AT 指令保留为变量列 |
| Drain3 | `Depth=4`、`sim_threshold=0.4`、`max_children=100`、`max_clusters=1024`、INCREMENTAL、**模板库持久化** |
| 模板化压缩 | logzip 无 pip 包，按「模板分组 + 变量列 + zstd/parquet」等价实现 |

## 4.5 分块与入库

- 粒度 400~800 token，硬上限 1024
- 日期（天/小时桶）为一级分区；服务以 `module_id` 为主键；错误事件锚点 ±20 行/±10s
- **只有异常事件块与模板摘要入 Milvus**（`chunk_type=error/template`），全量日志不入向量库
- 知识问答只查 `chunk_type=section`，强制过滤

---

# 5. P3 检索基础设施与运维

## 5.0 进度

| 项 | 状态 | 落地位置 |
| --- | --- | --- |
| 5.3 观测：流水线/检索/向量快照 | ✅ | `diagnostics/pipeline_metrics.py`、`GET /logs/pipeline/health` |
| 5.4 存储布局与预签名 | ✅ | `LogStorage.save(project_id=)` → `logs/p{pid}/{yyyymmdd}/`、`presigned_get()` TTL 900s |
| 5.1 BM25 外置 | ⏸ 暂缓 | 语料 292 块、recall@5 已 1.000，进程内 BM25 未成为瓶颈；文档上千或并发 20+ 再评估 |
| 5.2 阈值校准 | ✅ | 黄金集 52 条（45 正/7 负）基线：recall@5 1.000 / MRR 0.983（5 条因文档删除标 needs_recheck，详见 §基线说明）；`RRF_WEIGHT_DENSE=1.5`、`merge_tiny=False`、精排实测有害已默认关闭 |
| 5.5 回归 CI push 触发 | ✅（待 runner） | 已加 `push` 触发 + `GOLDEN_RUNNER_READY` 变量闸门；runner 就绪后设变量即生效 |

> 精排（bge-reranker-base）实测：开启后 recall@5 1.000→0.889、MRR 0.849→0.733、耗时 9.5×，
> 已把 `RERANKER_ENABLED` 默认改为 `False`；重开前应先用全文而非 snippet 再测一轮。

> 部署环境需要人工验证的项统一列在 [`Deployment-Verification-Checklist.md`](./Deployment-Verification-Checklist.md)，含命令、期望结果与回填模板。

## 5.1 BM25 外置

当前 BM25 是进程内索引（已按语料签名缓存，避免每请求重建）。进一步：
- 优先 Milvus 2.5 内置 BM25/sparse（同库同过滤）
- 或 SQLite FTS5 / OpenSearch 增量索引
- 验收：并发 20 时检索 P95 不随文档数线性上升

## 5.2 阈值与参数校准

- 用黄金集回归校准：`ef`、`M`、RRF k、rerank 分差阈值、`cosine` 弱相关阈值
- **阈值变更必须单独提交 + 管理员审批**，并记入黄金集版本

### 5.2 校准结果（2026-11，黄金集 21 条正样本）

| 参数 | 取值 | recall@5 | MRR | 结论 |
| --- | --- | --- | --- | --- |
| RRF 等权（原默认） | k=60, sparse=1.0, dense=1.0 | 0.952 | 0.897 | 基线 |
| **向量加权（新默认）** | k=60, sparse=1.0, **dense=1.5** | **0.952** | **0.921** | 采用 |
| BM25 加权 | k=60, sparse=1.5/2.0, dense=1.0 | 0.905 | 0.873 | 更差，不用 |
| k 扫描 | k=20/40/60/80 | 0.952 | 0.921 | k 无显著影响，保持 60 |
| **碎片合并 merge_tiny=ON** | 292→164 块 | 0.905 | 0.786 | **明确更差，保持关闭** |

> 样本量 21 条，MRR 提升（0.897→0.921）相当于一条样本名次前移；
> 方向可信但幅度需在样本扩到 50+ 后复核。调参脚本：`scripts/tune_retrieval.py`。

## 5.3 观测

- 检索各阶段耗时/命中数、pattern 命中分布、零命中率、embedding 服务 QPS 与延迟、任务队列积压
- `/api/v1/knowledge/vector/health` 必须能回答：provider 是否语义、维度、`schema_error`、集合实体数

## 5.4 存储治理

- 对象布局（已实现）：`logs/p{project_id}/{yyyymmdd}/{uuid}_{filename}`；预处理产物仍在 `UPLOAD_DIR/_ingest/{log_id}/`，迁移到对象存储时沿用同一前缀规则
- ILM：raw 30 天、index 90 天、artifacts 长期；`replay_snapshot` 独立桶不随 ILM 清理
- 预签名 TTL 15 分钟（`MINIO_PRESIGN_TTL_SECONDS=900`，`LogStorage.presigned_get()`），桶禁公开

## 5.5 黄金集与回归 CI

### 去重策略（定稿：只做结果层，不删数据）

实测 292 个章节块 → 292 个不同 `content_hash`，**跨文档完全重复 0 组**：
FAQ 与专题文档的重叠是"部分改写"，字节级 hash 根本抓不到。

因此：

- 现有 `content_hash` 去重**只作用于查询结果列表**，不删库、不改文档，命中率实测为 0，等于安全网；
- **不做存储层去重**：同一知识分散在多份文档、作者各写一版时，用算法裁决"哪份对"等于替内容负责人做判断，风险大于收益；
- 若现场反馈"同一问题给两段相似答案"，再做**结果层近似折叠**（只折叠 top-k 内的相似项，保留 alternate 可展开，阈值需用黄金集校准），随时可回退；
- 真要清理数据只允许标 `superseded`，不物理删除。

### 基线（2026-11，52 条样本：45 正 + 7 负，其中 5 正样本待复核）

| 指标 | 数值 | 门槛 |
| --- | --- | --- |
| 章节级 recall@5 | **1.000**（40/40 参与统计的正样本） | 0.85 |
| MRR | **0.983** | 0.70 |
| 负样本 | 7 条（ask_slot 3 / refused 4），不参与检索指标 | — |
| 待复核 | 5 条标 `needs_recheck`（依赖的文档已删除，不参与统计） | — |

> **索引漂移的事故与修复（2026-11-24）**
>
> 现象：一次复测 recall 从 1.000 掉到 0.800，且表现为「某篇大文档霸榜前 5」。
> 根因：内容改过但索引没重建 —— 集合里有 1192 条实体，当前内容只需 174 条。
> dense 检索把 top-k 名额花在**已不存在**的旧块上，映射失败后整段候选被丢弃，
> 且全程没有任何报错。重建集合后 recall 回到 1.000，MRR 从 0.849 升到 0.983
> （旧块此前也在拉低名次）。
>
> 纪律与工具：
> 1. **内容改动后必须回填**（`python -m scripts.reindex_knowledge`），否则检索会静默变差；
> 2. `python -m scripts.check_knowledge_index` 做漂移检查（期望块 hash 集合 vs 集合实际），
>    漂移时退出码 1，适合接进巡检/CI；
> 3. 切分口径只有一个 `VectorService._build_chunks`：占位章节（`（草稿未提供）`）与
>    短于 `MIN_SECTION_CHARS` 的碎片在**索引侧和检索侧一并排除**——索引里若留着
>    检索侧不认的块，同样会占满 top-k 后整段丢弃；
> 4. 目录节点（`doc_type=folder`）不参与回填，`skipped_folders` 单独计数，
>    不再混进 `empty_docs` 掩盖真正为空的坏数据。
>
> 5 条 `needs_recheck` 样本指向已删除的 `doc_id=11`（设备端 FAQ）：设备登录日志、
> ADAS 不报警、大华算法、4G 信号值、拨号网络不通。恢复该文档后复核确认即可回到
> `approved`；在此之前不要在代码里找原因。

样本构成：21 条初版 + 24 条第二批（补 FAQ、苏标、JT1078、GB28787、TMP、设备端等）
+ 7 条负样本；全部管理员提交免审，断言为**主题级**（章节标题含主题词）。

#### 定基线时发现并修掉的两个缺陷

1. **FAQ 文档是 `draft` 状态**：回填进了向量库，但 BM25 语料按 `status=active` 过滤，
   两套语料不一致 → FAQ 的 30 条 dense 命中只映射上 9 条，表现为「FAQ 永远检索不到」。
   产品口径是「知识库没有草稿一说」：数据统一置 active，并让 `run_reindex` 也按 active 过滤，
   回填与检索使用同一可见集合。
2. **BM25 语料与向量索引各写了一套切分**：`content_hash` 对不上，语义那一路形同废弃。
   改为 `build_section_chunks` 复用 `VectorService._build_chunks`，单一实现。

修复后 recall@5 0.889 → **1.000**；MRR 0.874 → 0.849（FAQ 现在能召回，
部分落在靠后名次，属正常权衡）。



- CI 快检（每次提交）：确定性断言（recall@5 ≥0.85、hit@30 ≥0.90、结论类别一致 ≥0.95），不调 LLM
- 夜间全量：LLM 判分抽样 20%
- 门槛：任一项低于门槛或单次下降 >2pp → 阻断；**只允许改代码或标 `superseded`，不允许下调阈值**
- 自托管 runner 就绪后，把仓库变量 `GOLDEN_RUNNER_READY` 设为 `true` 即启用 push 触发（工作流已加 `push`，runner 未就绪时 job 级 `if` 会直接跳过，不会排队等待）

---

# 6. 定稿决策清单（不可随意变更）

| 编号 | 决策 |
| --- | --- |
| D1 | 时区固定北京时间 +08:00，不做 UTC 推断 |
| D2 | 知识库无草稿概念，检索不做状态加权 |
| D3 | 日志只在对话提问时上传，不长期入独立日志库 |
| D4 | 日志检索不做全文件扫描，按时间宽范围定位 |
| D5 | 附日志提问必填五项槽位（城市/设备/现象/时间/附件） |
| D6 | 时间不匹配不猜、不静默返回「未找到」，走候选时段 |
| D7 | 关键字只来自知识库命中章节，不维护独立清单 |
| D8 | 候选时段 3 个 + 「其他」，每项带时段/错误数/模板摘要 |
| D9 | Embedding 私有 BGE（1024 维），collection 可重建 |
| D10 | 日志摘要与知识文档同集合，用 `chunk_type` 强制过滤 |
| D11 | 审核链按提交人角色：管理员直接生效；开发→管理员；测试→开发→管理员；用户→测试→开发→管理员 |
| D12 | 知识条目上线 → 依赖它的 approved 样本标 `needs_recheck`，复核确认后恢复 |
| D13 | 回归 CI 每次提交触发（确定性断言），LLM 判分夜间抽样 |
| D14 | 知识章节与日志证据块同集合，schema v3 增加 `chunk_type/source/ts`；知识检索必须传 `chunk_types=("section",)`，不传即视为缺陷 |
| D15 | 日志块主键取负数（`-(log_id*100000+i)`），与知识文档正数主键天然隔离，删除互不影响 |
| D16 | 日志按「模板 + 1 分钟桶」聚合后入库；报错行必入，正常模板需重复 ≥2 次；单日志上限 2000 块 |
| D17 | 开发阶段数据全部可删：v3 集合直接重建，不并行保留旧集合 |
| D18 | Milvus v2.4.0 支持 `in` 表达式：知识检索固定 `chunk_type in ["section"]`，不做单值降级 |
| D19 | 章节口径：AI 润色 Markdown 按标题切章、超长小节按段落切窗、**过滤目录/前言/修订记录**（`sections.py`） |
| D20 | 验收用例：提问「进出站日志中搜索什么」必须召回《FAQ》第 5 节（旧实现只召回《线路》第 1 节） |

---

# 7. 验收指标总表

| 维度 | 指标 | 目标 |
| --- | --- | --- |
| 向量真实性 | 同义改写 Recall@1（哈希兜底应≈随机） | ≥0.90 |
| 知识检索 | 黄金集 recall@5 / MRR | ≥0.85 / ≥0.70 |
| 精排 | 精排后 Top5 命中率相对召回提升 | +5pp 以上 |
| 时间定位 | 命中块日期正确率 / 跨天串日 | 100% / 0 |
| 日期错配 | 不重叠时正确提示并给出覆盖范围 | ≥95% |
| 日志召回 | 故障点在 Top30 块内 | ≥90% |
| 零命中表述 | 必须给「关键点未命中」而非「未找到」 | 100% |
| 首答延迟 | 100MB 上传完成后首 token P95 | <15s |
| 时间轴扫描 | 100MB P95 | <10s |
| Range GET | 时间窗读取占文件比例 | <20% |
| 异步任务 | 成功率 / 幂等产物 hash 一致 | ≥99% / 100% |
| 预处理 | 异常行丢失率 / 压缩比 | 0 / ≥15× |
| 问答引用 | 引用章节正确率 | ≥85% |

---

# 8. 执行纪律

1. **不静默降级**：embedding/集合/精排不可用时必须显式暴露（health 端点 + 日志），不允许退回哈希或静默跳过关键环节。
2. **不改阈值让 CI 变绿**：先查是检索退化还是样本过期；样本过期标 `superseded`，阈值调整单独提交 + 审批。
3. **章节切分只允许一套口径**：`services/knowledge/sections.py` 是唯一实现，BM25 索引、向量写入、snippet 展示必须共用；目录/前言/修订记录一律不进检索（`drop_navigation=True`）。
4. **检索轨迹必须落库**：任何绕过 `trace_service` 的新链路都会让黄金集无法标注。
5. **日志与知识文档同集合时必须过滤 `chunk_type`**：否则日志摘要会污染知识问答。

---

# 9. 相关文档

| 文档 | 内容 |
| --- | --- |
| [`Deployment-Verification-Checklist.md`](./Deployment-Verification-Checklist.md) | V1~V7：只能在部署环境验证的项（集合回填、过滤语义、100MB 端到端、Drain3 质量、精排 A/B、MinIO、回归 CI） |
| [`Chat-Image-Recognition-Design.md`](./Chat-Image-Recognition-Design.md) | 对话界面截图识别（DeepSeek-only：OCR 主路径 + 视觉兜底、路由规则、成本） |
