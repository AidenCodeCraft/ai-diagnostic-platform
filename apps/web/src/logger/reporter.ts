/**
 * 异步批量上报器（Reporter）
 *
 * 职责：
 * 1. 收集日志到内存队列
 * 2. 定时批量上报到后端
 * 3. 上报失败时写 IndexedDB 缓存
 * 4. 网络恢复时自动重传
 */

import { LogEntry, LoggerConfig } from './types'
import { RemoteTransport } from './transport'
import { saveFailedLogs, getFailedLogs, removeFailedLogs, cleanExpiredLogs } from './storage'

export class Reporter {
  private config: LoggerConfig
  private queue: LogEntry[] = []
  private transport: RemoteTransport
  private timer: ReturnType<typeof setInterval> | null = null
  private flushing = false
  private retrying = false

  constructor(config: LoggerConfig) {
    this.config = config
    this.transport = new RemoteTransport(config.endpoint)
  }

  // ── 启动 / 停止 ──────────────────────────────────────────

  /** 启动定时上报 */
  start(): void {
    this.timer = setInterval(() => this.flush(), this.config.flushInterval)

    // 网络恢复时触发重传
    window.addEventListener('online', this.onOnline)

    // 页面即将关闭时，最后一次尝试发送
    window.addEventListener('beforeunload', this.onBeforeUnload)

    // 启动时清理过期日志
    cleanExpiredLogs(this.config.maxRetentionDays)

    // 启动时尝试重传之前失败的日志
    this.retryFailedLogs()
  }

  /** 停止定时上报（通常不需要调用） */
  stop(): void {
    if (this.timer) {
      clearInterval(this.timer)
      this.timer = null
    }
    window.removeEventListener('online', this.onOnline)
    window.removeEventListener('beforeunload', this.onBeforeUnload)
  }

  // ── 入队 ────────────────────────────────────────────────

  /** 将日志加入上报队列 */
  enqueue(entry: LogEntry): void {
    // 超过最大大小则丢弃最旧的
    if (entry.message && new Blob([entry.message]).size > this.config.maxEntrySize) {
      return
    }
    this.queue.push(entry)
    // 超限时丢弃最旧的
    while (this.queue.length > this.config.maxQueueSize) {
      this.queue.shift()
    }
    // 达到批量大小时立即发送
    if (this.queue.length >= this.config.batchSize) {
      this.flush()
    }
  }

  // ── 批量发送 ────────────────────────────────────────────

  private async flush(): Promise<void> {
    if (this.flushing || this.queue.length === 0) return
    this.flushing = true

    const batch = this.queue.splice(0, this.config.batchSize)

    try {
      const success = await this.transport.sendBatch(batch)
      if (!success) {
        // 发送失败，写 IndexedDB
        await saveFailedLogs(batch)
      }
    } catch {
      await saveFailedLogs(batch)
    } finally {
      this.flushing = false
    }
  }

  // ── 重传 ────────────────────────────────────────────────

  private onOnline = (): void => {
    this.retryFailedLogs()
  }

  private onBeforeUnload = (): void => {
    // 使用 sendBeacon 在页面卸载时发送
    if (this.queue.length > 0) {
      const payload = JSON.stringify(this.queue)
      navigator.sendBeacon(this.config.endpoint, payload)
      this.queue = []
    }
  }

  private async retryFailedLogs(): Promise<void> {
    if (this.retrying) return
    this.retrying = true

    try {
      const logs = await getFailedLogs()
      if (logs.length === 0) return

      let successIds: string[] = []

      // 分批重传
      for (let i = 0; i < logs.length; i += this.config.batchSize) {
        const batch = logs.slice(i, i + this.config.batchSize)
        const ok = await this.transport.sendBatch(batch)
        if (ok) {
          successIds.push(...batch.map((l) => l.id))
        }
      }

      if (successIds.length > 0) {
        await removeFailedLogs(successIds)
      }
    } catch {
      // 重传失败，下次再试
    } finally {
      this.retrying = false
    }
  }
}
