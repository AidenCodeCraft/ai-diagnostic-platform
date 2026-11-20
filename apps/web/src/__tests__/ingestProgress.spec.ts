import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest'

import {
  stageLabel,
  toProgress,
  watchIngestProgress,
  type IngestStatus,
} from '@/utils/ingestProgress'

function status(partial: Partial<IngestStatus>): IngestStatus {
  return {
    log_id: 7,
    stages: {},
    tasks: 0,
    all_succeeded: false,
    failed_tasks: [],
    ...partial,
  }
}

describe('ingestProgress', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })
  afterEach(() => {
    vi.useRealTimers()
  })

  it('阶段名有中文时返回中文，未知阶段原样返回', () => {
    expect(stageLabel('template')).toBe('模板提取')
    expect(stageLabel('mystery')).toBe('mystery')
  })

  it('折算进度：统计已完成阶段数并找出运行中阶段', () => {
    const progress = toProgress(status({
      stages: {
        prepare: { total: 1, succeeded: 1, failed: 0, running: 0 },
        parse: { total: 3, succeeded: 1, failed: 0, running: 1 },
      },
    }))
    expect(progress.done).toBe(1)
    expect(progress.total).toBe(2)
    expect(progress.stage).toBe('parse')
    expect(progress.failed).toBe(false)
  })

  it('有失败阶段时标记 failed', () => {
    const progress = toProgress(status({
      stages: { parse: { total: 1, succeeded: 0, failed: 1, running: 0 } },
      failed_tasks: ['7:parse:0'],
    }))
    expect(progress.failed).toBe(true)
  })

  it('全部成功后停止轮询', async () => {
    const fetchStatus = vi.fn()
      .mockResolvedValueOnce(status({
        stages: { prepare: { total: 1, succeeded: 1, failed: 0, running: 0 } },
      }))
      .mockResolvedValueOnce(status({
        stages: {
          prepare: { total: 1, succeeded: 1, failed: 0, running: 0 },
          parse: { total: 1, succeeded: 1, failed: 0, running: 0 },
        },
        all_succeeded: true,
      }))
    const updates: number[] = []

    watchIngestProgress(7, fetchStatus, (p) => updates.push(p.done), { intervalMs: 1000 })

    await vi.advanceTimersByTimeAsync(1000)
    await vi.advanceTimersByTimeAsync(1000)
    await vi.advanceTimersByTimeAsync(5000)

    expect(fetchStatus).toHaveBeenCalledTimes(2)
    expect(updates).toEqual([1, 2])
  })

  it('轮询出错不终止，下一轮继续', async () => {
    const fetchStatus = vi.fn()
      .mockRejectedValueOnce(new Error('网络抖动'))
      .mockResolvedValue(status({
        stages: { prepare: { total: 1, succeeded: 1, failed: 0, running: 0 } },
        all_succeeded: true,
      }))

    const updates: number[] = []
    watchIngestProgress(7, fetchStatus, (p) => updates.push(p.done), { intervalMs: 1000 })

    await vi.advanceTimersByTimeAsync(1000)
    await vi.advanceTimersByTimeAsync(1000)

    expect(fetchStatus).toHaveBeenCalledTimes(2)
    expect(updates).toEqual([1])
  })

  it('stop() 之后不再请求', async () => {
    const fetchStatus = vi.fn().mockResolvedValue(status({}))
    const stop = watchIngestProgress(7, fetchStatus, () => {}, { intervalMs: 1000 })

    stop()
    await vi.advanceTimersByTimeAsync(5000)

    expect(fetchStatus).toHaveBeenCalledTimes(0)
  })
})
