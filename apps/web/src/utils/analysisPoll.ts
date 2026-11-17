/**
 * 分析任务轮询器 —— 上传日志后的异步分析状态跟踪。
 *
 * 与后端约定：
 *  - GET /analyses/{id} 返回 { status, summary, error_message, ... }
 *  - 分析期间 summary 携带 "[进度] <阶段文案>"（后端流水线实时上报），
 *    前端用它驱动思维链展示 Agent 各阶段的真实进度；
 *  - status: pending | running | completed | failed
 */

export interface AnalysisPollApi {
  getAnalysis(id: number): Promise<{ data: any }>
  getAnalysisResult(id: number): Promise<{ data: any }>
}

export interface AnalysisPollOptions {
  /** 每次发现新阶段时回调（用于思维链展示） */
  onProgress?: (text: string) => void
  /** 轮询总超时（默认 540 秒，须大于后端看门狗 480 秒） */
  timeoutMs?: number
  /** 轮询间隔（默认 1 秒） */
  pollIntervalMs?: number
}

export const PROGRESS_PREFIX = '[进度] '

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

/**
 * 轮询分析任务直到完成/失败/超时。
 * completed → 返回 /result 的完整结果；failed/超时 → 抛出带原因的 Error。
 */
export async function pollAnalysis(
  api: AnalysisPollApi,
  analysisId: number,
  options: AnalysisPollOptions = {},
): Promise<any> {
  const { onProgress, timeoutMs = 540_000, pollIntervalMs = 1000 } = options
  const startedAt = Date.now()
  const deadline = startedAt + timeoutMs
  let lastPhase = ''

  while (Date.now() < deadline) {
    const res = await api.getAnalysis(analysisId)
    const data = res.data || {}

    if (data.status === 'completed') {
      return (await api.getAnalysisResult(analysisId)).data
    }
    if (data.status === 'failed') {
      throw new Error(data.error_message || '分析失败')
    }

    // 优先使用后端上报的真实流水线进度（"[进度] …"），无进度时按耗时兜底
    const summary: string = typeof data.summary === 'string' ? data.summary : ''
    const elapsed = Date.now() - startedAt
    const phase = summary.startsWith(PROGRESS_PREFIX)
      ? summary.slice(PROGRESS_PREFIX.length)
      : elapsed < 15000
        ? '正在解析日志并提取关键错误片段…'
        : elapsed < 60000
          ? '规则引擎匹配 + 知识库检索中…'
          : 'AI 正在生成诊断结论…'

    if (phase && phase !== lastPhase) {
      lastPhase = phase
      onProgress?.(phase)
    }

    await sleep(pollIntervalMs)
  }

  const waited = Math.round((Date.now() - startedAt) / 1000)
  throw new Error(
    `分析超时（已等待 ${waited} 秒）。任务可能仍在后台执行，可稍后在「日志分析」中查看结果；` +
    '若日志过大，建议裁剪到关键片段后重试',
  )
}
