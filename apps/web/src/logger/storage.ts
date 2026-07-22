/**
 * 日志本地持久化存储
 *
 * 基于 IndexedDB 实现：
 * - 失败日志的本地缓存
 * - 网络恢复后的自动重传
 * - 过期日志自动清理
 */

import type { LogEntry } from './types'

// ── 常量 ─────────────────────────────────────────────────────

const DB_NAME = 'ai_diagnostic_logs'
const DB_VERSION = 1
const STORE_NAME = 'failed_logs'

// ── DB 初始化 ───────────────────────────────────────────────

function openDB(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DB_NAME, DB_VERSION)

    request.onupgradeneeded = () => {
      const db = request.result
      if (!db.objectStoreNames.contains(STORE_NAME)) {
        const store = db.createObjectStore(STORE_NAME, { keyPath: 'id' })
        store.createIndex('timestamp', 'timestamp', { unique: false })
      }
    }

    request.onsuccess = () => resolve(request.result)
    request.onerror = () => reject(request.error)
  })
}

// ── 存储操作 ────────────────────────────────────────────────

/** 批量保存失败日志 */
export async function saveFailedLogs(entries: LogEntry[]): Promise<void> {
  try {
    const db = await openDB()
    const tx = db.transaction(STORE_NAME, 'readwrite')
    const store = tx.objectStore(STORE_NAME)
    for (const entry of entries) {
      store.put(entry)
    }
    return new Promise((resolve, reject) => {
      tx.oncomplete = () => resolve()
      tx.onerror = () => reject(tx.error)
    })
  } catch {
    // IndexedDB 不可用时静默失败（如隐私模式）
  }
}

/** 获取所有失败日志（按时间排序） */
export async function getFailedLogs(): Promise<LogEntry[]> {
  try {
    const db = await openDB()
    return new Promise((resolve, reject) => {
      const tx = db.transaction(STORE_NAME, 'readonly')
      const store = tx.objectStore(STORE_NAME)
      const request = store.getAll()
      request.onsuccess = () => {
        const logs = request.result as LogEntry[]
        logs.sort((a, b) => a.timestamp - b.timestamp)
        resolve(logs)
      }
      request.onerror = () => reject(request.error)
    })
  } catch {
    return []
  }
}

/** 删除指定 ID 的日志 */
export async function removeFailedLogs(ids: string[]): Promise<void> {
  try {
    const db = await openDB()
    const tx = db.transaction(STORE_NAME, 'readwrite')
    const store = tx.objectStore(STORE_NAME)
    for (const id of ids) {
      store.delete(id)
    }
    return new Promise((resolve, reject) => {
      tx.oncomplete = () => resolve()
      tx.onerror = () => reject(tx.error)
    })
  } catch {
    // ignore
  }
}

/** 清理超过 maxDays 天的旧日志 */
export async function cleanExpiredLogs(maxDays: number): Promise<void> {
  try {
    const cutoff = Date.now() - maxDays * 24 * 60 * 60 * 1000
    const logs = await getFailedLogs()
    const expired = logs.filter((l) => l.timestamp < cutoff)
    if (expired.length > 0) {
      await removeFailedLogs(expired.map((l) => l.id))
    }
  } catch {
    // ignore
  }
}

/** 获取失败日志总数 */
export async function getFailedLogCount(): Promise<number> {
  try {
    const db = await openDB()
    return new Promise((resolve, reject) => {
      const tx = db.transaction(STORE_NAME, 'readonly')
      const store = tx.objectStore(STORE_NAME)
      const request = store.count()
      request.onsuccess = () => resolve(request.result)
      request.onerror = () => reject(request.error)
    })
  } catch {
    return 0
  }
}
