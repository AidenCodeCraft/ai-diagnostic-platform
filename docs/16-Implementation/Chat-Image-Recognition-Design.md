# 对话界面截图识别方案（DeepSeek-only）

> 用户在 Web 对话界面直接粘贴/上传截图（日志截图、报错弹窗、接线图），
> 识别为文本后作为"现场证据"参与诊断。**不涉及任何即时通讯平台集成。**

- 状态：**I1~I4 已实现**（上传、OCR+路由+视觉兜底、证据块注入、前端粘贴/选择截图）；I5 成本埋点待补
- 官方文档核对：2026-11（DeepSeek 图像理解 / OCR）
- 相关代码：`backend/app/services/vision/`、`backend/app/api/chat/images.py`、
  `backend/app/services/chat/log_context.py`

---

## 1. 为什么 OCR 是主路径、视觉是兜底

| | 视觉理解（`deepseek-flash`） | OCR API（`/v1/tools/ocr`） |
| --- | --- | --- |
| 输出 | 模型生成的自然语言（会改写） | 原样文本 + `<｜box｜>` 坐标 |
| 适合 | 弹窗、UI 状态、接线图、波形 | 等宽日志、报错堆栈、表格 |
| 单文件 | ≤32 MiB（base64/URL）/ ≤64 MiB（file_id） | ≤100 MiB |
| 计费 | 每图 ≤1024 tokens | 1.5 元 / 1000 页 |

设备日志截图要求**一字不差**（`ret=-1`、`0719` 模块号、时间戳），
视觉模型"理解"之后这些细节会丢。所以：**日志截图只走 OCR**，
OCR 信息不足（UI 截图、图表）才升级到视觉。

---

## 2. 用户流程

```
Web 对话界面
   │ 1. 粘贴/选择截图（png/jpg/webp，单张 ≤20MB）
   ▼
POST /api/v1/chat/images   （multipart: file, session_id）
   │ 2. 落私有桶（LogStorage） + 记录 chat_images
   │ 3. OCR → 路由判定 →（必要时）视觉
   ▼
返回 { id, status, recognize_path, text_preview }
   │ 4. 用户继续输入问题并发送（前端带上 image_ids）
   ▼
对话回答：截图文本作为「现场证据」块注入诊断上下文
```

同步识别（2~5 秒）：单次对话通常 1~3 张图，同步返回可以让用户
在发送提问前就看到"识别到了什么"，避免基于错误识别结果提问。
量级上来后再改成队列（复用 P2 的 Celery 骨架）。

---

## 3. 路由规则（确定性，不调模型判断）

```
text, stats = ocr(image)
if ocr_failed:                                    path = "vision"
elif stats.line_with_ts >= 3 or stats.module_id_hits >= 1:   path = "ocr"
elif stats.kb_keyword_hits >= 2 and stats.text_chars >= 500: path = "ocr"
else:                                             path = "vision"
```

| 指标 | 定义 | 日志截图期望 |
| --- | --- | --- |
| `line_with_ts` | 匹配 `[YYYY-MM-DD HH:MM:SS]` 的行数 | ≥3 |
| `module_id_hits` | `[A-Za-z][A-Za-z0-9_.]{2,}\.\.[ ]?\d{4}`（如 `NL668_4G_GetRegSta.. 0719`） | ≥1 |
| `kb_keyword_hits` | 命中知识库章节关键字数（复用 `chat/log_patterns.py`） | ≥2 |
| `text_chars` | OCR 文本总字符数 | >500 |

判定为视觉时，提示词要求输出 JSON：`{scene, texts[], summary, uncertainty[]}`，
并明确"只描述可见内容，不确定的写进 uncertainty"，禁止补全看不见的日志。

---

## 4. 数据模型

```sql
-- chat_images
id            BIGSERIAL PRIMARY KEY
session_id    INT REFERENCES chat_sessions(id)   -- 归属会话（可为空，上传时未绑定）
user_id       INT
filename      VARCHAR(255)
storage_ref   VARCHAR(512)        -- minio://bucket/key 或本地路径
mime          VARCHAR(64)
size_bytes    BIGINT
sha256        VARCHAR(64)         -- 同一张图重复上传复用文本
status        VARCHAR(16)         -- pending|recognizing|succeeded|failed
recognize_path VARCHAR(16)        -- ocr|vision|ocr+vision
extracted_text TEXT
usage         JSONB               -- {ocr_pages, vision_in, vision_out, cost_yuan}
error_message VARCHAR(500)
created_at / updated_at
```

`sha256` 去重：同一张截图重复发送直接复用 `extracted_text`，不重复计费。

---

## 5. 与诊断链路的关系

- 截图文本写 `chat_images.extracted_text`，由 `chat/log_context.py` 装配成
  **现场证据块**（与日志窗口证据并列），参与回答
- **不写入 Milvus**：截图是一次性现场证据，入向量库会污染知识召回
  （与 D14 的 `chunk_type` 强制过滤互为补充）
- 证据块外显：回答里引用截图文本时标注"来自用户截图"，与知识库引用区分

---

## 6. 成本

| 路径 | 高峰 | 空闲 |
| --- | --- | --- |
| OCR（1 页） | 0.00150 元 | 0.00150 元 |
| 视觉（1324 输入 + 300 输出 tokens） | 0.00505 元 | 0.00252 元 |

按 80% OCR / 20% 视觉：1,000 张 ≈ **2.21 元**（高峰）/ 1.70 元（空闲）；
10,000 张 ≈ 22.10 元 / 17.05 元。成本不是约束，瓶颈是单张 2~5 秒的等待。

---

## 7. 安全

- 截图存**私有桶**，前端只通过 15 分钟预签名 URL 查看
- 识别文本可能含设备序列号/SIM/IP：写库前按现有规则脱敏，但**证据块保留原文**
  （诊断需要原文），且不得写入知识库或黄金集
- 图片内容审核开启后，未通过的图片会拒答；UI 明确提示"图片未通过内容审核"

---

## 8. 验收指标

| 指标 | 门槛 |
| --- | --- |
| OCR 字符准确率 | ≥98%（抽 100 张真实截图人工比对） |
| 路由正确率 | ≥95%（人工标注"应走 OCR / 应走视觉"） |
| 上传→识别完成 | P95 ≤5s（单张、≤5MB） |
| 识别文本可进入日志定位的比例 | ≥90% |
| 单张平均成本 | ≤0.004 元 |

---

## 9. 实施阶段

| 阶段 | 内容 |
| --- | --- |
| I1 ✅ | `POST /chat/images` 上传 + 落私有桶 + `chat_images` 表（迁移 `c1d2e3f4a5b6`） |
| I2 ✅ | OCR + 路由判定 + 视觉兜底 + `extracted_text` 落库（`services/vision/`） |
| I3 ✅ | 证据块注入对话上下文（`log_context.image_evidence` → 回答上下文） |
| I4 ✅ | 前端：图片按钮 + 粘贴截图、缩略图与识别状态、识别中禁止发送、移除重试 |
| I5 ⏳ | 成本埋点与黄金集抽样（按 `usage` 汇总） |

待拍板（按默认执行）：

| 编号 | 默认 |
| --- | --- |
| W1 | 单次最多 5 张图，单张 ≤20MB，格式 png/jpg/webp（前端已按 5 张限制） |
| W2 | 识别同步完成后再允许发送（用户能看到识别结果） |
| W3 | 识别失败不阻断提问，证据块标注"截图识别失败" |
| W4 | 同一 `sha256` 复用文本，不重复扣费 |

---

## 附：与官方文档的核对结果（2026-11-20）

对照 `guides/vision` 与 `guides/ocr` 两篇，把实现对齐到文档口径，核到的差异与处理：

| 文档要求 | 原实现 | 处理 |
| --- | --- | --- |
| OCR 地址为 `/v1/tools/ocr` | 只从含 `/chat/completions` 的 base_url 截根，配置只写域名时会打到 `/tools/ocr` | `api_root` 归一补齐 `/v1` |
| OCR 识别开始后失败仍是 **HTTP 200**，响应体是 `error` 对象 | 直接读 `pages` → 得到空文本，失败被伪装成“识别成功但没文字” | 检测 `body.error` 并抛 `VisionProviderError` |
| `pages[].finish_reason == length` 表示该页文本不完整 | 忽略 | 返回 `truncated_pages`，落库 `usage.ocr_truncated_pages` 并打 warning |
| OCR 计费按 `page_count`（1.5 元/1000 页），`usage` 的 token 仅供参照 | 用 `len(pages)` 当页数 | 改用 `page_count` |
| OCR 上传错误码 400/402/408/413/429/500/503/504 各有含义 | 统一报状态码 | 增加中文提示（余额不足/上传过慢/文件过大/并发超限等） |
| 图片格式 JPEG/PNG/GIF/WebP（BMP/TIFF 仅 OCR 支持），**按内容判断** | 只认 PNG/JPEG/WebP，且 `RIFF` 前缀会把 WAV 误判成图片 | 补 GIF/BMP/TIFF；WebP 校验 `RIFF…WEBP` 双前缀 |
| base64/URL 单图上限 32MiB，请求体 48MiB，单请求 ≤600 图 | 上限 20MiB | 提到 32MiB（与文档一致） |
| `purpose` 必填（`text_recognition` / `rich_layout_recognition`），多传字段返回 400 | 固定 `text_recognition`，只传两个字段 | 保持不变（截图走 text_recognition 已够） |

新增 5 条回归测试覆盖：`/v1` 归一、200+error 抛错、截断页标记、413 等错误码提示、GIF/BMP/TIFF/WAV 判定。
