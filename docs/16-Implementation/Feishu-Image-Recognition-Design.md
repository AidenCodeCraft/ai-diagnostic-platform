# 飞书图片识别方案（DeepSeek-only，v2）

> 本文替换此前"M2 视觉模型 + 自建推理"方案。结论：**不引入第三方模型**，
> 图片识别全部通过 DeepSeek 官方能力完成（视觉理解 + OCR API），
> 飞书侧只负责"把图拿到手"。

- 状态：方案定稿；**S1 已实现**（回调骨架、验签/解密、事件幂等、图片记录落库）；S2~S5 未开始
- 最后核对的官方文档：2026-11（DeepSeek 图像理解 / OCR、飞书获取消息资源文件）
- 相关代码位置：`backend/app/api/integrations/`、`backend/app/services/integrations/feishu/`、
  `backend/app/services/providers/`、`backend/app/worker/tasks.py`

---

## 1. 为什么是 DeepSeek-only

| 维度 | 自建 M2 视觉模型 | DeepSeek 视觉 / OCR |
| --- | --- | --- |
| 依赖 | GPU 或大内存 CPU 推理服务、模型分发、权重升级 | 已有 API key，零新增基础设施 |
| 与现有链路 | 新增一套 Provider、并发与限流要自己设计 | 复用 `services/providers/` 抽象层 |
| 日志截图保真 | 视觉模型输出的仍是"模型改写后的文本" | OCR 返回**原样文本 + 坐标**，可直接喂模板提取 |
| 成本 | 固定投入（机器/显存）与利用率强相关 | 按量付费，见 §7 |
| 运维 | 需要监控显存、模型版本、队列积压 | 只需监控 API 错误率与限流 |

**关键结论**：设备日志截图要的是"一字不差的原文"，视觉模型的"理解"反而是损失。
因此主路径是 **OCR API**，视觉理解只做兜底。

---

## 2. DeepSeek 两条能力的差异（选型依据）

| | 视觉理解 | OCR API |
| --- | --- | --- |
| 端点 | `POST /chat/completions`（`deepseek-flash`） | `POST /v1/tools/ocr` |
| 入参 | 图片 + 自然语言指令（`image_url` / `file` 块） | 单个文件 + `purpose` |
| 出参 | 模型生成的自然语言 | 按页返回 `pages[].text`（原样，含 `<｜box｜>` 坐标标记） |
| 格式 | JPEG / PNG / GIF / WebP | PNG / JPEG / WebP / GIF / BMP / TIFF + PDF/DOC/DOCX/PPT/PPTX |
| 单图大小 | base64/URL ≤32 MiB；Files API `file_id` ≤64 MiB | 文件 ≤100 MiB |
| 单请求图片数 | ≤600 张 | — |
| 页数/文档 | — | ≤1000 页 |
| 超时 | 常规请求超时 | 上传 120s 内完成、总时长 180s（含上传） |
| 计费 | 图片折算 token（**每张 ≤1024 tokens**），与文本同价 | **1.5 元 / 1000 页** |
| 适用 | 弹窗、UI 状态、接线图、波形、图表 | 等宽日志截图、报错堆栈、表格 |

不支持视觉的模型：`deepseek-v4-pro`（仅 `deepseek-flash` 支持图像理解）。

---

## 3. 权限清单（飞书开放平台）

### 3.1 应用能力

- 开启**机器人能力**（bot）；资源下载要求"机器人与消息在同一会话内"
- 事件订阅方式：长连接（推荐，内网无需公网回调）或 HTTP 回调
- 若用 HTTP 回调：配置 `Verification Token` + `Encrypt Key`，实现 `url_verification` 握手与签名校验

### 3.2 权限 scope

| 用途 | 权限 |
| --- | --- |
| 接收单聊消息事件 | `im:message.p2p_msg:readonly` |
| 接收群内 @ 机器人消息事件 | `im:message.group_at_msg:readonly` |
| 下载消息中的图片资源 | `im:resource`（文档口径："获取与发送单聊、群组消息" / "获取单聊、群组消息"任一） |
| 回复消息 | `im:message:send_as_bot` |

> 应用必须被拉进目标群，否则下载返回 `234004 App not in chat`。

### 3.3 事件

- `im.message.receive_v1`：消息接收事件，取 `message_id`、`message_type=image`、
  `content` 中的 `image_key`
- 图片消息的 `content` 形如 `{"image_key": "img_v3_xxx"}`

---

## 4. 事件流

```
用户（飞书）        backend                      Redis/Celery           DeepSeek
   │  发图片消息        │                              │                    │
   ├──────────────────>│ 1. 验签/解密                  │                    │
   │                   │ 2. 事件去重(event_id)         │                    │
   │                   │ 3. 立即下载图片               │                    │
   │                   │    GET /im/v1/messages/{mid}  │                    │
   │                   │        /resources/{img_key}   │                    │
   │                   │ 4. 落 MinIO(私有桶)           │                    │
   │                   │ 5. 建 attachment 记录         │                    │
   │                   │ 6. 投递 vision.recognize ────>│                    │
   │<─ "已收到，处理中" ─┤                              │ 7. OCR ───────────>│
   │                   │                              │ 8. 路由判定        │
   │                   │                              │ 9. 视觉兜底 ──────>│
   │<─ 识别结果/追问 ───┴──────────────────────────────┤ 10. 回写文本+状态  │
```

### 4.1 各步骤要点

| 步骤 | 关键设计 | 失败处理 |
| --- | --- | --- |
| 1 验签/解密 | `X-Lark-Signature` 校验；开启加密时 AES 解密；`url_verification` 直接回 `challenge` | 校验失败返回 403，不落库 |
| 2 去重 | 以飞书 `event_id` 为幂等键（表 `feishu_events` 或 Redis `SETNX`，TTL 24h） | 重复事件直接 200，不重复下载 |
| 3 立即下载 | **资源 key 会过期，不能等展示时再下载**；`type=image` 不支持 Range，整文件下载 | 见 4.2 重试策略 |
| 4 存储 | 复用 `LogStorage`：`attachments/p{project_id}/{yyyymmdd}/{uuid}.{ext}`，桶私有 | 上传失败保留本地并告警 |
| 5 建记录 | `attachments(id, message_id, image_key, storage_ref, mime, size, sha256, status)` | `message_id+image_key` 唯一索引防重 |
| 6 投递任务 | 新队列 `vision`，`task_id = {attachment_id}:recognize:0`，复用 `agent_tasks` 状态机 | broker 不可用时仅落库并置 `pending`，由补偿任务扫描 |
| 7 OCR | `POST /v1/tools/ocr`，`purpose=text_recognition` | 失败按 4.2 重试，最终 `failed` 并告知用户 |
| 8 路由 | 见 §5 判定函数 | 判定为"信息不足"时进入视觉兜底 |
| 9 视觉 | `deepseek-flash` + `image_url`（MinIO 预签名 15 分钟） | 失败则返回 OCR 文本并标注"可能有遗漏" |
| 10 回写 | 写 `attachments.extracted_text`、`recognition_path`（ocr/vision/ocr+vision）、`usage` | 用户可见进度复用 `ingest-status` 模式 |

### 4.2 重试与幂等

- 下载：网络/5xx/`234019` → 指数退避重试 3 次（5s/25s/125s）；`234037`（>100MB）、
  `234038`（保密消息）、`234043`（不支持的消息类型）→ **不重试**，直接告知用户原因
- OCR/视觉：`429`/`5xx` → 退避重试最多 3 次；`400`（格式不支持/无法解码）不重试
- 全链路幂等键：`event_id`（防重投）、`attachment_id`（防重复识别）
- 同一 `message_id` 的多张图：每张独立记录与任务，任一失败不影响其他

---

## 5. OCR / 视觉路由规则

### 5.1 判定逻辑（确定性，不用模型判断）

```
text = ocr(image)                         # 主路径
stats = analyze(text)                     # 见下表
if ocr_failed or stats.is_log_screenshot:
    path = "ocr"
elif stats.text_chars < 200 or stats.line_with_ts == 0 and stats.kb_keyword_hits < 2:
    path = "vision"                       # OCR 拿到的信息不足以诊断 → 让模型看图
else:
    path = "ocr"
```

| 指标 | 定义 | 日志截图的期望 |
| --- | --- | --- |
| `line_with_ts` | 匹配 `\[\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\]` 的行数 | ≥3 |
| `module_id_hits` | 匹配 `[A-Za-z][A-Za-z0-9_.]{2,}\.\.[ ]?\d{4}`（如 `NL668_4G_GetRegSta.. 0719`） | ≥1 |
| `kb_keyword_hits` | 命中知识库章节关键字的数量（复用 `chat/log_patterns.py` 的关键字抽取） | ≥2 |
| `text_chars` | OCR 文本总字符数 | >500（一屏日志通常上千） |
| `non_text_ratio` | 无 OCR 文本区域的占比（用 `<｜box｜>` 覆盖面积估算） | <0.3 |

**判定顺序**（避免过度调用视觉）：

1. OCR 失败 → 视觉
2. `line_with_ts ≥ 3` 或 `module_id_hits ≥ 1` → **日志截图 → 只用 OCR**
3. `kb_keyword_hits ≥ 2` 且 `text_chars ≥ 500` → 只用 OCR
4. 其余（UI 弹窗、接线图、波形）→ 视觉

### 5.2 视觉提示词约束

- 提示词放 `services/prompts/vision_image_understanding_v1.txt`（AGENTS.md：禁止硬编码）
- 输出契约：JSON `{scene: dialog|ui|chart|wiring|other, texts: [...], summary: "...", uncertainty: [...]}`
- **不允许模型"补全"看不见的内容**：提示词明确要求"只描述可见文字与结构；不确定的写进 uncertainty"
- `detail=low`（512×512）用于快速分类，`original` 用于读小字；默认 `original`

### 5.3 识别结果如何进入现有链路

- 文本写入 `attachments.extracted_text`，随该会话的提问作为"日志证据"注入
  `chat/log_context.py` 的证据块（**不单独写入 Milvus**）
- 理由：图片文本是"一次性的现场证据"，不是知识；入向量库会污染知识召回
  （与 D14 的 `chunk_type` 强制过滤互为补充）
- 若用户后续追问，同一 `attachment_id` 的文本可重复使用，无需再次调用 DeepSeek

---

## 6. 数据结构

```sql
-- 新增表：feishu_attachments
id            BIGSERIAL PRIMARY KEY
tenant_key    VARCHAR(64)          -- 多租户隔离
message_id    VARCHAR(64) NOT NULL -- 飞书消息 id
image_key     VARCHAR(128) NOT NULL
chat_id       VARCHAR(64)          -- 群/单聊 id
sender_id     VARCHAR(64)          -- 飞书 open_id
storage_ref   VARCHAR(512)         -- minio://bucket/key
mime          VARCHAR(64)
size_bytes    BIGINT
sha256        VARCHAR(64)          -- 同一图片重复发送可去重
status        VARCHAR(16)          -- pending|downloading|recognizing|succeeded|failed
recognize_path VARCHAR(16)         -- ocr|vision|ocr+vision
extracted_text TEXT
usage         JSONB                -- {ocr_tokens, vision_in, vision_out, cost_yuan}
error_message VARCHAR(500)
created_at / updated_at
UNIQUE (message_id, image_key)
```

任务状态复用现有 `agent_tasks`（`task_id = {attachment_id}:recognize:0`），
不新建队列表；进度查询沿用 `GET /api/v1/logs/{id}/ingest-status` 的模式，
新增 `GET /api/v1/integrations/feishu/attachments/{id}`。

---

## 7. 成本估算

### 7.1 单价（DeepSeek 官方价，元）

| 项目 | 单价 |
| --- | --- |
| OCR / 文件解析 | 1.5 元 / 1000 页 |
| `deepseek-flash` 输入（缓存未命中） | 2 元 / 百万 tokens（高峰）· 1 元（空闲） |
| `deepseek-flash` 输出 | 8 元 / 百万 tokens（高峰）· 4 元（空闲） |

高峰 = 北京时间工作日 9:00–12:00、14:00–18:00；其余（含周末/节假日）为空闲，价格为一半。

### 7.2 单张图片成本

单张视觉请求按"图 ≤1024 tokens + 指令约 300 tokens + 输出约 300 tokens"估算：

| 路径 | 计算 | 高峰 | 空闲 |
| --- | --- | --- | --- |
| OCR | 1 页 × 1.5/1000 | 0.00150 元 | 0.00150 元 |
| 视觉 | (1024+300) tok 输入 + 300 tok 输出 | 1324×2/1e6 + 300×8/1e6 = **0.00505 元** | **0.00252 元** |

> 注意：输出 token 单价是输入的 4 倍，只按输入价算会把视觉成本低估约 1.6 倍。

### 7.3 按业务量估算

假设 **80% 日志截图走 OCR、20% 走视觉**（典型现场比例）：

| 规模 | OCR | 视觉（高峰） | 合计（高峰） | 合计（空闲） |
| --- | --- | --- | --- | --- |
| 1,000 张 | 0.8k 页 → 1.20 元 | 200 张 → 1.01 元 | **2.21 元** | **1.70 元** |
| 10,000 张 | 12.00 元 | 10.10 元 | **22.10 元** | **17.05 元** |
| 100,000 张 | 120.00 元 | 100.96 元 | **220.96 元** | **170.48 元** |

**原授权预算 10,000 元 ≈ 452 万张混合图片**（高峰价计算）。结论：**成本不是约束**，
真正的约束是并发（`deepseek-flash` 并发上限 2500）与用户等待时间（OCR 单张通常 2–5 秒）。

### 7.4 可控项

- OCR 命中率高时几乎不产生视觉调用；视觉只在"OCR 信息不足"时触发
- 同一 `sha256` 图片重复发送直接复用文本（0 成本）
- 视觉默认 `detail=original`，读小字失败再降级为分块裁切重试（每块单独计费，需限次数）

---

## 8. 安全与合规

- 图片与提取文本都存**私有桶**，对外只发 15 分钟预签名链接（`MINIO_PRESIGN_TTL_SECONDS=900`）
- **保密消息不可下载**（`234038`）——这是飞书的合规边界，不要尝试绕过
- 提交 DeepSeek 前：`model content safety` 开启后图片会过审；未通过的响应会拒答，需在 UI 明示"图片未通过内容审核"
- 提取文本里可能含设备序列号、SIM 号、IP：写库前按现有规则脱敏（IP/HEX/GUID/长数字），
  这些属于证据原文，尽量**保留在证据块中**，但不得写进知识库或黄金集
- 多租户：所有查询必须带 `tenant_key`；`attachment` 只允许其所属会话读取

---

## 9. 验收指标

| 指标 | 门槛 | 测法 |
| --- | --- | --- |
| 下载成功率 | ≥99%（排除保密消息/超大文件/已删除） | 埋点按错误码分组 |
| OCR 字符准确率 | ≥98% | 抽 100 张真实截图，人工比对（字符级编辑距离） |
| 路由正确率 | ≥95% | 人工标注 100 张"应走 OCR / 应走视觉"，比对判定 |
| 首次回复延迟 | P95 ≤5s（"已收到"即时回，结果异步） | 埋点 |
| 识别结果可用率 | 识别文本能进入日志定位的比例 ≥90% | 抽样看是否命中关键字/时间轴 |
| 单张平均成本 | ≤0.004 元 | `usage` 汇总 |

---

## 10. 分阶段实施

| 阶段 | 内容 | 验收 |
| --- | --- | --- |
| S1 | 飞书应用配置（权限/事件/加密）、回调或长连接骨架、`url_verification`、事件去重 | 发消息能把 `event_id`、`message_id`、`image_key` 落库 |
| S2 | 图片下载 + MinIO 落盘 + `feishu_attachments` 表与迁移 | 真实截图能下载、能预签名访问、重复发送不重复存 |
| S3 | OCR 任务（`vision` 队列）→ 文本落库 → 随提问注入证据块 | 日志截图识别后能直接定位到时间窗 |
| S4 | 路由判定 + 视觉兜底（Provider 抽象层 + 版本化提示词） | 弹窗/波形图走视觉，日志截图不误走视觉 |
| S5 | 飞书侧回复（处理中 → 结果/追问）、失败原因回传 | 用户全程知道状态，失败有明确原因 |

依赖：S3/S4 依赖 `services/providers/` 增加 vision 能力，**不得直连 SDK**（AGENTS.md）。

---

## 11. 已定稿决策（2026-11，按建议默认通过）

| 编号 | 决策 |
| --- | --- |
| F1 | **多图消息**：全部识别，合并成一个证据包，按图片在消息中的出现顺序排列 |
| F2 | **图片 + 文字混合**：拼成一次提问，图片识别文本作为附件证据 |
| F3 | **机器人回复**：只回"已识别 + 关键行摘要"；诊断结论仍由主对话流程生成，避免两条链路口径不一致 |
| F4 | **迟到事件**（`image_key` 已过期）：明确回复"资源已过期，请重新发送"，不做静默失败 |

## 12. S1 实现说明（已完成）

| 能力 | 位置 |
| --- | --- |
| 回调入口 + 握手 | `app/api/integrations/feishu.py`（`POST /api/v1/integrations/feishu/events`） |
| 验签 + AES-256-CBC 解密 | `services/integrations/feishu/security.py` |
| 事件解析（image / post 抽 image_key） | `services/integrations/feishu/events.py` |
| 事件幂等 + 图片记录落库 | `services/integrations/feishu/event_service.py` |
| 表结构 | `feishu_events`、`feishu_attachments`（迁移 `a1b2c3d4e5f7`） |
| 状态查询 | `GET /api/v1/integrations/feishu/attachments/{id}`（需登录） |

安全红线（实现时已固化）：

- 未配置 `FEISHU_ENCRYPT_KEY` 或 `FEISHU_VERIFICATION_TOKEN` 时，回调返回 **503**，
  绝不开放无校验的入口；
- 配置了 Encrypt Key 时必须验签 + 解密，签名不符返回 403，不落库；
- 事件幂等靠 `event_id` 唯一索引，并发重投按 duplicate 处理而不是 500。

字段级差异说明：`feishu_attachments.status` 默认 `pending`，S2 下载时才流转到
`downloading → recognizing → succeeded/failed`；`recognize_path` 由 S4 的路由判定写入。
