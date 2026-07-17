# AI Diagnostic Platform

> 企业级 AI 智能日志分析与故障诊断平台

---

# 一、项目介绍

## 项目背景

在软件开发、嵌入式开发、驱动开发以及硬件调试过程中，大量问题都需要依赖日志（Log）进行分析。

传统方式主要依赖经验丰富的研发工程师：

- 阅读数万行日志
- 搜索 ERROR 关键字
- 分析调用关系与上下文
- 查阅芯片规格书
- 查询历史 Bug 案例
- 综合判断故障原因

整个过程耗时且高度依赖个人经验。

本项目旨在利用 **大语言模型（LLM）+ RAG 知识库 + 规则引擎 + 日志解析器（Parser）+ AI Agent**，构建一个企业级 AI 智能诊断平台，实现自动化日志分析、根因定位、历史案例检索及故障报告生成。

---

# 二、项目目标

打造一个能够辅助研发工程师进行日志分析的 AI 平台，降低故障定位时间，提升研发效率。

最终能力包括：

- ✅ 日志自动解析与异常提取
- ✅ 错误自动定位与分类
- ✅ Root Cause 根因分析
- ✅ 历史 Bug 案例检索
- ✅ AI 智能故障推理
- ✅ 自动生成分析报告
- ✅ 企业知识库管理
- ✅ 多模型协同分析
- ✅ Agent 自动诊断流程
- ✅ 插件化扩展生态

最终目标：

> 成为企业研发部门的 AI Engineer。

---

# 三、产品定位

本项目不是一个聊天机器人，而是一个：

> 企业级 AI 智能诊断平台（AI Diagnostic Platform）

服务对象：

- 软件开发工程师
- 嵌入式开发工程师
- 驱动开发工程师
- 测试验证工程师
- FAE 现场应用工程师
- 技术支持与售后分析

---

# 四、产品形态

支持三端统一，所有客户端共用一套后台。

```
                 Web
                  │
        ┌─────────┴─────────┐
        │                   │
 Desktop Client      Mobile Client
        │                   │
        └─────────┬─────────┘
                  │
          AI Diagnostic API
                  │
────────────────────────────────
 Parser  Rule  RAG  Agent  LLM  Report
────────────────────────────────
```

| 客户端 | 技术栈 | 用途 |
|--------|--------|------|
| Web | Vue3 + TypeScript | 企业管理平台 |
| Desktop | Tauri + Rust | 本地日志分析 |
| Mobile | Flutter + Dart | 查看分析结果与告警 |

---

# 五、总体架构

## 分层架构

```
┌─────────────────────────────────┐
│          User Layer             │
│   Web    Desktop    Mobile      │
├─────────────────────────────────┤
│         API Gateway             │
│   Kong / APISIX / Nginx         │
├─────────────────────────────────┤
│       Core Platform Service     │
│ Auth  Project  Log  Analysis    │
│ Knowledge  Agent  Report        │
├─────────────────────────────────┤
│       AI Infrastructure         │
│ LLM Service  Embedding          │
│ Vector DB  Rule Engine          │
│ Parser Engine                   │
├─────────────────────────────────┤
│         Storage Layer           │
│ PostgreSQL  Redis  MinIO  Milvus│
└─────────────────────────────────┘
```

## 项目目录结构

```
ai-diagnostic-platform/
│
├── apps/                    # 应用入口
│
│   ├── web/
│   ├── desktop/
│   └── mobile/
│
│
├── backend/                 # 后端系统
│
│   ├── gateway/
│   ├── services/
│   ├── common/
│   └── migrations/
│
│
├── agents/                  # AI Agent系统
│
│   ├── core/
│   ├── diagnostic/
│   ├── planner/
│   ├── memory/
│   ├── tools/
│   └── prompts/
│
│
├── plugins/                 # 插件生态
│
│   ├── builtin/
│   ├── examples/
│   └── sdk/
│
│
├── ai-models/               # AI模型管理
│
│   ├── llm/
│   ├── embedding/
│   ├── reranker/
│   └── registry/
│
│
├── data/                    # AI数据资产
│
│   ├── raw/
│   ├── processed/
│   ├── datasets/
│   └── knowledge/
│
│
├── libs/                    # 公共库
│
├── configs/                 # 配置
│
├── deploy/                  # 部署
│
├── infra/                   # 基础设施
│
├── docs/                    # 文档
│
├── tests/                   # 测试
│
├── scripts/                 # 工具脚本
│
├── .github/                 # GitHub Actions
│
├── LICENSE
├── README.md
├── CONTRIBUTING.md
└── SECURITY.md

```

---

# 六、核心模块

## 1. Parser（日志解析器）

负责将原始日志解析为结构化事件。

**职责：**

- 日志读取与格式自动识别
- 提取时间戳、线程、模块、级别
- 提取 Error、Warning、Crash 等异常

**支持的日志类型：**

Linux Log, Android Logcat, Windows Event, UART, USB, PCIe, Bluetooth, WiFi, GNSS, Kernel Log

**输出格式：**

```json
{
    "time": "10:20:30",
    "level": "ERROR",
    "module": "USB",
    "message": "device timeout"
}
```

---

## 2. Rule Engine（规则引擎）

负责已知问题的秒级快速定位，无需调用 AI。

**工作原理：**

```
USB timeout
↓
建议：检查 VBUS → 检查 PHY → 检查 USB HUB
```

**目标：** 积累 1000+ 企业级规则

---

## 3. RAG 知识库

企业知识统一管理，为 AI 提供领域经验支撑。

**知识来源：**

PDF, Word, Excel, Markdown, Wiki, FAQ, Git, Issue, Jira, Bug, 芯片规格书, SDK 文档

**处理流程：**

```
Document → Chunk → Embedding → Vector DB → Retrieve → LLM
```

---

## 4. AI Engine

负责综合分析，生成诊断结论。

**输入：**

- 用户描述
- 日志内容
- Rule 匹配结果
- 历史案例
- 知识库文档

**输出：** Root Cause 根因分析

**模型：** 主推 DeepSeek，后期支持 Qwen, Llama, GLM。通过统一 LLM Provider 接口实现模型无关。

---

## 5. Agent

AI 自主执行分析流程。

**自动流程：**

```
① 分类日志 → ② 查Rule → ③ 查知识库
→ ④ 查历史Bug → ⑤ 综合分析 → ⑥ 输出报告
```

**Agent 类型：**

- Log Agent：日志分析
- Bug Agent：Bug 关联
- Search Agent：知识搜索
- Report Agent：报告生成
- Document Agent：文档处理

后期增加：Code Agent（代码分析）

---

## 6. Report Engine

自动生成诊断报告。

**支持格式：** Markdown, PDF, HTML, Word

**支持企业自定义模板。**

---

# 七、架构设计原则

| 原则 | 说明 |
|------|------|
| **Model Agnostic** | 模型无关，通过统一接口支持多种 LLM |
| **Plugin Driven** | 插件驱动，Parser/Rule/Agent 均可扩展 |
| **Cloud Native** | 支持 Docker + Kubernetes 微服务部署 |
| **API First** | 所有能力 API 化，支持多端调用 |

---

# 八、产品开发路线

## Phase 1：MVP（3~4 周）

**目标：** 完成上传日志 → AI 分析 → 生成报告的完整闭环

**功能：** 用户登录、日志上传、DeepSeek 分析、Markdown 报告

---

## Phase 2：Parser（4 周）

**目标：** 日志解析框架

**支持：** Linux, Android, UART, USB, Bluetooth, Kernel

**能力：** 事件流（TimeLine）、调用链分析

---

## Phase 3：Rule Engine（3 周）

**目标：** 建立 1000+ 规则

**能力：** 错误码匹配、异常模式识别、快速定位（无需 AI）

---

## Phase 4：RAG 知识库（4 周）

**目标：** 企业知识库

**支持：** PDF, FAQ, SDK, Bug, Issue, Git

**能力：** 自动 Embedding 与向量检索

---

## Phase 5：AI Agent（4 周）

**目标：** 自动分析流程

**能力：** AI 自主检索、分析、推理、报告

---

## Phase 6：企业版（6 周）

**目标：** 企业级功能

**能力：** 项目管理、权限控制、团队协作、Dashboard、分析统计、模型管理、开放 API

---

# 九、技术栈

| 层级 | 技术选型 |
|------|----------|
| **Web 前端** | Vue3 + TypeScript + Naive UI |
| **桌面端** | Tauri + Rust |
| **移动端** | Flutter + Dart |
| **后端** | FastAPI + Python |
| **数据库** | PostgreSQL + Redis + MinIO |
| **向量数据库** | FAISS（开发）/ Milvus（生产） |
| **Embedding** | BGE-M3 |
| **LLM** | DeepSeek（主推），后期 Qwen/Llama/GLM |
| **推理框架** | vLLM（生产）/ Ollama（开发） |
| **AI 框架** | LangGraph + LlamaIndex |
| **部署** | Docker + Docker Compose + Kubernetes（后期） |

---

# 十、数据库设计

主要数据表：

| 表名 | 说明 |
|------|------|
| User | 用户信息 |
| Project | 项目与设备管理 |
| LogFile | 日志文件元数据 |
| AnalysisTask | AI 分析任务 |
| AnalysisResult | 分析结果 |
| Rule | 诊断规则 |
| Knowledge | 知识库文档 |
| Embedding | 向量索引 |
| BugCase | 历史 Bug 案例 |
| PromptTemplate | Prompt 模板管理 |
| ChatHistory | 对话历史 |
| ModelConfig | 模型配置 |
| Report | 报告记录 |
| SystemConfig | 系统配置 |

---

# 十一、架构演进路线

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

---

# 十二、未来规划（Roadmap）

| 版本 | 目标 |
|------|------|
| V1 | 日志分析与基础诊断 |
| V2 | 企业知识库与 RAG |
| V3 | AI Agent 自主诊断 |
| V4 | Code Review 代码分析 |
| V5 | 自动修复建议 |
| V6 | 多 Agent 协同诊断 |
| V7 | 企业 AI 研发助手 |

---

# 十三、文档体系

本项目包含完整的 15 份技术文档：

| 编号 | 文档 | 说明 |
|------|------|------|
| 01 | 产品需求文档（PRD） | 产品定义与需求 |
| 02 | 软件架构文档（SAD） | 系统架构设计 |
| 03 | 数据库设计（ER） | 数据模型 |
| 04 | API 规范（OpenAPI） | 接口体系 |
| 05 | 插件开发规范 | 插件生态 |
| 06 | Agent 架构 | AI 大脑设计 |
| 07 | DevOps 标准 | 工程体系 |
| 08 | 编码规范 | 代码标准 |
| 09 | 部署架构 | 部署方案 |
| 10 | 安全设计 | 企业安全 |
| 11 | 开源治理 | 社区规范 |
| 12 | 测试体系 | 质量保障 |
| 13 | AI 模型与 RAG | AI 核心架构 |
| 14 | 企业架构 | 商业架构 |
| 15 | 产品路线图 | 未来发展 |

---

最终目标：打造一款真正能够辅助研发、测试和技术支持团队进行故障分析的企业级 AI 平台。
