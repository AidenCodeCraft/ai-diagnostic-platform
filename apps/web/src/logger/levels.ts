/**
 * 日志级别定义与过滤逻辑
 */

import { LogLevel } from './types'

// ── 级别名称映射 ────────────────────────────────────────────

export const LEVEL_LABELS: Record<LogLevel, string> = {
  [LogLevel.OFF]: 'OFF',
  [LogLevel.ERROR]: 'ERROR',
  [LogLevel.WARN]: 'WARN',
  [LogLevel.INFO]: 'INFO',
  [LogLevel.DEBUG]: 'DEBUG',
  [LogLevel.TRACE]: 'TRACE',
}

/** 根据运行时环境返回默认级别 */
export function getDefaultLevel(): LogLevel {
  return import.meta.env.DEV ? LogLevel.DEBUG : LogLevel.WARN
}

/** 判断一条日志是否应该输出 */
export function shouldLog(level: LogLevel, threshold: LogLevel): boolean {
  if (threshold === LogLevel.OFF) return false
  return level <= threshold
}

/** 判断一条日志是否应该上报到后端 */
export function shouldReport(level: LogLevel): boolean {
  // 仅 ERROR / WARN 级别上报，防止 INFO/DEBUG 海量数据压垮服务
  return level === LogLevel.ERROR || level === LogLevel.WARN
}
