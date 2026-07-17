# Deployment Architecture Specification

AI Diagnostic Platform

Version: 1.0

---

# 1. 部署目标

系统支持：

## 开发环境

Developer Laptop

## 测试环境

CI Server

## 企业私有部署

On-Premise

## 云部署

Cloud Native

---

# 2. 总体部署架构

```
Client: Web Desktop Mobile CLI
                |
                | HTTPS
                |
          API Gateway
                |
Backend Services: Auth, Project, Log, Analysis, Agent, Report
                |
AI Layer: Agent Runtime, RAG Engine, LLM Gateway
                |
Storage Layer: PostgreSQL, Redis, MinIO, Milvus, Elasticsearch
```

---

# 3. 三端应用架构

## 3.1 Web 端

- 技术：Vue3 + TypeScript
- 用途：企业管理平台
- 功能：项目管理、日志上传、AI 分析、报告查看、知识库管理
- 部署：Nginx

---

## 3.2 Desktop 端

推荐：Tauri

原因：相比 Electron 更轻量、内存更低、安全性更高。

功能重点：本地日志分析。

例如：

```
工程师电脑：设备日志
↓
Desktop App
↓
上传服务器
```

---

## 3.3 Mobile 端

- 技术：Flutter
- 用途：查看分析结果、告警、报告
- 不承担：大模型推理

---

# 4. 开发环境部署

目标：一台开发电脑运行。

架构：

```
Docker Compose
    |
Backend Frontend PostgreSQL Redis MinIO Milvus Ollama
```

---

# 5. Docker Compose 架构

目录：`deploy/docker-compose.yml`

包含：

- backend
- worker
- postgres
- redis
- minio
- milvus
- ollama

---

# 6. Backend 服务

- 职责：API 入口
- 部署：Docker
- 资源：CPU 2-4 核，Memory 4GB

---

# 7. Worker 服务

非常重要。负责异步任务。

例如：

```
上传10GB日志
↓
Worker处理
↓
Agent分析
```

技术：Celery 或者 Temporal

---

# 8. AI 服务架构

核心：LLM Gateway。不要业务直接调用模型。

架构：

```
Agent
  |
LLM Gateway
  |
DeepSeek Qwen Llama OpenAI
```

---

# 9. DeepSeek 部署方案

## 方案 A：API 调用

适合：开发阶段。

架构：Backend → DeepSeek API

优点：简单。

缺点：数据离开企业。

---

## 方案 B：本地部署

适合：企业。

架构：

```
Agent
  |
vLLM
  |
DeepSeek Model
  |
GPU
```

---

# 10. DeepSeek-V4-Flash-Base 部署分析

DeepSeek-V4-Flash-Base：284B / 13B / 1M Context

这类模型属于超大参数模型。

## 个人电脑

不推荐。

原因：284B 模型 FP16 约 568GB 显存，还未计算 KV Cache。运行需要多张 80GB GPU。

## 企业服务器

推荐 GPU 集群。例如：8 × NVIDIA H100 80GB。或者国产：昇腾、寒武纪、沐曦。

## 普通开发环境

建议小模型，例如 7B~32B。用途：开发测试。

---

# 11. 推荐模型架构

不要一个模型解决全部，推荐模型分层。

```
             Task
              |
         Model Router
              |
小模型 7B-14B     中模型 32B-70B     大模型 100B+
普通分析           复杂分析           专家诊断
```

---

# 12. 推荐本地模型方案

## 开发阶段

电脑：16GB 显存。

使用：Qwen2.5-14B / DeepSeek Distill 14B

## 企业阶段

GPU 服务器推荐：DeepSeek-R1 70B → vLLM

## 超大型企业

DeepSeek-V4 → GPU Cluster

---

# 13. vLLM 部署架构

```
         API
          |
      vLLM Server
          |
    Model Worker
          |
         GPU
```

优势：

- 高吞吐
- Batch 推理
- OpenAI 兼容接口
- 多用户支持

---

# 14. RAG 部署架构

```
Document
  |
Parser
  |
Chunk
  |
Embedding
  |
Milvus
  |
Retriever
  |
LLM
```

组件：

## MinIO

保存原始文件。例如：datasheet.pdf, bug.docx, log.zip

## Milvus

保存向量。

## PostgreSQL

保存元数据。

---

# 15. 生产环境 Kubernetes 架构

```
             User
              |
          Ingress
              |
         API Gateway
              |
Backend Pods  Worker Pods  Agent Pods  Parser Pods  LLM Gateway
              |
PostgreSQL  Redis  Milvus  MinIO
```

---

# 16. GPU 节点设计

节点：GPU Node

运行：vLLM, Embedding, Reranker

示例：GPU Node 8 × H100, CUDA, NVIDIA Container Toolkit

---

# 17. 服务拆分

生产：微服务

- auth-service
- project-service
- log-service
- analysis-service
- agent-service
- knowledge-service
- report-service

---

# 18. 高可用设计

## Backend

Replica >= 3

## Database

PostgreSQL：Primary + Replica

## Redis

Redis Cluster

## Object Storage

MinIO：Distributed Mode

---

# 19. 大日志处理方案

问题：日志可能几十 GB，不能一次加载。

方案：Streaming Parser

流程：

```
Upload
  ↓
Chunk
  ↓
Stream Parse
  ↓
Event Queue
  ↓
Analysis
```

---

# 20. 消息队列设计

推荐：Kafka

架构：

```
Parser
  |
Kafka
  |
Agent
  |
Report
```

用途：削峰。

---

# 21. 部署模式总结

## 个人开发

Docker Compose + 小模型

## 小团队

单服务器 + GPU + K8s

## 企业

Kubernetes + GPU Cluster + Private Model

---

# 22. 备份方案

数据每日备份。包括：PostgreSQL, MinIO, Milvus

---

# 23. 监控方案

- 监控：Prometheus（CPU, GPU, Memory, API）
- 仪表盘：Grafana Dashboard
- 日志：Loki
- 链路：OpenTelemetry

---

# 24. 灰度发布

生产更新：

```
v1.0
  |
10% 用户
  |
50% 用户
  |
100%
```

---

# 25. 私有化交付

企业客户提供：

- Docker Image
- Helm Chart
- Install Script
- Documentation
