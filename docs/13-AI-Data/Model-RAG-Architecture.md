# AI Model & RAG Architecture Specification

AI Diagnostic Platform

Version: 1.0

---

# 1. AI 体系设计目标

目标：让 AI 具备读懂日志、找异常、定位根因、查询历史案例、给出修复方案、持续学习。

---

# 2. 总体 AI 架构

```
                    User
                     |
               Task Question
                     |
               Agent Layer
                     |
        ---------------------------
        Planner  Memory  Tool  Reasoning
        ---------------------------
                     |
              AI Gateway
                     |
 ----------------------------------------
 |                 |                    |
LLM             RAG                 Rule
Model           System              Engine
 |                 |                    |
DeepSeek       Vector DB           Rules
Qwen           Knowledge            YAML
 ----------------------------------------
                     |
              Data Feedback
```

---

# 3. AI 系统分层设计

采用：AI Stack

```
Application
  Agent
  Knowledge
  Model
Infrastructure
```

---

# 4. Model 层设计

## 4.1 模型职责

基础模型负责：理解语言、推理、总结、生成

不负责：保存企业经验、记忆所有 Bug

---

# 5. 模型选择策略

不要单模型，采用 Model Router。

```
                 Task
                  |
            Model Router
                  |
--------------------------------
Small Model       Medium Model       Large Model
14B               32B-70B            100B+
普通日志          复杂分析            专家任务
```

---

# 6. 推荐模型组合

## 开发阶段

本地：DeepSeek-Distill, Qwen2.5 14B

用途：测试 Agent

## 企业阶段

推荐：DeepSeek-R1 32B/70B + vLLM

## 超大规模

DeepSeek-V4 + GPU Cluster

---

# 7. 为什么不用直接 Fine-tuning？

很多团队第一步：收集日志 → 训练模型 → 期待 AI 变专家

结果：失败。

原因：模型不知道哪些信息重要、哪些规则必须遵守、哪些案例相关。

正确顺序：RAG → Rule → Agent → Fine Tune

---

# 8. RAG 架构设计

RAG：Retrieval Augmented Generation（检索增强生成）

流程：

```
Question
↓
Embedding
↓
Vector Search
↓
Relevant Knowledge
↓
Prompt Assembly
↓
LLM
↓
Answer
```

---

# 9. RAG 核心组件

## 9.1 Document Storage

保存原始资料。例如：Datasheet, Firmware Manual, Bug Report, 测试报告, 驱动文档, FAQ

技术：MinIO

## 9.2 Vector Database

保存向量。推荐：Milvus

## 9.3 Embedding Model

负责文字转换向量。

推荐中文：BGE-large-zh, BGE-M3

---

# 10. 企业知识库设计

不要一个知识库，分层。

```
Knowledge Base
├── Hardware
├── Driver
├── Firmware
├── Software
├── Test
├── Bug
├── Solution
```

---

# 11. 日志知识库

重点。

结构：

```json
{
    "problem": "设备启动失败",
    "environment": "SS528",
    "log": "kernel panic",
    "rootcause": "driver init fail",
    "solution": "modify probe"
}
```

---

# 12. Bug Case 数据模型

数据库：`bug_cases`

| 字段 | 说明 |
| --- | --- |
| id | 编号 |
| device | 设备 |
| chip | 芯片 |
| module | 模块 |
| symptom | 现象 |
| log | 日志 |
| cause | 原因 |
| solution | 方案 |
| confidence | 可信度 |

---

# 13. Chunk 切分策略

RAG 效果 80% 取决于 Chunk。

错误：整篇日志 10MB 一个 Chunk → 效果很差。

推荐：按照语义切分。

例如：

```
Boot Start
↓
Kernel Init
↓
Driver Init
↓
Network
↓
Application
```

分别切。

---

# 14. 日志专用 Chunk

设计：Log Chunk

```json
{
    "time_range": "10:20-10:21",
    "module": "USB",
    "level": "ERROR",
    "content": "timeout"
}
```

---

# 15. Metadata 设计

每个向量必须带标签。

```json
{
    "chip": "SS528",
    "module": "USB",
    "version": "V2.1",
    "type": "bug"
}
```

---

# 16. 检索策略

不要只用 Vector Search，采用 Hybrid Search。

```
             Query
               |
 ----------------------------
Vector Search  Keyword Search  Rule Match
 ----------------------------
               |
             Merge
```

---

# 17. Reranker 设计

- 第一阶段：召回
- 第二阶段：排序

模型：BGE Reranker

---

# 18. Prompt Assembly

最终输入：

```
System Prompt
+ User Question
+ Log Evidence
+ Knowledge
+ Rules
+ History
```

---

# 19. 诊断 Prompt 模板

例如：

```
你是一名嵌入式系统专家。

任务：分析设备日志。

要求：
1. 找出异常
2. 引用日志证据
3. 判断根因
4. 给解决方案

禁止：无证据猜测。
```

---

# 20. Fine-Tuning 策略

什么时候训练？

满足：RAG 已经成熟 + 有大量案例 + 模型能力不足

---

# 21. 微调数据格式

采用：Instruction Dataset

```json
{
    "instruction": "分析USB错误",
    "input": "logxxx",
    "output": "USB PHY异常..."
}
```

---

# 22. LoRA 微调

推荐 LoRA。原因：成本低。

流程：Base Model + LoRA Adapter = Domain Model

---

# 23. 不建议训练全模型

原因：成本巨大，需要大量 GPU。而领域任务 LoRA 足够。

---

# 24. Agent Memory 设计

长期记忆：

```
Problem
↓
Analysis
↓
Solution
↓
Feedback
```

---

# 25. Feedback 闭环

```
AI Result
↓
Engineer Confirm
↓
Case Database
↓
RAG Update
↓
AI提升
```

---

# 26. 数据治理

所有数据需要标签：

- chip, module, firmware, version, error_type, solution

---

# 27. 数据质量评分

每条知识评分：Quality Score = Accuracy + Completeness + Freshness

---

# 28. AI 数据流水线

架构：

```
Raw Data
↓
Clean
↓
Normalize
↓
Annotate
↓
Embedding
↓
Vector DB
↓
Evaluation
```

---

# 29. 模型评估

指标：

- **Accuracy**：诊断正确率
- **Grounding**：是否引用正确证据
- **Hallucination**：幻觉率

---

# 30. AI 版本管理

模型也需要版本。

例如：`AI-Diagnostic-v1.0`

- Base：DeepSeek-70B
- RAG：KB-v3
- Prompt：v5

---

# 31. Model Registry

类似代码版本。保存：Model, Prompt, Dataset, Evaluation

---

# 32. 推荐实际落地方案

结合嵌入式日志场景：

### 第一阶段

不要训练。使用：DeepSeek API + RAG + 规则库 + Agent

### 第二阶段

本地部署：DeepSeek/Qwen 32B + vLLM

### 第三阶段

积累 5000+ Bug 案例，开始 LoRA。

---

# 33. 最终 AI 架构

```
              AI Engineer
                   |
          --------------------
          Agent  RAG  Rule  Memory  Model
          --------------------
                   |
          Enterprise Knowledge
```

---

> AI Model & RAG Architecture Complete
