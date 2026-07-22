/**
 * 关键对象保留保护
 *
 * 将 Logger 实例、上报队列等关键对象挂载到 window，
 * 防止被 tree-shaking、GC 或第三方代码意外清除。
 */

import type { Logger } from './Logger'

const PRESERVE_KEY = '__AI_DIAGNOSTIC_LOGGER__'

interface Preserved {
  logger: Logger | null
}

function getStore(): Preserved {
  const win = window as unknown as Record<string, unknown>
  if (!win[PRESERVE_KEY]) {
    win[PRESERVE_KEY] = { logger: null } as Preserved
  }
  return win[PRESERVE_KEY] as Preserved
}

/** 注册 Logger 实例，防止被 GC 清除 */
export function preserveLogger(logger: Logger): void {
  getStore().logger = logger
}

/** 获取已注册的 Logger 实例 */
export function getLogger(): Logger | null {
  return getStore().logger
}
