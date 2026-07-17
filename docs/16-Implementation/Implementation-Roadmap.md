# AI Diagnostic Platform 实施开发总计划

Version: 1.0

---

# 目录

1. MVP 开发计划
2. 项目初始化
3. 后端系统设计
4. 前端系统设计
5. 数据库实现
6. Agent 系统实现
7. RAG 知识库实现
8. 部署方案
9. 测试体系
10. 持续优化路线

---

# 1. MVP 开发计划

## 1.1 MVP 目标

目标：在 90 天内完成"上传设备日志 → AI 自动分析 → 输出故障诊断报告"完整闭环。

## 1.2 MVP 核心功能

### 用户功能

| 功能 | 说明 |
| --- | --- |
| 用户登录 | 基础账号 |
| 创建项目 | 设备项目管理 |
| 上传日志 | 支持 zip/log/txt |
| 查看分析 | AI 报告 |
| 管理知识库 | 上传资料 |

### AI 功能

| 模块 | 能力 |
| --- | --- |
| 日志解析 | 提取异常 |
| 规则分析 | 匹配错误模式 |
| RAG | 查询历史案例 |
| Agent | 组织分析流程 |
| 报告生成 | 输出结论 |

## 1.3 MVP 不包含

第一阶段禁止：复杂微服务、Kubernetes、手机 App、模型训练、插件市场、多租户

原因：先验证价值。

---

# 2. 项目初始化指南

## 2.1 技术栈

### 前端

Vue3, TypeScript, Vite, Element Plus, Pinia

### 后端

Python, FastAPI, SQLAlchemy, Pydantic

### AI

DeepSeek API, LangChain/LlamaIndex, Embedding Model

### 数据

PostgreSQL, Milvus, Redis, MinIO

## 2.2 项目目录

```
ai-diagnostic-platform/
├── backend
├── frontend
├── docs
├── data
├── deploy
├── scripts
├── tests
└── README.md
```

---

# 3. 后端系统设计

## 3.1 后端架构

```
             API Gateway
                 |
        ------------------
        User Service
        Log Service
        AI Service
        RAG Service
        Report Service
        ------------------
                 |
          PostgreSQL
```

## 3.2 FastAPI 目录

```
backend/
app/
├── main.py
├── api/
├── core/
├── models/
├── schemas/
├── services/
├── agent/
├── rag/
├── parser/
└── utils/
```

## 3.3 核心服务

### Log Service

负责：上传日志、文件管理、解析任务

接口：`POST /logs/upload`, `GET /logs/{id}`

### Analysis Service

负责：

```
日志
↓
Parser
↓
Agent
↓
Report
```

### Report Service

生成：Markdown, PDF, HTML

---

# 4. 前端系统设计

## 4.1 页面规划

Login, Dashboard, Project, Log Upload, Analysis Result, Knowledge Base, System Setting

## 4.2 前端结构

```
frontend/
src/
├── api/
├── views/
├── components/
├── store/
├── router/
├── utils/
```

## 4.3 核心页面

### Dashboard

显示：项目数量、分析任务、成功率

### Log Upload

功能：选择文件、填写问题描述、提交分析

### Analysis

展示：问题、证据、原因、建议、置信度

---

# 5. 数据库实现

## 5.1 数据库选型

- 业务：PostgreSQL
- 向量：Milvus
- 缓存：Redis
- 文件：MinIO

## 5.2 核心 ER 模型

```
User
  |
Project
  |
Log
  |
Analysis
  |
Report
```

## 5.3 数据表设计

### User

`users`: id, username, password, created_time

### Project

`projects`: id, name, chip, firmware, version

### Log

`logs`: id, project_id, filename, path, status

### Analysis

`analysis`: id, log_id, result, confidence, created_time

### Knowledge

`knowledge`: id, title, category, vector_id

---

# 6. Agent 系统实现

## 6.1 Agent 目标

让 AI 具备：理解任务、调用工具、分析日志、查询知识、生成报告

## 6.2 Agent 架构

```
User
  |
Planner
  |
----------------
Parser Tool  RAG Tool  Rule Tool  Report Tool
----------------
  |
LLM
```

## 6.3 第一版 Agent 流程

```
用户问题
↓
读取日志
↓
提取异常
↓
查询知识库
↓
DeepSeek推理
↓
生成报告
```

## 6.4 Agent 工具

- **Log Parser Tool**：输入 log，输出 error list
- **Knowledge Search Tool**：输入问题，输出历史案例
- **Report Tool**：输出诊断报告

---

# 7. RAG 系统实现

## 7.1 RAG 目标

让 AI 拥有企业经验。

## 7.2 数据来源

包括：芯片手册、驱动文档、Bug 记录、测试报告、FAQ、维修记录

## 7.3 RAG 流程

```
Document
↓
Split
↓
Embedding
↓
Vector DB
↓
Retrieve
↓
LLM
↓
Answer
```

## 7.4 Chunk 策略

日志按照时间、模块、错误等级、功能切分。

## 7.5 Metadata

每个知识保存：chip, module, version, error_type, solution

---

# 8. 部署方案

## 8.1 开发环境

Docker Compose：Frontend, Backend, PostgreSQL, Redis, Milvus

## 8.2 生产环境

```
Nginx
  |
Backend Cluster
  |
AI Service
  |
Database Cluster
```

## 8.3 AI 部署

- **云模式**：DeepSeek API
- **私有模式**：GPU Server + vLLM + DeepSeek/Qwen

## 8.4 Kubernetes

企业版本：Frontend Pod, Backend Pod, AI Pod, Database Pod, GPU Pod

---

# 9. 测试体系

## 9.1 软件测试

包括：Unit Test, Integration Test, API Test, E2E Test

## 9.2 AI 测试

重点：建立 Golden Dataset

结构：log, question, expected_answer, solution

## 9.3 AI 指标

- **Accuracy**：诊断正确率
- **Evidence**：是否引用正确日志
- **Hallucination**：幻觉率

## 9.4 性能测试

测试：10MB 日志、100MB 日志、1GB 日志

指标：解析速度、响应时间、GPU 占用

---

# 10. 持续优化路线

### V0.1 Demo

时间：1 个月

实现：上传日志、AI 分析、报告生成

### V0.5

时间：3 个月

增加：RAG, Agent, 知识库, 历史记录

### V1.0 产品版

时间：6 个月

增加：用户系统, 项目管理, 权限, 部署脚本

### V2.0 企业版

时间：12 个月

增加：多租户, 插件系统, 私有模型, 企业部署

### V3.0 AI 工程师

时间：24 个月

目标：自动分析、自动测试、自动定位、自动修复

---

# 11. 开发优先级

必须遵循：产品价值 > AI 能力 > 工程复杂度

推荐开发顺序：

1. 日志上传
2. 日志解析
3. AI 分析
4. 知识库
5. Agent
6. 产品化
7. 企业化

---

# 12. 最终系统形态

```
                 AI Engineer
                      |
 ------------------------------------------------
 Log Understanding  Knowledge Retrieval  Reasoning
 Debug Planning  Report Generation  Learning
 ------------------------------------------------
                      |
              Embedded Device
```

---

# 结论

这个项目最终不是一个调用大模型分析日志的工具，而是一个面向嵌入式设备、智能硬件、工业设备的 AI 故障诊断工程平台。

核心资产：模型 + 知识库 + Bug 数据 + 工程经验 + Agent 流程

其中模型可以替换，但是领域知识和诊断数据会形成长期壁垒。
