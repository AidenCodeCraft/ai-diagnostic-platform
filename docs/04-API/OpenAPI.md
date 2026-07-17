# OpenAPI Specification

## AI Diagnostic Platform

Version: 1.0

---

# 1. API 设计原则

## 1.1 RESTful

所有接口：HTTP REST API

例如：

- GET
- POST
- PUT
- DELETE

---

## 1.2 API 版本管理

统一：`/api/v1/`

未来：`/api/v2/`

---

## 1.3 数据格式

- 统一：JSON
- 编码：UTF-8

---

## 1.4 时间格式

统一采用 ISO8601 标准，且必须携带时区偏移。

例如：`2026-07-16T18:20:30+08:00`（北京时间）

---

# 2. 服务架构

```
Client
|
API Gateway
|
FastAPI Backend
|
Auth
|
Project
|
Log
|
Analysis
|
Knowledge
|
Agent
|
Report
```

---

# 3. 认证设计

采用：JWT Token

请求：Header

```http
Authorization: Bearer {token}
```

---

# 4. 用户接口

## 4.1 用户注册

`POST /api/v1/auth/register`

Request：

```json
{
    "username": "test",
    "email": "test@test.com",
    "password": "123456"
}
```

Response：

```json
{
    "id": "uuid",
    "username": "test"
}
```

## 4.2 用户登录

`POST /api/v1/auth/login`

Request：

```json
{
    "email": "test@test.com",
    "password": "123456"
}
```

Response：

```json
{
    "access_token": "xxxxx",
    "expire": 3600
}
```

---

# 5. 项目管理 API

## 创建项目

`POST /api/v1/projects`

Request：

```json
{
    "name": "智能终端项目",
    "device": "SS528",
    "version": "1.0.0"
}
```

Response：

```json
{
    "id": "xxx",
    "name": "智能终端项目"
}
```

## 查询项目

`GET /api/v1/projects`

Response：

```json
[
    {
        "id": "1",
        "name": "AI终端"
    }
]
```

## 删除项目

`DELETE /api/v1/projects/{id}`

---

# 6. 日志管理 API

## 上传日志

`POST /api/v1/logs/upload`

Content-Type：multipart/form-data

参数：

- file
- project_id
- device
- version
- description

Response：

```json
{
    "log_id": "xxx",
    "status": "uploaded"
}
```

---

# 7. 日志解析 API

## 开始解析

`POST /api/v1/logs/{id}/parse`

Response：

```json
{
    "task_id": "xxx"
}
```

## 获取解析结果

`GET /api/v1/logs/{id}/events`

Response：

```json
[
    {
        "time": "10:20:30",
        "level": "ERROR",
        "module": "USB",
        "message": "timeout"
    }
]
```

---

# 8. AI 分析 API

核心接口。

## 创建分析任务

`POST /api/v1/analyze`

Request：

```json
{
    "log_id": "xxx",
    "question": "设备启动失败，请分析原因",
    "model": "deepseek"
}
```

Response：

```json
{
    "task_id": "xxx",
    "status": "running"
}
```

---

# 9. 分析状态查询

`GET /api/v1/analyze/{task_id}`

Response：

```json
{
    "status": "running",
    "progress": 60
}
```

状态：

- pending
- running
- success
- failed

---

# 10. AI 流式输出接口

用于：ChatGPT 类似效果。

协议：WebSocket

地址：`/api/v1/ws/analyze/{task_id}`

返回：

```json
{
    "type": "thinking",
    "content": "正在分析USB错误"
}
```

最终：

```json
{
    "type": "final",
    "content": "USB PHY异常"
}
```

---

# 11. 分析结果 API

`GET /api/v1/analyze/{id}/result`

返回：

```json
{
    "summary": "USB无法枚举",
    "root_cause": "PHY初始化失败",
    "confidence": 0.92,
    "evidence": [
        "USB timeout",
        "reset fail"
    ],
    "solution": ["检查PHY配置"]
}
```

---

# 12. 知识库 API

## 创建知识库

`POST /api/v1/knowledge/base`

Request：

```json
{
    "name": "USB知识库",
    "type": "hardware"
}
```

## 上传知识文档

`POST /api/v1/knowledge/document/upload`

支持：

- PDF
- DOCX
- MD
- TXT

## 文档解析

`POST /api/v1/knowledge/document/{id}/parse`

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

# 13. Rule API

## 创建规则

`POST /api/v1/rules`

Request：

```json
{
    "name": "USB_TIMEOUT",
    "pattern": "USB timeout",
    "priority": 10
}
```

## 测试规则

`POST /api/v1/rules/test`

输入日志，返回命中的规则。

---

# 14. Agent API

## 查询 Agent 列表

`GET /api/v1/agents`

返回：

```json
[
    {
        "name": "log_agent",
        "version": "1.0"
    }
]
```

## 执行 Agent

`POST /api/v1/agents/run`

Request：

```json
{
    "agent": "log_agent",
    "task": "分析日志"
}
```

---

# 15. 报告 API

## 获取报告

`GET /api/v1/report/{id}`

## 导出报告

`POST /api/v1/report/export`

参数：

- format：pdf

---

# 16. Dashboard API

## 数据统计

`GET /api/v1/dashboard/statistics`

返回：

```json
{
    "total_logs": 10000,
    "errors": 523,
    "projects": 20
}
```

---

# 17. 搜索 API

全文搜索：

`GET /api/v1/search`

支持搜索：

- 日志
- Bug
- 文档
- 分析记录

---

# 18. OpenAPI YAML 示例

实际项目生成：`openapi.yaml`

示例：

```yaml
openapi: 3.1.0
info:
  title: AI Diagnostic Platform API
  version: 1.0.0
paths:
  /api/v1/analyze:
    post:
      summary: Create Analysis Task
```

---

# 19. API 错误规范

统一：

```json
{
    "code": "AUTH_ERROR",
    "message": "token expired"
}
```

错误码：

| Code | 说明 |
| --- | --- |
| AUTH_ERROR | 认证失败 |
| PERMISSION_DENIED | 权限不足 |
| FILE_TOO_LARGE | 文件过大 |
| MODEL_ERROR | 模型异常 |
| RAG_ERROR | 知识库异常 |
| AGENT_ERROR | Agent 失败 |

---

# 20. API 安全设计

必须：

- JWT
- HTTPS
- Rate Limit
- API Key
- RBAC
- Audit Log

---

# 21. API 未来扩展

## CLI

例如：`diag analyze test.log`

## SDK

提供：Python SDK

例如：

```python
client.analyze("log.txt")
```

## Webhook

支持：分析完成通知。
