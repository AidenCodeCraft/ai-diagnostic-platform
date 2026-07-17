# Plugin Development Specification

AI Diagnostic Platform

Version: 1.0

---

# 1. 插件系统设计目标

插件系统用于实现：

- 功能扩展
- 第三方开发
- 企业自定义
- 行业适配

核心原则：

- Core Stable
- Plugin Flexible
- 核心代码不感知具体插件。

---

# 2. 插件类型

平台支持：

```
Plugin
├── Parser Plugin
├── Rule Plugin
├── Agent Plugin
├── LLM Provider Plugin
├── Knowledge Plugin
├── Report Plugin
```

---

# 3. 插件生命周期

所有插件统一生命周期。

```
Install
↓
Load
↓
Initialize
↓
Register
↓
Running
↓
Disable
↓
Uninstall
```

---

# 4. 插件目录规范

所有插件：

```
plugins/
├── parser-linux/
├── parser-android/
├── rule-usb/
├── agent-log/
└── llm-deepseek/
```

标准结构：

```
plugin-name/
├── plugin.yaml
├── README.md
├── src/
├── tests/
├── docs/
└── requirements.txt
```

---

# 5. 插件描述文件

文件：`plugin.yaml`

示例：

```yaml
name: usb-parser
version: 1.0.0
type: parser
author: AI Diagnostic Team
description: USB log parser
runtime: python
entry: main.USBParser
dependencies:
  - pyusb
```

# 6. Parser Plugin 规范

## 6.1 职责

负责：

```
原始日志
↓
结构化事件
```

- 输入：log file
- 输出：LogEvent

## 6.2 Parser 接口

Python 示例：

```python
class ParserPlugin:
    def initialize(self):
        pass

    def parse(self, log):
        pass

    def close(self):
        pass
```

## 6.3 Event 数据结构

统一：

```json
{
    "time": "10:20:30",
    "level": "ERROR",
    "module": "USB",
    "message": "timeout"
}
```

# 7. Rule Plugin 规范

## 7.1 职责

快速发现已知问题。

例如：

```
USB timeout
↓
USB PHY问题
```

## 7.2 Rule 结构

目录：

```
rule-usb/
├── rules/
├── usb_timeout.yaml
```

规则：

```yaml
name: USB_TIMEOUT
version: 1.0
match:
  keywords:
    - USB timeout
priority: 10
action:
  type: diagnosis
result:
  reason: USB PHY failure
```

## 7.3 Rule 接口

```python
class Rule:
    def match(self, event):
        pass

    def execute(self, event):
        pass
```

# 8. Agent Plugin 规范

Agent 是最高级插件，负责自主任务。

## 8.1 Agent 结构

```
agent-log/
├── manifest.yaml
├── planner.py
├── tools.py
└── prompt/
```

## 8.2 Agent 定义

```yaml
name: log_agent
version: 1.0
type: agent
tools:
  - parser
  - search
  - llm
```

## 8.3 Agent 接口

```python
class Agent:
    def plan(self, task):
        pass

    def execute(self):
        pass

    def result(self):
        pass
```

# 9. LLM Provider Plugin

目的：模型无关。

支持：

- DeepSeek
- Qwen
- Llama
- GPT
- Claude

接口：

```python
class LLMProvider:
    def chat(self, message):
        pass

    def stream(self, message):
        pass

    def embedding(self, text):
        pass
```

配置：

```yaml
provider: deepseek
model: deepseek-v4
endpoint: http://localhost:8000
```

# 10. Knowledge Plugin

负责：知识来源。

支持：

- PDF
- Git
- Wiki
- Jira
- Database

接口：

```python
class KnowledgeProvider:
    def load(self):
        pass

    def search(self, query):
        pass
```

---

# 11. Report Plugin

负责：输出格式。

支持：

- Markdown
- PDF
- Word
- HTML

接口：

```python
class ReportGenerator:
    def generate(self, data):
        pass
```

---

# 12. 插件通信规范

统一：Event Bus。

架构：

```
Plugin
  |
Event
  |
Message Bus
  |
Core
```

推荐：

- 开发：Redis Stream
- 生产：Kafka

---

# 13. Plugin SDK

官方提供：`ai-diagnostic-sdk`

安装：

```bash
pip install ai-diagnostic-sdk
```

开发者：

```python
from diagnostic import Parser

class MyParser(Parser):
    def parse(self, data):
        return events
```

---

# 14. 插件权限

插件声明：

```yaml
permissions:
  filesystem: read
  network: false
  model: true
```

---

# 15. 插件安全

生产环境：插件运行于 Sandbox。

限制：

- 文件权限
- 网络权限
- CPU
- Memory

技术：

- Docker
- gVisor
- WASM

---

# 16. 插件市场设计

未来：Plugin Marketplace。

类似：VSCode Marketplace。

插件：

- USB Analyzer
- Bluetooth Analyzer
- CAN Analyzer
- Android Analyzer

---

# 17. 插件版本管理

采用：Semantic Version

格式：`Major.Minor.Patch`

例如：`1.2.3`

规则：

- **Major**：破坏性更新
- **Minor**：新增功能
- **Patch**：Bug 修复

---

# 18. 插件测试规范

每个插件必须包含：

```
tests/
├── unit
├── integration
└── benchmark
```

---

# 19. 官方插件列表

初始：

| 类型 | 插件 |
|------|------|
| Parser | parser-linux, parser-android, parser-uart, parser-usb, parser-kernel |
| Rule | rule-usb, rule-bluetooth, rule-memory, rule-network |
| Agent | log-agent, bug-agent, report-agent |
| LLM | llm-deepseek, llm-qwen, llm-openai |

---

# 20. 插件未来生态

最终目标：

```
Community
    |
 Plugin
    |
 AI Diagnostic Platform
```

形成 AI 诊断生态。

---

> Plugin Specification Complete
