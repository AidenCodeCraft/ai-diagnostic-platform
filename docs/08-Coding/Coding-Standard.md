# Coding Standard

AI Diagnostic Platform

Version: 1.0

---

# 1. 编码规范目标

目标：建立统一代码质量标准。

保证：

- 可读性
- 可维护性
- 可扩展性
- 安全性
- 可测试性

---

# 2. 通用原则

## 2.1 KISS 原则

Keep It Simple and Stupid

- 禁止：过度设计
- 推荐：简单明确

---

## 2.2 SOLID 原则

所有核心模块遵循：

- **S**：Single Responsibility
- **O**：Open Closed
- **L**：Liskov Substitution
- **I**：Interface Segregation
- **D**：Dependency Inversion

---

## 2.3 DRY 原则

Don't Repeat Yourself

- 禁止：复制代码
- 应该：抽象公共模块

---

## 2.4 高内聚低耦合

模块之间通过 Interface 通信。

---

# 3. 项目代码结构规范

统一：

```
src/
├── api
├── core
├── models
├── services
├── repositories
├── plugins
├── agents
├── utils
└── tests
```

---

# 4. Python Backend 规范

技术：FastAPI

版本：Python >= 3.12

## 4.1 文件命名

使用：snake_case

正确：

- log_parser.py
- agent_manager.py

错误：

- LogParser.py
- agentManager.py

---

## 4.2 类命名

使用：PascalCase

例如：

```python
class LogAnalyzer:
    pass
```

## 4.3 函数命名

使用：snake_case

例如：

```python
def parse_log():
    pass
```

## 4.4 常量

全部大写。

例如：

```python
MAX_FILE_SIZE = 1024
DEFAULT_TIMEOUT = 30
```

## 4.5 类型标注

必须。

错误：

```python
def parse(data):
```

正确：

```python
def parse(data: str) -> list:
```

## 4.6 Docstring 规范

所有公共接口必须。

例如：

```python
def analyze_log(log_id: str):
    """
    Analyze uploaded log file.

    Args:
        log_id: log identifier

    Returns:
        AnalysisResult
    """
```

---

# 5. Python 代码质量工具

必须：

- **Formatter**：Black — `black .`
- **Linter**：Ruff — `ruff check .`
- **Type Check**：MyPy — `mypy src/`
- **Security**：Bandit — `bandit -r src/`

---

# 6. FastAPI 规范

## Router 分离

禁止：`main.py` 1000 行接口

推荐：

```
routers/
├── auth.py
├── project.py
├── analysis.py
```

---

# 7. Service 层规范

禁止：Controller 写业务。

错误：API → SQL → AI 调用

正确：API → Service → Repository → Database

---

# 8. Repository 规范

数据库访问隔离。

例如：

```python
class LogRepository:
    def get_by_id(self, id):
        pass
```

业务不知道 SQL。

---

# 9. 异常处理规范

禁止：

```python
except:
    pass
```

统一异常：

```python
class AnalysisException(Exception):
    pass
```

API 返回：

```json
{
    "code": "ANALYSIS_FAILED",
    "message": "parser error"
}
```

---

# 10. Async 规范

AI 任务必须异步。

例如：上传日志 → API → Queue → Worker

禁止：`await llm.run()` （阻塞接口）

---

# 11. 数据模型规范

使用 Pydantic。

例如：

```python
class AnalysisRequest(BaseModel):
    log_id: str
    question: str
```

---

# 12. SQL 规范

禁止业务代码直接 SQL。

错误：`cursor.execute()`

使用 ORM。推荐：SQLAlchemy。

---

# 13. 数据库迁移

必须：Alembic。

流程：Model → Migration → Database

---

# 14. Frontend 规范

技术：Vue3 + TypeScript

## 14.1 目录

```
src/
├── views
├── components
├── api
├── stores
├── hooks
├── utils
```

## 14.2 Vue 组件

命名：PascalCase

例如：`LogViewer.vue`, `AnalysisPanel.vue`

## 14.3 状态管理

使用：Pinia

禁止：组件之间传递大量状态。

---

# 15. TypeScript 规范

开启：strict

```json
{
    "strict": true
}
```

---

# 16. API 调用规范

统一封装。

错误：`axios.get()`

正确：`api.analysis.create()`

---

# 17. CSS 规范

推荐：Tailwind CSS

禁止：大量散落 style。

---

# 18. Rust 规范

用途：高性能 Parser。

标准：rustfmt, clippy

命名：

- 函数：snake_case
- 结构体：PascalCase

---

# 19. Flutter 规范

用途：Mobile App。

要求：`flutter analyze`, `flutter test`

---

# 20. AI 代码规范

AI 相关代码特殊要求。

## Prompt 必须版本化

目录：

```
prompts/
├── log_agent_v1.md
├── log_agent_v2.md
```

## 禁止 Hard Code Prompt

错误：

```python
prompt = "你是专家"
```

正确：

```python
load_prompt("log_agent_v1")
```

---

# 21. Model 调用规范

禁止业务代码直接调用 LLM。

错误：`deepseek.chat()`

正确：Service → LLM Provider → DeepSeek Plugin

---

# 22. Agent 代码规范

Agent 必须拆分：

- Planner
- Executor
- Tool
- Memory

禁止：一个 agent.py 超过 500 行。

---

# 23. 日志规范

所有服务：结构化日志。

格式：

```json
{
    "service": "agent",
    "level": "INFO",
    "trace_id": "xxx",
    "message": "task started"
}
```

---

# 24. 注释规范

原则：解释为什么，不要解释是什么。

错误：

```python
# 加1
x += 1
```

正确：

```python
# compensate timestamp offset
x += 1
```

---

# 25. 测试规范

新功能必须测试。

要求：

- Unit Test：80% 覆盖率
- Critical：100%

---

# 26. 文件大小规范

限制：

- Python 单文件：< 500 行
- 函数：< 50 行
- 类：< 300 行

---

# 27. Code Review Checklist

检查：

- 是否符合架构
- 是否有测试
- 是否影响性能
- 是否安全
- 是否有文档

---

# 28. 禁止事项

- 上传敏感信息（密码等）
- 提交大文件（日志进入 Git LFS）
- 删除测试（禁止）

---

# 29. AI 辅助开发规范

允许：Copilot, Claude Code, Codex

但是：AI 生成代码必须人工 Review。

---

# 30. Definition of Done

任务完成标准：

```
Code完成
↓
Test通过
↓
Review通过
↓
Document更新
↓
CI成功
```

---

> Coding Standard Complete
