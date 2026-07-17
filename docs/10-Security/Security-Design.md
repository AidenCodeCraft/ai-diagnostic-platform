# Security Design Specification

AI Diagnostic Platform

Version: 1.0

---

# 1. 安全设计目标

保障：

- 数据安全
- 模型安全
- 用户安全
- 系统安全
- 插件安全

满足：企业私有化部署要求。

---

# 2. 安全架构总体设计

```
                 User
                  |
             Identity
                  |
             API Gateway
                  |
Authentication  Authorization  Audit  Rate Limit
                  |
         Application Layer
    Log Service  Agent Service  Knowledge Service
                  |
            Data Layer
    Database  Object Storage  Vector Database
```

---

# 3. 安全分层模型

采用：Defense In Depth

- **Layer 1**：Network Security
- **Layer 2**：Identity Security
- **Layer 3**：Application Security
- **Layer 4**：Data Security
- **Layer 5**：AI Security
- **Layer 6**：Operation Security

---

# 4. 身份认证设计

## 4.1 Authentication

支持：

### 基础认证

Username, Password, JWT

### 企业认证

LDAP, Active Directory, OAuth2, SSO

---

## 4.2 密码安全

禁止：明文保存密码。

采用：Argon2id + Salt

示例：

```
password
↓
Argon2
↓
hash
↓
database
```

---

# 5. JWT 设计

Token 结构：

```json
{
    "user_id": "xxx",
    "role": "engineer",
    "expire": 3600
}
```

Token 规则：

- Access Token：短时间，例如 30 分钟
- Refresh Token：长期，例如 7 天

---

# 6. 权限管理 RBAC

采用：Role Based Access Control

模型：

```
User
  |
Role
  |
Permission
  |
Resource
```

---

# 7. 角色设计

默认：

- **Admin**：用户管理、系统配置、插件管理
- **Engineer**：上传日志、执行分析、查看报告
- **Tester**：上传测试日志、查看结果
- **Viewer**：只读

---

# 8. 权限表设计

数据库：users, roles, permissions, user_roles, role_permissions

---

# 9. 多租户安全

企业版必须支持。

模型：

```
Tenant A
  |
Projects
  |
Logs
  |
Knowledge

Tenant B：完全隔离
```

### 数据隔离策略

- 数据库级：字段 `tenant_id`，所有查询必须带 `WHERE tenant_id=xxx`
- 更高级：Schema 隔离，例如 `tenant_a.logs`, `tenant_b.logs`

---

# 10. 日志数据安全

## 10.1 上传安全

上传前检查：文件类型、文件大小、病毒

## 10.2 文件隔离

存储：MinIO bucket: tenant-id

例如：`company-a/logs`, `company-b/logs`

---

# 11. 日志脱敏系统

非常重要。日志进入 AI 前执行 Mask。

例如：

- 原始：`device_mac=88:12:AA:33:44` → 转换：`device_mac=[MASK_MAC]`
- IP：`192.168.1.100` → `[MASK_IP]`
- SN：`SN123456789` → `[MASK_SN]`
- Token：`Bearer xxxx` → `[MASK_TOKEN]`

---

# 12. Sensitive Data Detector

自动检测。规则：Regex + NER 模型 + 规则库

发现 `password=`, `apikey=`, `token=` 自动阻断。

---

# 13. AI 安全设计

这是 AI 系统新增风险。

## 13.1 Prompt Injection 防护

攻击：用户上传日志包含 `Ignore previous instruction.` 输出系统 Prompt

防护：

- 输入过滤：Prompt Scanner
- 上下文隔离：System Prompt > User Data

## 13.2 Tool 调用安全

Agent 不能无限调用工具。

限制：max_steps=20, max_time=300s

## 13.3 文件访问控制

禁止 Agent 读取 `/etc`, `/home` 等。

只能：`/workspace/logs`

---

# 14. AI 幻觉控制

企业场景不能随便猜。

要求：所有结论必须 Evidence Based。

格式：

```
Conclusion: USB PHY failure
Evidence: Line 1023 USB timeout
Confidence: 92%
```

---

# 15. 可信度评分

输出 Confidence。

- 90-100：高可信
- 70-90：较可信
- <70：需要人工确认

---

# 16. Human In The Loop

关键问题必须人工确认。

流程：

```
AI Analysis
↓
Engineer Review
↓
Confirm
↓
Knowledge Update
```

---

# 17. 模型安全

## 模型来源

必须可信，禁止未知模型。

## 模型文件校验

使用 Hash，例如 SHA256

---

# 18. 模型访问控制

限制谁可以调用模型。

例如：普通用户只能小模型，管理员可用大模型。

---

# 19. API 安全

- **HTTPS**：强制
- **Rate Limit**：例如 100 requests/min
- **API Key**：第三方调用必须 API Key

---

# 20. 防攻击设计

- **SQL Injection**：使用 ORM
- **XSS**：前端过滤
- **CSRF**：Token
- **文件攻击**：Sandbox

---

# 21. 插件安全

插件是最大风险。

插件运行：Sandbox

限制：CPU, Memory, Network, File

插件权限声明：

```yaml
permissions:
  filesystem: false
  network: false
  model: true
```

---

# 22. Agent 安全

Agent 必须可控。

限制：

- Tool 白名单：允许 search_tool，禁止 shell_tool
- Action 审批：危险操作人工确认

---

# 23. 审计系统

所有关键行为记录 Audit Log。

例如：用户 A 上传 log.zip，时间 10:20，调用 DeepSeek，生成报告

---

# 24. 审计内容

记录：who, when, what, where, result

---

# 25. 数据加密

- **传输加密**：TLS
- **存储加密**：数据库 AES，对象存储 SSE

---

# 26. Secret 管理

禁止代码中写 `API_KEY="xxx"`

使用：Vault / Kubernetes Secret

---

# 27. 安全扫描

CI 阶段加入：

- **Dependency Scan**：检查第三方漏洞
- **Container Scan**：例如 Trivy
- **Code Scan**：例如 SonarQube

---

# 28. 数据生命周期

日志：上传 → 分析 → 归档 → 删除

策略：例如 90 天自动删除。

---

# 29. 安全事件响应

流程：

```
发现
↓
隔离
↓
分析
↓
修复
↓
复盘
```

---

# 30. 企业安全等级

- **Level 1**：普通开发环境
- **Level 2**：企业内部。增加：权限、审计
- **Level 3**：高安全企业。增加：离线部署、私有模型、物理隔离

---

> Security Design Complete
