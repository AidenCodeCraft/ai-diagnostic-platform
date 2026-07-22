/**
 * Logger 核心类
 *
 * 职责：
 * 1. 接收应用程序的日志调用
 * 2. 根据级别阈值过滤
 * 3. 组装 LogEntry 数据结构
 * 4. 分发到各 Transport（console / remote）
 */

import { LogEntry, LogLevel, LogCategory, LogContext, LoggerConfig, Transport, DEFAULT_CONFIG } from './types'
import { shouldLog, shouldReport } from './levels'
import { sanitize } from './sanitizer'
import { ConsoleTransport, RemoteTransport } from './transport'
import { preserveLogger } from './preserve'

// ── UUID 生成 ───────────────────────────────────────────────

let counter = 0

function uuid(): string {
  counter += 1
  const now = Date.now().toString(36)
  const rand = Math.random().toString(36).substring(2, 10)
  const seq = counter.toString(36).padStart(4, '0')
  return `${now}-${rand}-${seq}`
}

// ── Reporter 接口 ───────────────────────────────────────────

interface Reporter {
  enqueue(entry: LogEntry): void
}

// ── Logger ──────────────────────────────────────────────────

export class Logger {
  readonly config: LoggerConfig
  private transports: Transport[] = []
  private reporter: Reporter | null = null

  constructor(config?: Partial<LoggerConfig>) {
    this.config = { ...DEFAULT_CONFIG, ...config }

    // 初始化 transports
    if (this.config.consoleEnabled) {
      this.transports.push(new ConsoleTransport())
    }

    // 自动保护，防止 GC
    preserveLogger(this)
  }

  // ── 公开 API ─────────────────────────────────────────────

  /** 注册一个 transport */
  addTransport(transport: Transport): void {
    this.transports.push(transport)
  }

  /** 设置 reporter（由外部 reporter 模块注入） */
  setReporter(reporter: Reporter): void {
    this.reporter = reporter
  }

  /** 记录 ERROR 级别日志 */
  error(message: string, category: LogCategory = 'system', context?: LogContext): void {
    this.log(LogLevel.ERROR, category, message, context)
  }

  /** 记录 WARN 级别日志 */
  warn(message: string, category: LogCategory = 'system', context?: LogContext): void {
    this.log(LogLevel.WARN, category, message, context)
  }

  /** 记录 INFO 级别日志 */
  info(message: string, category: LogCategory = 'system', context?: LogContext): void {
    this.log(LogLevel.INFO, category, message, context)
  }

  /** 记录 DEBUG 级别日志 */
  debug(message: string, category: LogCategory = 'system', context?: LogContext): void {
    this.log(LogLevel.DEBUG, category, message, context)
  }

  /** 记录 TRACE 级别日志 */
  trace(message: string, category: LogCategory = 'system', context?: LogContext): void {
    this.log(LogLevel.TRACE, category, message, context)
  }

  // ── 核心方法 ─────────────────────────────────────────────

  private log(level: LogLevel, category: LogCategory, message: string, context?: LogContext): void {
    if (!shouldLog(level, this.config.level)) return

    const entry: LogEntry = {
      id: uuid(),
      timestamp: Date.now(),
      level,
      category,
      message: sanitize(message) as string,
      context: context ? (sanitize(context) as LogContext) : undefined,
      tags: context?.extra ? Object.keys(context.extra) : undefined,
    }

    // 分发到所有 transport
    for (const transport of this.transports) {
      this.safeSend(transport, entry)
    }

    // 入队上报
    if (this.config.remoteEnabled && shouldReport(level) && this.reporter) {
      this.reporter.enqueue(entry)
    }
  }

  private safeSend(transport: Transport, entry: LogEntry): void {
    try {
      transport.send(entry)
    } catch {
      // Transport 自身异常不能再抛，避免日志系统崩溃
    }
  }
}
