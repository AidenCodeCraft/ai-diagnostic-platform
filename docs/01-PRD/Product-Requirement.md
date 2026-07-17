# Product Requirement Document

# AI Diagnostic Platform

Version: 1.0

---

# 1. 产品概述

## 1.1 产品名称

AI Diagnostic Platform

中文：AI 智能故障诊断平台

---

## 1.2 产品定位

AI Diagnostic Platform 是一个面向软件研发、嵌入式开发、测试验证、技术支持团队的智能故障分析平台。

通过：

- 大语言模型（LLM）
- RAG 知识库
- 日志解析技术
- 规则引擎
- AI Agent

帮助工程师快速定位软件、硬件以及系统问题。

---

## 1.3 产品愿景

### Vision

成为：

> 企业研发团队中的 AI 工程师。

帮助工程师从"查看几万行日志"变成"几分钟获得故障定位结果"。

---

# 2. 用户分析

## 2.1 目标用户

### 用户 A：嵌入式软件工程师

工作内容：

- 驱动开发
- Linux 开发
- MCU 开发
- Android HAL 开发

痛点：

- 日志量巨大
- 问题定位困难
- 依赖专家经验

需求：自动分析：

- Crash
- Exception
- Kernel Panic
- Driver Error

---

### 用户 B：测试工程师

工作内容：

- 功能测试
- 自动化测试
- 回归测试

痛点：每天产生大量：

- 测试日志
- Fail Case
- Error Log

需求：自动：

- 分类问题
- 定位原因
- 输出 Bug 报告

---

### 用户 C：FAE/售后工程师

工作：客户问题支持。

痛点：客户描述"设备打不开"但是不知道原因。

需求：

上传：

- 用户日志
- 设备信息

AI 输出：可能原因。

---

### 用户 D：研发管理者

关注：

- Bug 趋势
- 产品质量
- 模块稳定性

需求：Dashboard。

---

# 3. 核心使用场景

---

## 场景 1：设备启动失败

用户输入：设备启动失败，偶尔卡死。

上传：boot.log

AI 输出：

```
问题：DDR初始化失败

依据：DDR training timeout

概率：92%

建议：检查DDR配置、时钟、电源

历史案例：BUG-1024
```

---

## 场景 2：蓝牙无法连接

输入：蓝牙搜索不到设备

日志：

```
HCI timeout

BT init fail

UART error
```

AI：

```
根因：Bluetooth firmware加载失败

建议：

检查：
1. UART
2. FW版本
3. GPIO
```

---

## 场景 3：自动生成 Bug

输入：测试失败。

AI 生成：

```
Title: USB enumeration failed

Description: 设备无法识别USB设备

Root Cause: USB PHY timeout

Log: xxx

建议: xxx
```

---

# 4. 产品功能架构

AI Diagnostic Platform

```
├── 用户中心
├── 项目管理
├── 日志管理
├── AI分析
├── 知识库
├── Rule管理
├── Agent管理
├── 报告中心
├── 数据统计
```

---

# 5. 功能需求

## 5.1 用户系统

### 功能

#### 用户注册

支持：

- Email
- 手机
- 企业账号

---

#### 登录

支持：

- 用户密码
- OAuth

---

#### 权限

RBAC：

角色：

- Admin
- Engineer
- Tester
- Viewer

权限：

- 查看日志
- 上传日志
- 管理知识库
- 管理规则

---

## 5.2 项目管理

目的：隔离不同产品。

例如：

项目：智能座舱

模块：

- USB
- Bluetooth
- Camera
- GNSS

功能：

- 创建项目
- 删除项目
- 成员管理
- 标签管理

---

## 5.3 日志管理

### 上传

支持：

- .log
- .txt
- .zip
- .tar.gz

限制：单文件 1GB

---

### 日志信息

保存：

- 文件名
- 大小
- 上传者
- 时间
- 设备型号
- 版本号
- 项目

---

### 日志预览

支持：

- 搜索
- 高亮
- 分页
- ERROR 过滤

---

## 5.4 AI 分析

核心功能。

输入：

- 用户描述
- 日志
- 设备信息
- 版本信息

输出：

### 问题总结

例如：USB 设备枚举失败

---

### 错误定位

例如：USB Driver

---

### 根因分析

例如：USB PHY 初始化失败

---

### 证据链

显示：

- Line 10234: USB timeout
- Line 10240: reset failed

---

### 解决建议

例如：

检查：

1. USB 供电
2. PHY 配置
3. Driver 版本

---

## 5.5 知识库

功能：

上传：

- PDF
- Word
- Markdown
- Excel
- 网页

自动：

- 解析
- 切片
- Embedding
- 索引

---

知识类型：

### 技术文档

例如：芯片 Datasheet

---

### Bug 库

例如：BUG-001

原因：解决方案：

---

### FAQ

例如：USB timeout 怎么办？

---

## 5.6 Rule 管理

工程师可以创建规则。

例如：

规则：

```
name: USB_TIMEOUT

match: USB timeout

action: check USB PHY
```

功能：

- 新增 Rule
- 编辑 Rule
- 测试 Rule
- 发布 Rule
- 版本管理

---

## 5.7 AI Agent

功能：自动执行分析流程。

例如：Agent 流程：

```
读取日志
↓
寻找异常
↓
调用Rule
↓
搜索知识库
↓
调用LLM
↓
生成报告
```

---

## 5.8 报告系统

生成：

- Markdown
- PDF
- Word

内容：

- 问题描述
- 环境信息
- 日志摘要
- 异常时间线
- Root Cause
- Evidence
- Solution
- History Case

---

# 6. MVP 版本范围

## V1.0

必须实现：

| 功能 | 优先级 |
|------|--------|
| 用户登录 | P0 |
| 日志上传 | P0 |
| 日志解析 | P0 |
| DeepSeek 分析 | P0 |
| 报告生成 | P0 |
| 历史记录 | P1 |
| 知识库 | P1 |
| 规则系统 | P1 |

---

# 7. V2 版本

增加：

| 功能 |
|------|
| RAG 知识库 |
| Bug 关联 |
| Agent |
| Dashboard |
| 团队管理 |

---

# 8. V3 企业版

增加：

- 多租户
- 权限系统
- 私有化部署
- Kubernetes
- 企业 SSO
- API 开放平台

---

# 9. 非功能需求

## 性能

目标：

- 单日志：< 30 秒分析
- 支持：1000 用户

---

## 安全

要求：

- 数据隔离
- 权限控制
- 日志脱敏
- 文件安全扫描

---

## 可维护性

要求：

- 模块化
- 插件化
- API First
- 自动测试

---

## 可扩展性

支持新增：

- 模型
- Parser
- Agent
- Rule
- Knowledge Provider

无需修改核心代码。

---

# 10. 商业化方向

## 企业私有部署

客户：大型研发企业。

收费：License。

---

## SaaS 版本

按：用户数、存储量、AI 调用次数收费。

---

## 行业版本

例如：

汽车行业版

- CAN
- AUTOSAR
- Linux
- ADAS

IoT 版本

- MQTT
- BLE
- WiFi

---

# 11. 产品长期目标

最终成为：

AI 研发助手平台 = 日志分析、代码分析、测试分析、知识管理、自动修复建议、PRD 完成
