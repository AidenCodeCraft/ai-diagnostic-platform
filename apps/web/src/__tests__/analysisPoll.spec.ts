import { describe, expect, it, vi } from 'vitest'

import { pollAnalysis, PROGRESS_PREFIX } from '@/utils/analysisPoll'

function makeApi(statuses: Array<{ status: string; summary?: string; error_message?: string }>, result: any = { ok: true }) {
  const getAnalysis = vi.fn(async () => ({ data: statuses.shift() ?? { status: 'running' } }))
  const getAnalysisResult = vi.fn(async () => ({ data: result }))
  return { getAnalysis, getAnalysisResult }
}

describe('pollAnalysis', () => {
  it('returns the analysis result once completed', async () => {
    const api = makeApi([{ status: 'running' }, { status: 'completed' }], { diagnosis_markdown: '## 诊断结果' })
    const out = await pollAnalysis(api as any, 1, { pollIntervalMs: 1 })
    expect(out.diagnosis_markdown).toBe('## 诊断结果')
    expect(api.getAnalysisResult).toHaveBeenCalledWith(1)
  })

  it('reports backend "[进度]" stage text to the thinking chain', async () => {
    const api = makeApi([
      { status: 'running', summary: `${PROGRESS_PREFIX}④ 知识库检索相关案例…` },
      { status: 'completed', summary: 'done' },
    ])
    const phases: string[] = []
    await pollAnalysis(api as any, 1, { pollIntervalMs: 1, onProgress: (t) => phases.push(t) })
    expect(phases).toContain('④ 知识库检索相关案例…')
    // [进度] 前缀被剥离，不会原样进入思维链
    expect(phases.every((p) => !p.startsWith(PROGRESS_PREFIX))).toBe(true)
  })

  it('falls back to elapsed-based phases when the backend sends no progress', async () => {
    const api = makeApi([{ status: 'running', summary: '' }, { status: 'completed' }])
    const phases: string[] = []
    await pollAnalysis(api as any, 1, { pollIntervalMs: 1, onProgress: (t) => phases.push(t) })
    expect(phases[0]).toContain('解析日志')
  })

  it('throws the backend error message when the analysis fails', async () => {
    const api = makeApi([{ status: 'failed', error_message: '日志文件不存在' }])
    await expect(pollAnalysis(api as any, 1, { pollIntervalMs: 1 })).rejects.toThrow('日志文件不存在')
  })

  it('throws an actionable message on timeout', async () => {
    const api = makeApi([{ status: 'running' }])
    await expect(pollAnalysis(api as any, 1, { pollIntervalMs: 1, timeoutMs: 0 })).rejects.toThrow(/分析超时/)
  })
})
