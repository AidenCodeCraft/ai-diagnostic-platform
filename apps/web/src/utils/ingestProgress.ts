/** 单条日志的异步预处理进度轮询 */

export interface IngestStageStat {
  total: number
  succeeded: number
  failed: number
  running: number
}

export interface IngestStatus {
  log_id: number
  stages: Record<string, IngestStageStat>
  tasks: number
  all_succeeded: boolean
  failed_tasks: string[]
}

export interface IngestProgress {
  /** 已成功阶段数 / 总阶段数 */
  done: number
  total: number
  /** 当前正在跑或最后完成的阶段名 */
  stage: string
  failed: boolean
}

/** 阶段中文名（后端 stage 名固定为这几步） */
export const STAGE_LABELS: Record<string, string> = {
  prepare: '准备',
  parse: '解析',
  template: '模板提取',
  compress: '压缩',
  finalize: '收尾',
}

export function stageLabel(stage: string): string {
  return STAGE_LABELS[stage] || stage
}

/** 把后端 summary 折算成一行进度：优先展示失败，其次展示运行中阶段 */
export function toProgress(status: IngestStatus): IngestProgress {
  const entries = Object.entries(status.stages || {})
  const total = entries.length
  const done = entries.filter(([, stat]) => stat.succeeded > 0 && stat.failed === 0 && stat.running === 0).length
  const failed = entries.some(([, stat]) => stat.failed > 0) || status.failed_tasks.length > 0
  const running = entries.find(([, stat]) => stat.running > 0)
  const lastFinished = entries
    .filter(([, stat]) => stat.succeeded > 0)
    .map(([name]) => name)
    .pop()
  return {
    done,
    total,
    stage: running ? running[0] : lastFinished || entries[0]?.[0] || '',
    failed,
  }
}

export interface WatchOptions {
  intervalMs?: number
  timeoutMs?: number
}

/**
 * 轮询预处理进度，直到全部阶段成功、出现失败或超时。
 *
 * 不阻塞上传后的主流程：调用方拿到 stop() 自行决定何时停（分析结束时停掉即可）。
 */
export function watchIngestProgress(
  logId: number,
  fetchStatus: (logId: number) => Promise<IngestStatus>,
  onUpdate: (progress: IngestProgress) => void,
  options: WatchOptions = {},
): () => void {
  const intervalMs = options.intervalMs ?? 1500
  const timeoutMs = options.timeoutMs ?? 300_000
  const deadline = Date.now() + timeoutMs
  let timer: ReturnType<typeof setTimeout> | null = null
  let stopped = false

  const stop = () => {
    stopped = true
    if (timer) {
      clearTimeout(timer)
      timer = null
    }
  }

  const tick = async () => {
    if (stopped) return
    try {
      const status = await fetchStatus(logId)
      if (stopped) return
      const progress = toProgress(status)
      onUpdate(progress)
      if (status.all_succeeded || progress.failed) {
        stop()
        return
      }
    } catch {
      // 单次轮询失败不终止：预处理链可能刚投递，任务行尚未写入
    }
    if (Date.now() >= deadline) {
      stop()
      return
    }
    timer = setTimeout(tick, intervalMs)
  }

  timer = setTimeout(tick, intervalMs)
  return stop
}
