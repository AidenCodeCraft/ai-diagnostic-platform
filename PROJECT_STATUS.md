# AI Diagnostic Platform
# 项目状态

## 当前版本

v1.0.0 — 企业版

---

## 已完成

### Commit 001 — 项目初始化

状态：✅ 完成

### Commit 002 — 后端 FastAPI 初始化

- FastAPI 应用框架
- API Router 路由系统
- 配置系统（Settings / .env）
- Docker 支持

状态：✅ 完成

### Commit 003 — 数据库层

- PostgreSQL 集成
- SQLAlchemy ORM
- Alembic 数据库迁移
- 初始数据模型（User, Project, Log, Analysis, Report, Knowledge）

状态：✅ 完成

### Commit 004 — 日志管理服务

- 日志上传 API
- 文件存储（本地文件系统）
- 日志元数据（文件名、大小、设备、版本、描述）
- 日志状态机（uploaded → parsing → parsed → analyzing → analyzed）
- 完整 CRUD（GET / PUT / DELETE）
- 状态转换校验

状态：✅ 完成

### Commit 005 — 日志解析引擎

- 可插拔解析器架构（BaseParser + ParserRegistry）
- Linux syslog 解析器（传统格式 + ISO 格式）
- Kernel dmesg 解析器（内核缓冲区格式）
- 通用降级解析器
- LogReader（支持大文件流式读取）
- 错误分类体系（timeout, filesystem, memory, panic, oom, io_error 等）
- 规则引擎（诊断建议生成）

状态：✅ 完成

### Commit 006 — 分析任务服务

- 统一 AnalysisTaskService
- 任务生命周期管理（pending → running → completed / failed）
- 状态追踪与时间戳记录
- 分页查询与状态过滤
- 结构化分析结果持久化

状态：✅ 完成

### Commit 007 — DeepSeek LLM 集成

- DeepSeek Provider（支持重试与优雅降级）
- Mock Provider（开发阶段默认）
- OpenAI-compatible Provider（支持 Qwen/Llama/GPT/Ollama 等）
- JSON 响应解析（直接解析 / markdown 代码块 / 兜底提取）
- 置信度区间限制 [0.0, 1.0]
- Prompt 模板系统（独立文件管理，版本化）
- Provider 健康检查
- Provider 动态注册（`register_openai_compatible`）

状态：✅ 完成

### Commit 008 — Agent 框架

- BaseAgent 抽象基类 + 执行引擎
- AgentState 状态机（CREATED → PLANNING → PLAN_READY → EXECUTING → VALIDATING → COMPLETED / FAILED）
- Tool 系统（Tool ABC + ToolRegistry + ToolResult）
- 内置工具：parse_log / rule_check / llm_analyze / generate_report
- SimplePlanner 规划器
- DiagnosticAgent 完整诊断流程编排
- Agent 任务持久化与查询

状态：✅ 完成

### Commit 009 — RAG 知识库

- 知识文档完整 CRUD
- 混合搜索（向量搜索 + 关键词降级）
- 分类管理（category 枚举）
- 文档类型（manual, faq, bug_report, datasheet）
- 搜索结果摘要提取
- VectorService — Milvus 向量搜索接口（含关键词降级）
- 多格式文档导入（Markdown / 纯文本，`POST /knowledge/upload`）
- 自动分块（DocumentImporter）

状态：✅ 完成

### Commit 010 — 诊断报告系统

- 从分析结果自动生成诊断报告
- 报告 CRUD + 分页
- Markdown 格式导出
- 报告元数据（标题、格式、时间戳）

状态：✅ 完成

### Commit 011 — 前端 Web 应用

- Vue3 + TypeScript + Vite + Element Plus（中文语言包）
- **对话式主界面**（参考 DeepSeek + ChatGPT）：
  - 输入框融合附件上传，支持拖拽日志文件
  - 分析结果以对话气泡形式渐进式呈现
  - 模型切换下拉框（Mock / DeepSeek）
  - 「生成诊断报告」按钮按需触发
  - 新对话状态：提示语 + 输入框整体居中
  - 开始对话后输入框平滑过渡至底部
- **左侧边栏**（参考 ChatGPT）：
  - 顶部：搜索 + 侧栏展开/收缩（圆形按钮 flex 并排）
  - 「新对话」按钮
  - 知识库 / 插件管理 / 诊断报告入口
  - 最近对话列表（自动归档 + 智能标题生成 + hover 更多操作）
  - 对话菜单：重命名 / 置顶 / 分析 / 删除
  - 底部用户区（头像 + 用户名 → 设置/帮助/退出）
  - 侧栏收起时浮动展开按钮
- **设置弹窗**：
  - 平滑缩放动画（cubic-bezier 缓动）
  - 左右分栏结构（导航 + 内容）
  - 固定窗口尺寸（680×520px），切换 tab 不跳动
  - 通用设置：主题（浅色/深色/跟随系统）+ 语言
  - 账号管理 / 数据管理 / 服务协议
- Axios API 客户端层
- Vite 开发代理（/api → backend:8000）
- Docker 构建 + Nginx 生产部署

状态：✅ 完成

### Commit 012 — 桌面客户端

- 技术栈：Tauri + Rust
- 本地日志分析能力
- 计划中（需 Tauri 开发环境）

状态：⏳ 计划中

### Commit 013 — 移动客户端

- 技术栈：Flutter + Dart
- 查看分析结果与告警
- 计划中（需 Flutter 开发环境）

状态：⏳ 计划中

### Commit 014 — 插件系统

- 插件 SDK：PluginBase / PluginManifest / PluginManager
- 6 种插件类型：parser / rule / agent / llm / knowledge / report
- 完整生命周期：install → load → initialize → running → disable → uninstall
- 内置插件：USB 日志解析器（8 种错误模式）、Bluetooth 日志解析器（5 种错误模式）
- 插件管理 API（list / stats / toggle）
- 模型列表 API（`GET /plugins/models`）
- 插件自动注册内置解析器

状态：✅ 完成

### Commit 015 — 生产部署

- Docker Compose 四服务编排（PostgreSQL + Redis + Backend + Frontend）
- 一键启动：`docker compose up -d --build` → `http://localhost`
- 多阶段 Docker 构建
- Nginx 反向代理（SPA 路由 + /api/ 转发到后端）
- 所有服务健康检查
- 环境变量配置模板（.env.example）
- Alembic 启动时自动执行数据库迁移
- 国内镜像加速（pip 清华源 + npm 淘宝源）

状态：✅ 完成

### v0.5 — 平台化增强（全部完成）

| 优先级 | 模块 | 状态 |
|--------|------|------|
| 🔴 P0 | 用户认证系统 | ✅ |
| 🔴 P0 | 项目管理 | ✅ |
| 🔴 P0 | Milvus 向量搜索 | ✅ |
| 🔴 P0 | 对话式交互界面 | ✅ |
| 🔴 P0 | 模型插件化管理 | ✅ |
| 🔴 P0 | 左侧边栏重构 | ✅ |
| 🔴 P0 | 多轮实时对话 | ✅ |
| 🟡 P1 | 多格式知识导入 | ✅ |
| 🟡 P1 | 扩展解析器 | ✅ |
| 🟡 P1 | 规则引擎增强 | ✅ |
| 🟢 P2 | LLM 多模型支持 | ✅ |

---

## 测试覆盖

**172 个测试 — 全部通过**

| 模块 | 测试数 |
|------|--------|
| Agent 框架 | 21 |
| 日志管理 | 14 |
| 解析引擎 | 37 |
| 分析任务 | 15 |
| LLM 集成 | 12 |
| 知识库 | 18 |
| 报告系统 | 6 |
| 插件系统 | 20 |
| 项目管理 | 7 |
| 用户认证 | 7 |
| 健康检查 & 配置 | 8 |
| 集成测试 | 7 |
| **总计** | **172** |

---

## 系统架构

```
apps/web/         — Vue3 前端应用（对话式界面 + 侧栏）
  src/
    layouts/      — ChatLayout（核心布局 + 设置弹窗）
    views/        — ChatView / KnowledgeBase / PluginManager / ReportList
    api/          — chat / knowledge / reports
    router/       — 4 条路由

backend/          — FastAPI 后端
  app/
    api/          — REST API（13 个模块）
    agents/       — Agent 框架（core / planner / tools）
    models/       — SQLAlchemy 模型（7 张表）
    schemas/      — Pydantic Schema
    services/     — 业务逻辑（14 个服务）
      parser/     — 可插拔解析引擎
      providers/  — LLM Provider（DeepSeek / Mock / OpenAI Compatible）
      prompts/    — Prompt 模板
    database/     — 数据库会话管理
  migrations/     — Alembic 迁移（11 个版本）

plugins/          — 插件 SDK + 内置插件
  sdk/            — PluginBase / PluginManifest / PluginManager
  builtin/        — USB / Bluetooth 解析器

deploy/           — Docker Compose + 部署文档
```

## 一键启动

```bash
cd deploy
docker compose up -d --build
```

启动后浏览器访问 **http://localhost** 即可使用。

---

## 阶段三：核心对话功能完善 🚧

> **归属**: v1.0 企业版  
> **优先级**: 🔴 最高 — 打通平台核心价值链路  
> **目标**: 实现真正的多轮 AI 诊断对话，v1.0 所有功能可正常使用  

### 现状诊断

```
┌─────────────────────────────────────────┐
│  前端 ChatLayout    ← ChatGPT 风格 UI    │
│  ✅ 侧栏 / 气泡 / 文件上传               │
│  ❌ 消息存 localStorage，不调后端 chat    │
└──────────────┬──────────────────────────┘
               │ 断开的
┌──────────────┴──────────────────────────┐
│  后端 ChatSession CRUD  ← 完整持久化     │
│  ✅ 会话/消息/级联删除/分页               │
│  ❌ 没有 sendMessage → LLM 的方法        │
└──────────────┬──────────────────────────┘
               │ 断开的
┌──────────────┴──────────────────────────┐
│  Agent + LLM Provider  ← 完整引擎        │
│  ✅ BaseAgent / DeepSeek / OpenAI兼容    │
│  ❌ 只支持一次性诊断，不支持 chat()       │
└─────────────────────────────────────────┘
```

### P0 — 打通基础多轮对话

| 任务 | 层 | 说明 |
|------|-----|------|
| `BaseProvider.chat(messages[])` | Provider | 新增多轮对话方法，DeepSeek + OpenAI 兼容 Provider 均实现 |
| `ChatService.send_message()` | Service | 组装历史消息 → 调用 LLM Provider.chat() → 存储 AI 回复 → 返回 |
| `POST /chat-sessions/{id}/chat` | API | 新增聊天端点，接收用户消息返回 AI 回复 |
| `chat.ts` 新增 API 方法 | 前端 API | `createSession()` / `sendMessage()` / `getMessages()` |
| `ChatLayout.sendMessage()` 改造 | 前端 UI | 从 localStorage 改为调用后端 chat API，对话历史服务端持久化 |
| 对话历史从 localStorage 迁移 | 数据 | 最近对话列表从服务端加载，支持跨设备同步 |

### P1 — 流式输出

| 任务 | 说明 |
|------|------|
| Provider 支持 stream 模式 | 使用 SSE 逐 token 返回 |
| `POST /chat-sessions/{id}/stream` | SSE 端点 |
| 前端 EventSource 流式渲染 | 逐字打字效果，替代等待 spinner |

### P2 — 诊断聊天智能化

| 任务 | 说明 |
|------|------|
| `DiagnosticChatAgent` | 基于 Agent 框架的多轮诊断对话 Agent |
| Function Calling / Tool Use | LLM 在对话中触发日志解析/知识库搜索/分析工具 |
| 上下文自动注入 | 上传日志后分析结果自动注入对话上下文 |
| 追问与澄清 | Agent 主动追问缺失信息（设备型号、固件版本等） |

### P3 — 体验增强

| 任务 | 说明 |
|------|------|
| 对话分支 | 用户可回溯到某条消息重新生成回复 |
| 消息操作 | 复制 / 重新生成 / 点赞踩 |
| 上下文窗口管理 | 长对话自动摘要压缩，避免超出 token 限制 |
| Markdown 渲染 | AI 回复中的表格/代码块正确渲染 |

### 工作量估算

| 阶段 | 后端 | 前端 | 前端 API | 预估 |
|------|------|------|----------|------|
| P0 基础对话 | Provider + Service + API | ChatLayout 改造 | chat.ts 重写 | 中 |
| P1 流式输出 | SSE 端点 | 流式渲染 | EventSource | 小 |
| P2 智能诊断 | DiagnosticChatAgent | 上下文 UI | — | 大 |
| P3 体验增强 | — | UI 组件 | — | 中 |

---

## 未来路线图

### v1.0 — 企业版

| 优先级 | 模块 | 状态 |
|--------|------|------|
| 🔴 P0 | 多租户架构 | ✅ 完成 |
| 🔴 P0 | RBAC 权限 | ✅ 完成 |
| 🔴 P0 | 登录与防爆破 | ✅ 完成 |
| 🔴 P0 | 管理后台 | ✅ 完成 |
| 🔴 P0 | 知识库管理 | ✅ 完成 |
| 🟡 P1 | Bug 案例系统 | ✅ 完成 |
| 🔴 P0 | 核心对话功能（阶段三） | 🚧 进行中 |
| 🟢 P2 | 插件市场 | ⏳ 计划中 |
| 🟢 P2 | 开放 API | ✅ 完成 |

### 阶段三 P0：基础多轮对话 — 🚧 进行中

打通对话闭环，v1.0 所有功能正常可用。

| 任务 | 层 | 说明 |
|------|-----|------|
| `BaseProvider.chat(messages[])` | Provider | 新增多轮对话方法，DeepSeek + OpenAI 兼容 Provider 均实现 |
| `ChatService.send_message()` | Service | 组装历史消息 → 调用 LLM → 存储 AI 回复 |
| `POST /chat-sessions/{id}/chat` | API | 新增聊天端点，接收用户消息返回 AI 回复 |
| `chat.ts` 新增 API 方法 | 前端 API | `createSession()` / `sendMessage()` / `getMessages()` |
| `ChatLayout.sendMessage()` 改造 | 前端 UI | 从 localStorage 改为调用后端 chat API，服务端持久化 |

### 阶段三 P1：流式输出 — ⏳

| 任务 | 说明 |
|------|------|
| Provider stream 模式 | SSE 逐 token 返回 |
| `POST /chat-sessions/{id}/stream` | SSE 端点 |
| 前端流式渲染 | 逐字打字效果 |

### 阶段三 P2：诊断聊天智能化 — ⏳

| 任务 | 说明 |
|------|------|
| `DiagnosticChatAgent` | 多轮诊断对话 Agent |
| Function Calling | LLM 在对话中触发日志分析/知识库搜索工具 |
| 上下文自动注入 | 上传日志后分析结果自动注入对话 |

### v2.0 — 未来规划

- 桌面客户端（Tauri + Rust）
- 移动客户端（Flutter + Dart）
- 插件市场
- 多语言国际化

---

## 一键启动

```bash
cd deploy
docker compose up -d --build
```

启动后浏览器访问 **http://localhost** 即可使用。
