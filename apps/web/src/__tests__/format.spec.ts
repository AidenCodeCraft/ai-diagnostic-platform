import { describe, expect, it } from 'vitest'

import {
  analysisStatusLabel,
  analysisStatusType,
  formatBytes,
  formatDateTime,
} from '@/utils/format'
import { anchorCandidate, normalizeAnchorLine } from '@/utils/markdownLine'

describe('format utils', () => {
  it('formats byte sizes', () => {
    expect(formatBytes(null)).toBe('—')
    expect(formatBytes(512)).toBe('512 B')
    expect(formatBytes(2048)).toBe('2.0 KB')
    expect(formatBytes(5 * 1024 * 1024)).toBe('5.0 MB')
  })

  it('formats empty datetime', () => {
    expect(formatDateTime('')).toBe('')
  })

  it('maps analysis status to label and tag type', () => {
    expect(analysisStatusLabel('pending')).toBe('排队中')
    expect(analysisStatusLabel('running')).toBe('分析中')
    expect(analysisStatusLabel('completed')).toBe('已完成')
    expect(analysisStatusLabel('failed')).toBe('失败')
    expect(analysisStatusLabel('unknown')).toBe('unknown')

    expect(analysisStatusType('pending')).toBe('info')
    expect(analysisStatusType('running')).toBe('warning')
    expect(analysisStatusType('completed')).toBe('success')
    expect(analysisStatusType('failed')).toBe('danger')
  })
})

describe('markdown line anchor', () => {
  it('strips heading / list / ordered-list markers', () => {
    expect(normalizeAnchorLine('## 现象')).toBe('现象')
    expect(normalizeAnchorLine('- 紧急报警')).toBe('紧急报警')
    expect(normalizeAnchorLine('2. 写盘完成')).toBe('写盘完成')
    expect(normalizeAnchorLine('> 引用内容')).toBe('引用内容')
  })

  it('returns empty candidate for too-short lines', () => {
    expect(anchorCandidate('## ')).toBe('')
    expect(anchorCandidate('a')).toBe('')
  })

  it('truncates long lines to the configured length', () => {
    expect(anchorCandidate('x'.repeat(100)).length).toBe(60)
    expect(anchorCandidate('x'.repeat(100), 10).length).toBe(10)
  })
})
