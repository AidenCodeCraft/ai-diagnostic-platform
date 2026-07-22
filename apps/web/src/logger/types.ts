/**
 * Logger 模块类型定义
 *
 * 所有日志相关类型的单一来源（Single Source of Truth）。
 */

// ── 日志级别 ────────────────────────────────────────────────

export enum LogLevel {
  OFF = 0,
  ERROR = 1,
  WARN = 2,
  INFO = 3,
  DEBUG = 4,
  TRACE = 5,
}

// ── 日志分类 ────────────────────────────────────────────────

export type LogCategory = 'api' | 'user' | 'system' | 'business'

// ── 日志条目 ────────────────────────────────────────────────

export interface LogContext {
  /** 当前页面 URL */
  url?: string
  /** 脱敏后的用户标识 */
  userId?: string
  /** 用户操作描述 */
  action?: string
  /** 操作耗时（ms） */
  duration?: number
  /** 错误堆栈（仅 ERROR 级别） */
  stack?: string
  /** 业务自定义扩展 */
  extra?: Record<string, unknown>
}

export interface LogEntry {
  /** UUID v4，唯一标识 */
  id: string
  /** UTC 毫秒时间戳 */
  timestamp: number
  /** 日志级别 */
  level: LogLevel
  /** 日志分类 */
  category: LogCategory
  /** 人类可读的描述 */
  message: string
  /** 结构化上下文 */
  context?: LogContext
  /** 标签，便于检索 */
  tags?: string[]
}

// ── Transport 接口 ──────────────────────────────────────────

export interface Transport {
  readonly name: string
  send(entry: LogEntry): void
  sendBatch?(entries: LogEntry[]): Promise<boolean>
}

// ── Logger 配置 ─────────────────────────────────────────────

export interface LoggerConfig {
  /** 最低输出级别，默认开发 DEBUG，生产 WARN */
  level: LogLevel
  /** 是否启用控制台输出 */
  consoleEnabled: boolean
  /** 是否启用远端上报 */
  remoteEnabled: boolean
  /** 批量上报端点 */
  endpoint: string
  /** 上报批量大小 */
  batchSize: number
  /** 上报时间间隔（ms） */
  flushInterval: number
  /** 失败日志最大缓存天数 */
  maxRetentionDays: number
  /** 单条日志最大大小（字节），默认 100KB */
  maxEntrySize: number
  /** 队列最大长度 */
  maxQueueSize: number
}

export const DEFAULT_CONFIG: LoggerConfig = {
  level: import.meta.env.DEV ? LogLevel.DEBUG : LogLevel.WARN,
  consoleEnabled: import.meta.env.DEV,
  remoteEnabled: import.meta.env.PROD,
  endpoint: '/api/v1/logs/batch',
  batchSize: 50,
  flushInterval: 5000,
  maxRetentionDays: 7,
  maxEntrySize: 100 * 1024,
  maxQueueSize: 200,
}
