/** @fileoverview 前端性能优化：请求批处理 + 虚拟滚动 + 懒加载 */

import { ref, type Ref } from 'vue'

// ═══════════════════════════════════════════════════════
// 请求批处理器 (Request Batching)
// ═══════════════════════════════════════════════════════

interface BatchedRequest<T> {
  id: string
  resolver: (value: T) => void
  rejecter: (error: Error) => void
}

interface BatchConfig {
  maxBatchSize: number
  maxWaitMs: number
}

export class RequestBatcher<TParams, TResult> {
  private pending: BatchedRequest<TResult>[] = []
  private pendingParams: TParams[] = []
  private timer: ReturnType<typeof setTimeout> | null = null
  private config: BatchConfig
  private executor: (params: TParams[]) => Promise<TResult[]>

  constructor(
    executor: (params: TParams[]) => Promise<TResult[]>,
    config: Partial<BatchConfig> = {},
  ) {
    this.executor = executor
    this.config = {
      maxBatchSize: config.maxBatchSize ?? 10,
      maxWaitMs: config.maxWaitMs ?? 50,
    }
  }

  fetch(param: TParams): Promise<TResult> {
    return new Promise((resolve, reject) => {
      const id = crypto.randomUUID()
      this.pending.push({ id, resolver: resolve, rejecter: reject })
      this.pendingParams.push(param)

      if (this.pending.length >= this.config.maxBatchSize) {
        this.flush()
      } else if (!this.timer) {
        this.timer = setTimeout(() => this.flush(), this.config.maxWaitMs)
      }
    })
  }

  private async flush() {
    if (this.timer) {
      clearTimeout(this.timer)
      this.timer = null
    }

    if (this.pending.length === 0) return

    const batch = [...this.pending]
    const params = [...this.pendingParams]
    this.pending = []
    this.pendingParams = []

    try {
      const results = await this.executor(params)
      batch.forEach((req, i) => {
        if (i < results.length) {
          req.resolver(results[i])
        } else {
          req.rejecter(new Error(`Result index ${i} out of range`))
        }
      })
    } catch (error) {
      batch.forEach(req => req.rejecter(error as Error))
    }
  }

  destroy() {
    if (this.timer) {
      clearTimeout(this.timer)
    }
    this.pending.forEach(req => req.rejecter(new Error('Batcher destroyed')))
  }
}

// ═══════════════════════════════════════════════════════
// 防抖 (Debounce)
// ═══════════════════════════════════════════════════════

export function debounce<T extends (...args: unknown[]) => unknown>(
  fn: T,
  delayMs: number,
): (...args: Parameters<T>) => void {
  let timer: ReturnType<typeof setTimeout> | null = null
  return (...args: Parameters<T>) => {
    if (timer) clearTimeout(timer)
    timer = setTimeout(() => {
      fn(...args)
      timer = null
    }, delayMs)
  }
}

// ═══════════════════════════════════════════════════════
// 节流 (Throttle)
// ═══════════════════════════════════════════════════════

export function throttle<T extends (...args: unknown[]) => unknown>(
  fn: T,
  limitMs: number,
): (...args: Parameters<T>) => void {
  let lastCall = 0
  let pendingArgs: Parameters<T> | null = null
  let pendingTimer: ReturnType<typeof setTimeout> | null = null

  return (...args: Parameters<T>) => {
    const now = Date.now()
    if (now - lastCall >= limitMs) {
      lastCall = now
      fn(...args)
    } else {
      pendingArgs = args
      if (!pendingTimer) {
        pendingTimer = setTimeout(() => {
          pendingTimer = null
          if (pendingArgs) {
            lastCall = Date.now()
            fn(...pendingArgs)
            pendingArgs = null
          }
        }, limitMs - (now - lastCall))
      }
    }
  }
}

// ═══════════════════════════════════════════════════════
// 虚拟滚动工具 (Virtual Scroll Helper)
// ═══════════════════════════════════════════════════════

export interface VirtualScrollConfig {
  itemHeight: number
  overscan: number
  totalItems: Ref<number>
  containerHeight: number
}

export interface VirtualScrollState {
  startIndex: Ref<number>
  endIndex: Ref<number>
  offsetY: Ref<number>
  totalHeight: Ref<number>
  onScroll: (scrollTop: number) => void
}

export function useVirtualScroll(config: VirtualScrollConfig): VirtualScrollState {
  const startIndex = ref(0)
  const endIndex = ref(0)
  const offsetY = ref(0)

  const totalHeight = ref(0)
  const visibleCount = Math.ceil(config.containerHeight / config.itemHeight)

  function updateRange(scrollTop: number) {
    const rawStart = Math.floor(scrollTop / config.itemHeight)
    startIndex.value = Math.max(0, rawStart - config.overscan)
    endIndex.value = Math.min(
      config.totalItems.value,
      rawStart + visibleCount + config.overscan,
    )
    offsetY.value = startIndex.value * config.itemHeight
    totalHeight.value = config.totalItems.value * config.itemHeight
  }

  // 初始计算
  updateRange(0)

  return { startIndex, endIndex, offsetY, totalHeight, onScroll: updateRange }
}

// ═══════════════════════════════════════════════════════
// 懒加载 (Lazy Load)
// ═══════════════════════════════════════════════════════

export function useLazyLoad(
  cb: () => void,
  options: IntersectionObserverInit = { rootMargin: '200px' },
) {
  const targetRef = ref<HTMLElement | null>(null)
  let observer: IntersectionObserver | null = null

  function setup() {
    observer = new IntersectionObserver((entries) => {
      if (entries[0]?.isIntersecting) {
        cb()
        if (observer && targetRef.value) {
          observer.unobserve(targetRef.value)
        }
      }
    }, options)

    if (targetRef.value) {
      observer.observe(targetRef.value)
    }
  }

  function cleanup() {
    if (observer && targetRef.value) {
      observer.unobserve(targetRef.value)
    }
    observer = null
  }

  return { targetRef, setup, cleanup }
}

// ═══════════════════════════════════════════════════════
// 内存缓存 (Memo Cache)
// ═══════════════════════════════════════════════════════

export class MemoCache<T> {
  private cache = new Map<string, { value: T; timestamp: number }>()
  private ttlMs: number

  constructor(ttlMs: number = 300000) {
    this.ttlMs = ttlMs
  }

  get(key: string): T | undefined {
    const entry = this.cache.get(key)
    if (!entry) return undefined
    if (Date.now() - entry.timestamp > this.ttlMs) {
      this.cache.delete(key)
      return undefined
    }
    return entry.value
  }

  set(key: string, value: T): void {
    this.cache.set(key, { value, timestamp: Date.now() })
  }

  getOrSet(key: string, factory: () => T): T {
    const existing = this.get(key)
    if (existing !== undefined) return existing
    const value = factory()
    this.set(key, value)
    return value
  }

  clear(): void {
    this.cache.clear()
  }

  get size(): number {
    this.evictExpired()
    return this.cache.size
  }

  private evictExpired(): void {
    const now = Date.now()
    for (const [key, entry] of this.cache) {
      if (now - entry.timestamp > this.ttlMs) {
        this.cache.delete(key)
      }
    }
  }
}

// ═══════════════════════════════════════════════════════
// AbortController 管理器 (防止内存泄漏)
// ═══════════════════════════════════════════════════════

export class AbortManager {
  private controllers = new Map<string, AbortController>()

  create(key: string): AbortController {
    // 先取消旧的
    this.abort(key)
    const controller = new AbortController()
    this.controllers.set(key, controller)
    return controller
  }

  abort(key: string): void {
    const existing = this.controllers.get(key)
    if (existing) {
      existing.abort()
      this.controllers.delete(key)
    }
  }

  abortAll(): void {
    this.controllers.forEach(c => c.abort())
    this.controllers.clear()
  }
}
