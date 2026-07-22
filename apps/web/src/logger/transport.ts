/**
 * Transport 传输层实现
 *
 * Transport 模式允许灵活扩展日志输出目标：
 * - ConsoleTransport ：开发环境控制台输出
 * - RemoteTransport ：生产环境批量上报
 */

import { LogEntry, Transport } from './types'
import { toConsole, toJSON } from './formatter'
import { shouldReport } from './levels'
import { sanitize } from './sanitizer'

// ── Console Transport ─────────────────────────────────────────

export class ConsoleTransport implements Transport {
  readonly name = 'console'

  send(entry: LogEntry): void {
    // 脱敏后再输出到控制台
    const sanitized = {
      ...entry,
      message: sanitize(entry.message) as string,
      context: entry.context ? sanitize(entry.context) : undefined,
    } as LogEntry

    const [message, style] = toConsole(sanitized)
    const [labelStyle, resetStyle] = style.split('|')

    switch (entry.level) {
      case 0: // OFF — never reached
        break
      case 1: // ERROR
        console.error(message, labelStyle, resetStyle)
        break
      case 2: // WARN
        console.warn(message, labelStyle, resetStyle)
        break
      case 3: // INFO
        console.info(message, labelStyle, resetStyle)
        break
      case 4:
      case 5: // DEBUG / TRACE
        console.debug(message, labelStyle, resetStyle)
        break
    }
  }
}

// ── Remote Transport ──────────────────────────────────────────

export class RemoteTransport implements Transport {
  readonly name = 'remote'
  private endpoint: string

  constructor(endpoint: string) {
    this.endpoint = endpoint
  }

  send(entry: LogEntry): void {
    // Remote transport 不支持单条发送，必须通过 sendBatch
    if (import.meta.env.DEV) {
      console.warn('[Logger] RemoteTransport.send() called directly, use sendBatch() instead')
    }
  }

  async sendBatch(entries: LogEntry[]): Promise<boolean> {
    // 仅上报 WARN/ERROR
    const reportable = entries.filter((e) => shouldReport(e.level))
    if (reportable.length === 0) return true

    const payload = reportable.map((entry) => ({
      id: entry.id,
      timestamp: entry.timestamp,
      level: entry.level,
      category: entry.category,
      message: sanitize(entry.message) as string,
      context: entry.context ? sanitize(entry.context) : undefined,
      tags: entry.tags,
    }))

    const body = JSON.stringify(payload)

    try {
      const token = sessionStorage.getItem('token')
      const headers: Record<string, string> = { 'Content-Type': 'application/json' }
      if (token) {
        headers['Authorization'] = `Bearer ${token}`
      }

      const resp = await fetch(this.endpoint, {
        method: 'POST',
        headers,
        body,
        // 使用 keepalive 确保页面关闭时也能发送
        keepalive: true,
      })

      return resp.ok
    } catch {
      return false
    }
  }
}
