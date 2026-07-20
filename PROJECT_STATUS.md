# AI Diagnostic Platform
# 项目状态

## 当前版本

v0.1.0 — MVP 完成

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

- 统一 AnalysisTaskService（合并 AnalysisService + AnalysisResultService）
- 任务生命周期管理（pending → running → completed / failed）
- 状态追踪与时间戳记录
- 分页查询与状态过滤
- 结构化分析结果持久化

状态：✅ 完成

### Commit 007 — DeepSeek LLM 集成

- DeepSeek Provider（支持重试与优雅降级）
- Mock Provider（开发阶段默认）
- JSON 响应解析（直接解析 / markdown 代码块 / 兜底提取）
- 置信度区间限制 [0.0, 1.0]
- Prompt 模板系统（独立文件管理，版本化）
- Provider 健康检查
- LLM Provider 配置化（API Key / Base URL / Model）

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
- 关键词搜索 + 相关性评分
- 分类管理（category 枚举）
- 文档类型（manual, faq, bug_report, datasheet）
- 搜索结果摘要提取
- 预留 vector_id 字段（未来 Milvus 向量搜索）

状态：✅ 完成

### Commit 010 — 诊断报告系统

- 从分析结果自动生成诊断报告
- 报告 CRUD + 分页
- Markdown 格式导出
- 报告元数据（标题、格式、时间戳）

状态：✅ 完成

### Commit 011 — 前端 Web 应用

- Vue3 + TypeScript + Vite + Element Plus
- 7 个页面：Dashboard、日志管理、日志详情、分析列表、分析详情、知识库、报告中心
- Axios API 客户端层（对接全部后端接口）
- Vite 开发代理（/api → backend:8000）
- Docker 多阶段构建 + Nginx 生产部署

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
- 插件管理 API

状态：✅ 完成

### Commit 015 — 生产部署

- Docker Compose 四服务编排（PostgreSQL + Redis + Backend + Frontend）
- 一键启动：`docker compose up -d --build`
- 启动后浏览器打开 `http://localhost` 即可使用完整 Web 应用
- 多阶段 Docker 构建
- Nginx 反向代理（SPA 路由 + /api/ 转发到后端）
- 所有服务健康检查
- 环境变量配置模板（.env.example）
- Alembic 启动时自动执行数据库迁移
- 部署文档

状态：✅ 完成

---

## 测试覆盖

**158 个测试 — 全部通过**

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
| 健康检查 & 配置 | 8 |
| 集成测试 | 7 |
| **总计** | **158** |

---

## 系统架构

```
apps/web/         — Vue3 前端应用
backend/          — FastAPI 后端
  app/
    api/          — REST API（11 个模块）
    agents/       — Agent 框架（core / planner / tools）
    models/       — SQLAlchemy 模型（7 张表）
    schemas/      — Pydantic Schema
    services/     — 业务逻辑（14 个服务）
      parser/     — 可插拔解析引擎
      providers/  — LLM Provider（DeepSeek / Mock）
      prompts/    — Prompt 模板
    database/     — 数据库会话管理
  migrations/     — Alembic 迁移（9 个版本）
plugins/          — 插件 SDK + 内置插件
deploy/           — Docker Compose + 部署文档
```

## 一键启动

```bash
cd deploy
docker compose up -d --build
```

启动后浏览器访问 **http://localhost** 即可使用完整的 AI Diagnostic Platform。

---

## 未来路线图

### v0.5 — 平台化增强

| 优先级 | 模块 | 说明 |
|--------|------|------|
| 🔴 P0 | **用户认证系统** | 注册/登录/JWT/角色权限 |
| 🔴 P0 | **项目管理** | 设备项目 CRUD、按项目隔离数据 |
| 🔴 P0 | **Milvus 向量搜索** | 知识库从关键词搜索升级为语义向量搜索 |
| 🔴 P0 | **对话式交互界面** | 参考 DeepSeek 设计，对话区与附件上传融合，保持界面极简 |
| 🔴 P0 | **模型插件化管理** | 基于现有插件系统，LLM Provider 可安装/切换 |
| 🔴 P0 | **左侧边栏重构** | 参考 ChatGPT 布局：Logo+搜索+收缩 / 知识库+插件入口 / 最近对话 |
| 🔴 P0 | **多轮实时对话** | 支持持续追问，默认输出实时分析，按需生成诊断报告 |
| 🟡 P1 | **多格式知识导入** | PDF/Word/Markdown 文档解析 → 自动分块 → Embedding → 入库 |
| 🟡 P1 | **扩展解析器** | Android logcat、UART 串口、WiFi/BT 驱动日志 |
| 🟡 P1 | **规则引擎增强** | YAML 规则库 + 在线编辑 |
| 🟢 P2 | **分析统计仪表盘** | 成功率、错误分布、趋势图表 |
| 🟢 P2 | **LLM 多模型支持** | Qwen/Llama Provider 插件 |

### v1.0 — 企业版

| 优先级 | 模块 | 说明 |
|--------|------|------|
| 🔴 P0 | **多租户架构** | Organization 模型 + 数据隔离 |
| 🔴 P0 | **RBAC 权限** | 管理员/工程师/测试员/只读 |
| 🟡 P1 | **Bug 案例系统** | 历史案例检索 + 解决方案关联 |
| 🟡 P1 | **Chat 对话系统** | AI 助手模式 + 多轮对话 |
| 🟢 P2 | **插件市场** | 发布/安装/评分 |
| 🟢 P2 | **开放 API** | API Key + Rate Limit + Webhook |

### 界面设计方向

**对话式主界面**（参考 DeepSeek + ChatGPT）：
- 输入框融合附件上传，用户可直接拖拽日志文件
- 分析结果以对话气泡形式渐进式呈现
- 模型切换下拉框置于对话区顶部
- 「生成诊断报告」按钮仅在用户主动点击时触发，汇总当前对话上下文生成正式报告

**左侧边栏**（参考 ChatGPT）：
- 顶部：Logo + 全局搜索 + 边栏展开/收缩开关
- 中部：知识库入口 + 插件管理入口
- 下部：最近对话历史列表

### 桌面 & 移动客户端

- **Commit 012** — 桌面客户端（Tauri + Rust）
- **Commit 013** — 移动客户端（Flutter + Dart）
