/**
 * Logger 模块入口
 *
 * 导出面向应用程序的 useLogger composable，
 * 以及 Logger 类和所有类型定义。
 */

import { reactive } from 'vue'
import { Logger } from './Logger'
import type { LoggerConfig } from './types'

export { Logger } from './Logger'
export { LogLevel } from './types'
export type { LogEntry, LogCategory, LogContext, LoggerConfig, Transport } from './types'
export { sanitize, sanitizeText } from './sanitizer'

// ── 全局单例 ───────────────────────────────────────────────

let instance: Logger | null = null

/**
 * 创建或获取全局 Logger 实例
 */
export function createLogger(config?: Partial<LoggerConfig>): Logger {
  if (!instance) {
    instance = new Logger(config)
  }
  return instance
}

/**
 * 获取当前 Logger 实例
 * 如果尚未创建，则使用默认配置创建
 */
export function getLogger(): Logger {
  if (!instance) {
    instance = new Logger()
  }
  return instance
}

/**
 * Vue Composable：在组件中使用 Logger
 */
export function useLogger() {
  // 用 reactive 包裹确保 Vue 组件中也能感知日志状态（未来扩展用）
  const logger = reactive({ instance: getLogger() }) as { instance: Logger }

  return {
    logger: logger.instance,
    error: (msg: string, category?: Parameters<Logger['error']>[1], ctx?: Parameters<Logger['error']>[2]) =>
      logger.instance.error(msg, category, ctx),
    warn: (msg: string, category?: Parameters<Logger['warn']>[1], ctx?: Parameters<Logger['warn']>[2]) =>
      logger.instance.warn(msg, category, ctx),
    info: (msg: string, category?: Parameters<Logger['info']>[1], ctx?: Parameters<Logger['info']>[2]) =>
      logger.instance.info(msg, category, ctx),
    debug: (msg: string, category?: Parameters<Logger['debug']>[1], ctx?: Parameters<Logger['debug']>[2]) =>
      logger.instance.debug(msg, category, ctx),
  }
}
