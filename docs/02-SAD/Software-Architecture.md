# Software Architecture Document

# AI Diagnostic Platform

Version: 1.0

---

# 1. 文档目的

本文档描述 AI Diagnostic Platform 的整体软件架构设计。

目标：

- 定义系统边界
- 明确模块职责
- 指导开发实现
- 支持未来扩展

---

# 2. 系统定位

AI Diagnostic Platform 是一个：

> 基于大语言模型、大规模知识检索、规则推理和智能 Agent 的企业级故障诊断平台。

系统能力：

- 日志解析
- 异常检测
- 根因分析
- 知识检索
- AI 推理
- 自动报告
- 企业知识沉淀

---

# 3. 架构设计原则

## 3.1 Model Agnostic

模型无关。

支持：

- DeepSeek
- Qwen
- Llama
- GLM
- GPT

通过统一接口：LLM Provider Interface

---

## 3.2 Plugin Driven

插件驱动。

所有扩展能力：

- Parser
- Rule
- Agent
- Knowledge Provider

均采用插件。

---

## 3.3 Cloud Native

支持：

- Docker
- Kubernetes
- 微服务部署

---

## 3.4 API First

所有能力：API 化。

支持：

- Web
- Mobile
- Desktop
- CLI

---

# 4. 总体架构

```
                User
                 |
    --------------------------------
    Web       Desktop       Mobile
                 |
          API Gateway
                 |
    --------------------------------
    Core Platform Service

    Auth Service
    Project Service
    Log Service
    Analysis Service
    Knowledge Service
    Agent Service
    Report Service

    --------------------------------
                 |
         AI Infrastructure

    LLM Service
    Embedding Service
    Vector Database
    Rule Engine
    Parser Engine

    --------------------------------
    Storage Layer

    PostgreSQL
    Redis
    MinIO
    Milvus
```

---

# 5. 微服务设计

## 5.1 API Gateway

职责：

- 请求路由
- 鉴权
- 限流
- API 版本管理

技术推荐：

- Kong
- APISIX
- Nginx

---

## 5.2 Auth Service

负责：用户认证。

功能：

- 用户注册
- 登录
- OAuth
- JWT
- RBAC 权限

---

## 5.3 Log Service

负责：日志生命周期管理。

功能：

- 上传
- 存储
- 下载
- 标签
- 删除

---

## 5.4 Parser Service

核心服务。

负责：日志解析。

输入：xxx.log

输出：

```json
{
    "time": "10:20:30",
    "level": "ERROR",
    "module": "USB",
    "message": "timeout"
}
```

---

## 5.5 Analysis Service

负责：AI 分析任务。

流程：

```
Log
↓
Parser
↓
Rule
↓
RAG
↓
LLM
↓
Report
```

---

## 5.6 Knowledge Service

负责：知识库管理。

支持：

- PDF
- Word
- Markdown
- Wiki

流程：

```
Document
↓
Chunk
↓
Embedding
↓
Vector DB
```

---

## 5.7 Agent Service

负责：AI Agent。

包括：

- Log Agent
- Search Agent
- Bug Agent
- Report Agent

---

## 5.8 Report Service

负责：报告生成。

支持：

- Markdown
- PDF
- HTML

---

# 6. AI 架构设计

```
                 User Question
                       |
                       |
              Context Builder
                       |
        ----------------------------
        |                          |
        Rule Engine                 RAG
        |                          |
        ----------------------------
              Agent
                |
                LLM
                |
                Report
```

---

# 7. 数据流

```
用户上传日志
        |
Log Service
        |
Parser
        |
Event Extraction
        |
Rule Engine
        |
Knowledge Retrieval
        |
Agent Planning
        |
DeepSeek
        |
Report
```

---

# 8. 扩展能力

未来支持：

## 新日志格式

增加：plugins/parser_xxx

无需修改核心。

## 新模型

增加：plugins/llm_xxx

## 新 Agent

增加：agents/xxx

---

# 9. 高可用设计

生产环境：

```
LoadBalancer
     |
API Gateway
     |
Service Cluster
     |
Database Cluster
```

支持：

- 水平扩展
- 服务发现
- 自动恢复

---

# 10. 安全设计

包括：

- 用户隔离
- 项目隔离
- 数据权限
- API Token
- 日志脱敏
- 文件病毒扫描

---

# 11. 性能目标

MVP：

- 单日志：< 30 秒

生产：支持 1000+ 并发用户

- 单日志：GB 级

---

# 12. 架构演进路线

```
V1: Monolith
↓
V2: Modular Monolith
↓
V3: Microservice
↓
V4: Cloud Native
↓
V5: AI Agent Platform
```
