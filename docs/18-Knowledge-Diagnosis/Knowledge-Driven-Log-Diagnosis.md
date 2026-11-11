# 知识驱动日志诊断设计（文本 + 附件）

> 归属：AI Diagnostic Platform · 诊断增强
> 目标：文本 + 附件提问时，一切结论必须由「知识库条目 + 日志证据」支撑；无知识库支撑不出结论；知识库从自由文本升级为可执行「诊断剧本」；后期自进化候选 + 人工审核。

---

## 1. 背景与现状

### 1.1 当前两条链路

| 场景 | 前端入口 | 后端 | 特点 |
| --- | --- | --- | --- |
| 纯文本 | `ChatLayout.sendMessage()` → `streamChat()` | `POST /chat-sessions/{id}/stream` → `DiagnosticChatAgent` | 严格 RAG，无命中强制返回「知识库中暂无」 |
| 文本 + 附件 | `sendMessage()` → `processFiles()` | `POST /analyses/run` → `DiagnosisPipeline` | 解析 → 裁剪 → 规则 → RAG → LLM，LLM 可基于日志自由推理 |

### 1.2 关键差距

1. **附件路径不是强约束**：`DiagnosisPipeline.DIAGNOSIS_PROMPT` 允许「基于日志本地分析自由推理」，知识库仅作参考，存在胡编风险。
2. **「知识库 → 日志检索」是隐式的**：Stage 4 是「日志（规则名/错误分类）→ 知识库」单向；Stage 2 的日志 grep 只由 `user_query` 关键词驱动。缺少「知识条目内容 → 反哺日志关键词/正则」的显式闭环。
3. **知识条目没有结构化能力**：`KnowledgeDocument` 只有自由文本，无法携带「要搜什么关键字、用什么正则、命中后怎么判定」。
4. **自进化缺失**：没有把「成功解决」的经验沉淀回知识库的机制。

---

## 2. 设计原则（已确认）

1. **强约束**：每个结论必须同时挂到「某条知识库条目」+「日志命中行（带行号）」；缺任一 → 不输出结论，走固定「知识库中暂无支撑」话术。
2. **自进化**：AI 只产出**候选草稿**，人工审核通过才入库。
3. **确定性优先**：字段/关键字判定走「知识库结构化关键词 + 正则」，LLM 仅做组织表达与兜底。
4. **一切总结基于知识库**。

---

## 3. 数据模型

### 3.1 新增 `KnowledgeDiagnosisProfile`（与 `KnowledgeDocument` 1:1）

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `id` | int PK | |
| `doc_id` | int FK unique | 关联知识条目 |
| `symptom` | Text | 现象/问题描述 |
| `environment` | String(300) | 设备/芯片/固件版本 |
| `log_keywords` | JSON `list[str]` | 要搜的日志关键词 |
| `log_patterns` | JSON `list[str]` | 要匹配的正则 |
| `negative_patterns` | JSON `list[str]` | 排除用负正则 |
| `expected` | Text | 命中后如何判定（如版本号格式） |
| `root_cause` | Text | 根因 |
| `solution` | Text | 解决方案 |
| `confidence` | Float | 可信度（自进化权重） |
| `status` | String(20) | `draft` / `active` / `archived` |
| `source` | String(20) | `manual` / `ai_candidate` |
| `created_at/updated_at` | DateTime | |

> 选择「新表」而非给 `knowledge_documents` 加列：运行时用 `create_all()` 不会 ALTER 既有表；新表可同时兼容 `create_all` 与 alembic（与 `KnowledgeImage` 的做法一致）。自进化候选复用同表（`status=draft`, `source=ai_candidate`），无需再建表。

---

## 4. 流水线改造

### 4.1 新增 Stage 4.5：知识驱动日志定位

在 `DiagnosisPipeline` 的 Stage 4（RAG 检索）之后、Stage 5（组 Prompt）之前：

```
KB 命中条目 → 取该条目的 KnowledgeDiagnosisProfile
        → 编译 log_patterns（正则）逐行匹配
        → log_keywords 做窗口 grep
        → negative_patterns 排除
        → 产出 verdict = hit / miss / partial + matched_lines[{line_no, text, via}]
```

- 有 profile → 执行定位，得到 `detections`
- 无 profile → 标记 `supported=False`（该条目没有结构化剧本，无法驱动日志检索）

### 4.2 强约束分支

`detections` 全 miss 或全部无 profile 支撑 → 直接返回固定「知识库中暂无可验证的支撑，无法给出诊断结论；以下仅列出日志事实…」，**不调 LLM 自由发挥**。

### 4.3 Prompt 版本化

把 `DiagnosisPipeline.DIAGNOSIS_PROMPT` 迁移到 `services/prompts/`（Prompt v2），核心约束：

- 结论必须引用「KB 条目 id/标题」+「日志行号」
- 无 KB 支撑的结论一律不输出
- 日志与 KB 冲突以日志为准并标注
- 证据不足输出「证据不足，无法确认」

输出 JSON 扩展：`summary, root_cause, confidence, next_steps, matched(bool), evidence: [{kb_id, title, log_lines[]}]`。

---

## 5. API 与 Schema

| 改动 | 位置 |
| --- | --- |
| 新增 `KnowledgeProfileCreate/Update/Response`，`KnowledgeCreate/Update` 加可选 `profile` | `schemas/knowledge/knowledge.py` |
| create/update 时同步 upsert profile；新增 `GET/PUT /knowledge/{doc_id}/profile` | `api/knowledge/__init__.py` |
| 审核队列：`GET /knowledge/profiles/drafts`、`POST /knowledge/profiles/{id}/approve`、`POST .../reject` | `api/knowledge/`（阶段 C） |
| 结果返回增加 `detections` 与 `evidence` | `analysis_task_service.py`（阶段 B） |

---

## 6. 自进化闭环（候选 + 人工审核）

```
问题 + 日志 + AI 回答 → 用户确认「已解决/未解决」或点赞/点踩
        → LLM 蒸馏候选 profile（status=draft, source=ai_candidate, confidence=0.3）
        → 去重（与现有 profile 相似度）
        → 权重累加：confidence ≈ 解决成功次数 / 出现次数 + 人工审核加成
        → 人工审核通过 → status=active → 进入检索
```

- 低置信度条目：可进参考，但不参与「强结论」。
- 必须加审核闸，避免错误答案污染知识库。

---

## 7. 示例：版本号查询

知识条目配置 profile：

```json
{
  "symptom": "设备程序版本号查询",
  "log_keywords": ["version", "版本号", "firmware", "build"],
  "log_patterns": ["(?i)(version|版本号|firmware)\\s*[:=]\\s*[\\w.\\-]+"],
  "expected": "从命中行提取 x.y.z 形式版本号"
}
```

用户问「这个日志程序版本号多少」+ 上传日志：
1. Stage 4 命中该 KB 条目；
2. Stage 4.5 用其 `log_patterns` 在日志中定位到 `version: 1.2.3`（第 N 行）；
3. Prompt 带「KB 标题 + 该行」；
4. 回答输出「程序版本号为 1.2.3（依据《XX手册》+ 日志第 N 行）」。
5. 若无对应 KB 条目 → 直接回「知识库中暂无支撑」。

---

## 8. 分阶段实施

| 阶段 | 内容 |
| --- | --- |
| **A 地基** | profile 表 + 服务 + schema + 知识库编辑表单（让 KB 能存结构化剧本） |
| **B 核心** | `KnowledgeLogLocator` + Pipeline Stage 4.5 + 强约束 Prompt + 结果带证据 |
| **C 自进化** | 蒸馏服务 + 反馈触发 + 审核队列 + 前端审核页 |
| **D 可选** | 存量 KB 批量回填（`extract_from_document`） |

---

## 9. 验收标准

1. 有对应 profile 的 KB + 日志 → 回答必带「KB 条目 + 日志行号」证据。
2. KB 无支持 → 不产出结论，返回固定「知识库中暂无支撑」话术。
3. 自进化：点「已解决」→ 生成 draft；未经审核不入库；审核通过后可被检索命中。
4. 确定性：同一问题 + 同一日志多次分析，命中的 KB / 日志行一致（可复现）。

---

## 10. 风险与对策

- 结构化字段冷启动成本 → LLM 辅助提取 + 模板 + 存量批量回填。
- 正则误命中 → 负模式 + 窗口 + 人工审核。
- LLM 幻觉 → 输出后校验：`evidence` 非空且行号真实存在，否则降级为无结论。
- `create_all` 不 ALTER 旧表 → 全部用新表承载（profile / 候选）。

---

## 11. 实施进度

- [x] **阶段 A**：profile 表 / 服务 / Schema / API / 前端「诊断配置」表单
- [x] **阶段 B**：`KnowledgeLogLocator` + `DiagnosisPipeline` Stage 4.5 + 强约束 Prompt（v3.0）+ 结果带证据
- [ ] **阶段 C**：自进化（蒸馏 + 反馈触发 + 审核队列）
- [ ] **阶段 D**：存量 KB 批量回填
