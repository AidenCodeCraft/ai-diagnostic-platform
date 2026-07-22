/**
 * 日志结构化格式化器
 *
 * 将 LogEntry 转换为统一格式：
 * - Console 输出：带颜色的可读文本
 * - 远端上报：压缩 JSON 字符串
 */

import { LogEntry, LogLevel } from './types'
import { LEVEL_LABELS } from './levels'

// ── Console 颜色 ─────────────────────────────────────────────

const COLORS: Record<LogLevel, string> = {
  [LogLevel.ERROR]: '#ef4444', // red
  [LogLevel.WARN]: '#f59e0b',  // amber
  [LogLevel.INFO]: '#3b82f6',  // blue
  [LogLevel.DEBUG]: '#8b5cf6', // purple
  [LogLevel.TRACE]: '#6b7280', // gray
  [LogLevel.OFF]: '#000',
}

// ── JSON 上报格式 ───────────────────────────────────────────

/**
 * 将 LogEntry 序列化为上报用的 JSON 字符串
 * - 使用 compact JSON（无空格）以减小体积
 */
export function toJSON(entry: LogEntry): string {
  return JSON.stringify({
    id: entry.id,
    ts: entry.timestamp,
    lv: entry.level,
    cat: entry.category,
    msg: entry.message,
    ctx: entry.context,
    tags: entry.tags,
  })
}

// ── Console 格式化 ──────────────────────────────────────────

/**
 * 将 LogEntry 转为开发者友好的 console 输出
 * 开发环境使用，生产环境不输出。
 */
export function toConsole(entry: LogEntry): [string, string] {
  const label = LEVEL_LABELS[entry.level]
  const color = COLORS[entry.level] || '#000'

  const parts: string[] = [
    `%c[${label}]%c`,
    new Date(entry.timestamp).toISOString(),
  ]

  if (entry.category) {
    parts.push(`[${entry.category}]`)
  }
  parts.push(entry.message)

  if (entry.context?.url) {
    parts.push(`\n  url: ${entry.context.url}`)
  }
  if (entry.context?.duration != null) {
    parts.push(`\n  duration: ${entry.context.duration}ms`)
  }
  if (entry.context?.stack) {
    parts.push(`\n  stack: ${entry.context.stack}`)
  }
  if (entry.context?.extra && Object.keys(entry.context.extra).length > 0) {
    parts.push(`\n  extra: ${JSON.stringify(entry.context.extra)}`)
  }

  const style = `color: ${color}; font-weight: bold`
  const reset = 'color: inherit; font-weight: normal'

  return [parts.join(' '), `${style}|${reset}`]
}
