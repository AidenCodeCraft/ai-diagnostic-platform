/**
 * Logger Vue Plugin
 *
 * 全局注册：
 * - app.config.errorHandler：捕获未处理的 Vue 异常
 * - app.config.warnHandler：捕获 Vue 内部警告
 * - window.onerror：捕获 JS 运行时异常
 * - window.unhandledrejection：捕获未处理的 Promise 拒绝
 * - 将 Logger 实例注入全局属性 $logger
 */

import type { App } from 'vue'
import type { Logger } from '@/logger/Logger'
import { getLogger } from '@/logger'

// ── 全局错误处理 ─────────────────────────────────────────────

function setupGlobalErrorHandlers(logger: Logger): void {
  // Vue 组件渲染/生命周期异常
  // （在插件 install 中通过 app.config.errorHandler 注册）

  // JS 运行时未捕获异常
  window.addEventListener('error', (event: ErrorEvent) => {
    logger.error(`Uncaught Error: ${event.message}`, 'system', {
      stack: event.error?.stack || event.filename ? `${event.filename}:${event.lineno}:${event.colno}` : undefined,
      url: window.location.href,
    })
  })

  // Promise 未捕获拒绝
  window.addEventListener('unhandledrejection', (event: PromiseRejectionEvent) => {
    const reason = event.reason
    const message = reason instanceof Error ? reason.message : String(reason)
    logger.error(`Unhandled Promise Rejection: ${message}`, 'system', {
      stack: reason instanceof Error ? reason.stack : undefined,
      url: window.location.href,
    })
  })
}

// ── Vue Plugin ───────────────────────────────────────────────

export const LoggerPlugin = {
  install(app: App): void {
    const logger = getLogger()

    // 注入全局属性
    app.config.globalProperties.$logger = logger

    // Vue 组件级错误处理
    app.config.errorHandler = (err: unknown, _instance, info: string) => {
      const message = err instanceof Error ? err.message : String(err)
      logger.error(`[Vue] ${message}`, 'system', {
        stack: err instanceof Error ? err.stack : undefined,
        extra: { componentInfo: info },
      })

      // 仍然抛出，让浏览器控制台也能看到
      console.error('[Vue Error]', err)
    }

    // Vue 内部警告处理
    app.config.warnHandler = (msg: string, _instance, _trace: string) => {
      logger.warn(`[Vue Warn] ${msg}`, 'system', {
        url: window.location.href,
      })
    }

    // 全局 JS 错误
    setupGlobalErrorHandlers(logger)
  },
}
