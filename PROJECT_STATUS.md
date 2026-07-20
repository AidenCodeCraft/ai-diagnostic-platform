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

## 未来路线图

### v1.0 — 企业版

| 优先级 | 模块 | 说明 |
|--------|------|------|
| 🔴 P0 | 多租户架构 | Organization 模型 + 数据隔离 |
| 🔴 P0 | RBAC 权限 | 管理员/工程师/测试员/只读 |
| 🟡 P1 | Bug 案例系统 | 历史案例检索 + 解决方案关联 |
| 🟡 P1 | Chat 多轮对话增强 | 对话上下文管理 + 历史恢复 |
| 🟢 P2 | 插件市场 | 发布/安装/评分 |
| 🟢 P2 | 开放 API | API Key + Rate Limit + Webhook |

### 桌面 & 移动客户端

- **Commit 012** — 桌面客户端（Tauri + Rust）
- **Commit 013** — 移动客户端（Flutter + Dart）

---

## v1.0 完成后下一步工作分析

### 阶段一：用户端界面完善

主对话界面（ChatLayout + ChatView）、设置弹窗已完成。剩余待搭建的前端页面：

| 页面 | 后端 API | 前端组件 |
|------|----------|----------|
| 知识库管理 | `GET/POST/PUT/DELETE /knowledge` + `/knowledge/search` + `/knowledge/upload` + `/knowledge/categories` | KnowledgeBase.vue（已有基础版） |
| 插件管理 | `GET /plugins` + `/plugins/models` + `/plugins/stats` + `/plugins/toggle` | PluginManager.vue（已有基础版） |
| 诊断报告 | `GET/POST/DELETE /reports` + `/reports/{id}/markdown` | ReportList.vue（已有基础版） |

### 阶段二：管理后台界面（新增）

#### 总体架构

```
ChatLayout（侧栏 — admin 角色显示管理入口）
  ├── /chat              → 对话界面（所有用户）
  ├── /knowledge         → 知识库（所有用户）
  ├── /plugins           → 插件管理（所有用户）
  ├── /reports           → 诊断报告（所有用户）
  └── /admin/*           → 管理后台（仅 admin）
       ├── /admin/overview    → 系统概览
       ├── /admin/users       → 用户与角色管理
       ├── /admin/audit       → 审核与日志监控
       └── /admin/settings    → 系统配置
```

**权限控制**：路由守卫检查 `user.role === 'admin'`，非管理员重定向到对话页。

#### 1. 系统概览（`/admin/overview`）

| 功能 | 数据来源 | 说明 |
|------|----------|------|
| 关键指标卡片 | `GET /plugins/stats` + 各模块 list API | 用户总数、组织数、今日分析量、活跃插件数 |
| 分析趋势图 | `GET /analyses?status=completed` | 近 7/30 天分析量折线图 |
| 存储用量 | `GET /logs` 统计 size 字段 | 日志存储总量 + 文档数 |
| 系统健康状态 | `GET /health` + `GET /plugins/models` | 后端/DB/Redis/LLM Provider 状态指示灯 |

#### 2. 用户与角色管理（`/admin/users`）

| 功能 | 数据交互 | 说明 |
|------|----------|------|
| 用户列表 | `GET /users`（需新增） | 表格：用户名/邮箱/角色/组织/状态 |
| 角色修改 | `PUT /users/{id}`（需新增） | 下拉切换 admin/engineer/viewer |
| 启用/禁用 | `PUT /users/{id}` 修改 is_active | 开关按钮 + 确认弹窗 |
| 组织分配 | `PUT /users/{id}` 修改 organization_id | 下拉选择已注册组织 |
| 组织管理 | `GET/POST /organizations` | 创建组织 + 成员管理 |
| API Key 管理 | `GET/POST/DELETE /api-keys` | 每个用户可生成多个 Key |

#### 3. 审核与日志监控（`/admin/audit`）

| 功能 | 数据来源 | 说明 |
|------|----------|------|
| 分析任务监控 | `GET /analyses?status=failed` | 失败任务列表 + 错误信息 + 重试 |
| 插件状态 | `GET /plugins` + `POST /plugins/toggle/{name}` | 插件启停管理 |
| 规则管理 | `GET/POST/DELETE /rules` | 规则列表 + 新增/删除 |
| Bug 案例审核 | `GET /bug-cases` | 审核 Bug 案例信息完整性 |
| 知识文档审核 | `GET /knowledge?status=all` | 审核新增/修改的知识文档 |

#### 4. 系统配置（`/admin/settings`）

| 功能 | 数据交互 | 说明 |
|------|----------|------|
| LLM 配置 | 环境变量 / 数据库配置表 | Provider 选择 + API Key + Base URL |
| 系统参数 | `GET/PUT /system/config`（需新增） | 最大上传大小、超时、日志保留天数 |
| 数据清理 | `DELETE /logs` + `DELETE /analyses` | 按日期范围批量清理 |
| 关于系统 | 静态信息 | 版本号、构建时间、许可协议 |

#### 需要新增的后端端点

| 端点 | 用途 | 优先级 |
|------|------|--------|
| `GET /users` | 用户列表（含分页+角色筛选） | 🔴 必须 |
| `PUT /users/{id}` | 修改用户角色/状态/组织 | 🔴 必须 |
| `GET /system/config` | 获取系统配置 | 🟡 建议 |
| `PUT /system/config` | 更新系统配置 | 🟡 建议 |
| `GET /admin/stats` | 聚合统计数据 | 🟡 建议 |

#### 工作量估算

| 模块 | 前端页面 | 后端端点 | 预估 |
|------|----------|----------|------|
| 系统概览 | 1 页 | 1 新增 | 小 |
| 用户管理 | 1 页 | 2 新增 | 中 |
| 审核监控 | 1 页（5 标签） | 0 新增 | 小 |
| 系统配置 | 1 页（4 标签） | 2 新增 | 中 |

### 界面开发前置条件

| 条件 | 状态 |
|------|------|
| 后端 API 全部可用 | ✅ 172 测试通过 |
| API 响应格式确定 | ✅ Pydantic Schema 已定义 |
| 前端 API 客户端就绪 | ✅ chat.ts / knowledge.ts / reports.ts |
| 布局框架就绪 | ✅ ChatLayout + 路由系统 |
| Docker 环境可用 | ✅ 一键部署 |

### 开发建议顺序

| 顺序 | 阶段 | 内容 |
|------|------|------|
| 1 | 后端补充 | 新增 `GET/PUT /users`、`GET/PUT /system/config`、`GET /admin/stats` 端点 |
| 2 | 用户端界面 | 知识库管理 → 诊断报告 → 插件管理 |
| 3 | 管理后台 | 系统概览 → 用户管理 → 审核监控 → 系统配置 |
| 4 | 全局状态 | Pinia 用户登录态 + 权限判断 + 组织上下文 |
