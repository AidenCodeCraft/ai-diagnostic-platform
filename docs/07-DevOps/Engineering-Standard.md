# Engineering Standard

AI Diagnostic Platform

Version: 1.0

---

# 1. 工程目标

建立可维护、可测试、可扩展、可部署、可协作的软件工程体系。

目标：支持 10+ 开发人员、100+ 插件开发者、10000+ 企业用户。

---

# 2. Git 仓库设计

采用：Monorepo

原因：前后端、插件、部署文件统一管理。

目录：

```
AI-Diagnostic-Platform/
├── apps/
├── backend/
├── frontend/
├── mobile/
├── desktop/
├── plugins/
├── agents/
├── models/
├── deploy/
├── docs/
├── tests/
└── scripts/
```

---

# 3. Git 分支策略

采用：GitHub Flow + Release Branch

## main

用途：生产稳定版本。

规则：

- 禁止直接提交
- 必须 PR Merge

## develop

用途：开发集成。所有 feature 进入。

## feature

功能开发。

格式：

- feature/log-parser
- feature/rag-engine
- feature/mobile-ui

## bugfix

修复：

- bugfix/parser-crash

## release

发布准备。

例如：release/v1.0.0

## hotfix

紧急修复。

例如：hotfix/security-issue

---

# 4. Commit 规范

采用：Conventional Commit

格式：`type(scope): message`

例如：

- 新增：`feat(parser): add linux kernel parser`
- 修复：`fix(agent): solve memory leak`
- 文档：`docs(api): update api document`
- 测试：`test(rule): add usb rule test`

## Commit 类型

| Type | 说明 |
| --- | --- |
| feat | 新功能 |
| fix | Bug 修复 |
| docs | 文档 |
| style | 格式 |
| refactor | 重构 |
| test | 测试 |
| build | 构建 |
| ci | CI/CD |

---

# 5. Pull Request 规范

所有代码必须 PR。

流程：

```
Developer
↓
Create PR
↓
CI 检查
↓
Code Review
↓
Merge
```

PR 必须包含：

## 描述

解决什么问题。

## 修改内容

例如：新增 USB Parser 插件

## 测试

例如：pytest passed

## Screenshot

UI 修改必须提供。

---

# 6. Code Review 规范

Reviewer 关注：

## 架构

是否符合设计。

## 性能

是否：

- 内存泄漏
- 慢查询

## 安全

是否：

- 注入风险
- 权限漏洞

## 可维护性

是否：

- 模块清晰
- 注释完整

---

# 7. Coding Style

## Python 规范

遵循：PEP8

工具：black, ruff, mypy

示例：

```python
class LogParser:
    def parse(self, content: str):
        """
        Parse log content
        """
        return events
```

## TypeScript 规范

工具：eslint, prettier

## Rust 规范

工具：rustfmt, clippy

## Flutter 规范

工具：dart format, flutter analyze

---

# 8. 项目质量要求

所有模块必须包含：

- README.md
- CHANGELOG.md
- TEST.md

---

# 9. 自动测试体系

测试分层：

```
              E2E Test
                 ↑
          Integration Test
                 ↑
            Unit Test
```

## Unit Test

覆盖：80%

工具：

- Python：pytest
- Frontend：vitest
- Flutter：flutter test

## Integration Test

测试服务之间通信。

例如：

```
Upload Log
↓
Parser
↓
AI
↓
Report
```

## E2E Test

模拟用户。

例如：

```
登录
上传日志
等待分析
查看报告
```

---

# 10. CI/CD 体系

采用：GitHub Actions

流程：

```
Push
  |
Lint
  |
Unit Test
  |
Build
  |
Security Scan
  |
Docker Build
  |
Deploy
```

---

# 11. CI Pipeline

文件：`.github/workflows/`

```
├── backend.yml
├── frontend.yml
├── docker.yml
├── release.yml
```

示例：

```yaml
name: Backend CI

on: push

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - checkout
      - install
      - pytest
```

---

# 12. Docker 规范

所有服务：容器化。

目录：`deploy/docker/`

```
├── backend.Dockerfile
├── frontend.Dockerfile
├── worker.Dockerfile
```

Backend Dockerfile 示例：

```dockerfile
FROM python:3.12
WORKDIR /app
COPY .
RUN pip install -r requirements.txt
CMD ["uvicorn", "main:app"]
```

---

# 13. Docker Compose 开发环境

开发环境：`docker-compose.yml`

包含：

- backend
- postgres
- redis
- milvus
- minio
- ollama

---

# 14. Kubernetes 架构

生产环境：

```
                 Ingress
                    |
              API Gateway
                    |
 ------------------------------------------------
 Backend Pod  Worker Pod  Agent Pod  Parser Pod  LLM Pod
 ------------------------------------------------
                    |
               Database
```

---

# 15. Kubernetes Namespace 设计

```
ai-platform
├── frontend
├── backend
├── ai
├── storage
├── monitoring
```

---

# 16. Kubernetes Deployment

示例：

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: backend
spec:
  replicas: 3
```

---

# 17. Helm Chart

目录：

```
charts/
ai-platform/
├── templates/
├── values.yaml
└── Chart.yaml
```

---

# 18. 配置管理

禁止：代码写配置。

使用：Environment。

例如：`DATABASE_URL`, `MODEL_ENDPOINT`, `VECTOR_DB_URL`

---

# 19. Secret 管理

生产使用 Kubernetes Secret。保存密码、Token、API Key。

---

# 20. 日志系统

所有服务输出结构化日志。

格式：

```json
{
    "time": "",
    "service": "parser",
    "level": "error",
    "message": "failed"
}
```

---

# 21. 监控体系

采用：

- Metrics：Prometheus
- Dashboard：Grafana
- Logging：Loki
- Tracing：OpenTelemetry

---

# 22. 性能监控指标

关注：

- API：QPS, Latency
- AI：Token 消耗, 推理时间
- Agent：Task 成功率
- Parser：MB/s

---

# 23. 安全规范

必须：

- 身份：JWT
- 通信：HTTPS
- 数据：加密存储
- 文件：病毒扫描
- AI：Prompt Injection 防护

---

# 24. Release 流程

版本：Semantic Version

格式：`Major.Minor.Patch`

例如：`v1.0.0`

Release 步骤：

```
Code Freeze
↓
Test
↓
Build Image
↓
Security Scan
↓
Release
↓
Publish
```

---

# 25. 开源规范

GitHub 要求必须包含：

- README.md
- LICENSE
- CONTRIBUTING.md
- CODE_OF_CONDUCT.md
- SECURITY.md
- CHANGELOG.md

---

# 26. License 建议

推荐：Apache License 2.0

原因：商业友好、企业可使用、社区认可。

---

# 27. Issue 管理

标签：

- bug
- feature
- question
- discussion
- security

---

# 28. Roadmap 管理

使用：GitHub Project

状态：

- Todo
- Doing
- Review
- Done

---

> Engineering Standard Complete
