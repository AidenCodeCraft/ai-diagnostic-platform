import { describe, expect, it } from 'vitest'

import { appendVersion, applyVersion, snapshotVersion } from '@/utils/messageVersions'

describe('messageVersions 编辑重发版本历史', () => {
  it('appendVersion 保留旧内容并写透到新版本', () => {
    const msg: any = { content: '原始提问' }
    const idx = appendVersion(msg, '修改后的提问')
    expect(idx).toBe(1)
    expect(msg.content).toBe('修改后的提问')
    expect(msg.activeVersion).toBe(1)
    expect(msg.versions.map((v: any) => v.content)).toEqual(['原始提问', '修改后的提问'])
  })

  it('appendVersion 在已有版本上继续追加', () => {
    const msg: any = {
      content: 'v2',
      versions: [{ content: 'v1' }, { content: 'v2' }],
      activeVersion: 1,
    }
    const idx = appendVersion(msg, 'v3')
    expect(idx).toBe(2)
    expect(msg.versions.map((v: any) => v.content)).toEqual(['v1', 'v2', 'v3'])
    expect(msg.activeVersion).toBe(2)
  })

  it('snapshotVersion 归档当前内容（含 sources/thinking）到指定下标', () => {
    const msg: any = {
      content: '旧回答',
      sources: [{ id: 1 }],
      thinking: { text: 't', elapsed: 3, active: false },
    }
    const idx = snapshotVersion(msg, 0)
    expect(idx).toBe(0)
    expect(msg.versions[0].content).toBe('旧回答')
    expect(msg.versions[0].sources).toEqual([{ id: 1 }])
    expect(msg.versions[0].thinking.elapsed).toBe(3)
    // 快照是拷贝，不随后续修改而变化
    msg.content = '新回答'
    expect(msg.versions[0].content).toBe('旧回答')
  })

  it('applyVersion 切换版本并写回 content/sources/thinking', () => {
    const msg: any = {
      content: 'v2',
      sources: [{ id: 2 }],
      versions: [
        { content: 'v1', sources: [{ id: 1 }], thinking: { text: 'old', elapsed: 1 } },
        { content: 'v2', sources: [{ id: 2 }] },
      ],
      activeVersion: 1,
    }
    expect(applyVersion(msg, 0)).toBe(true)
    expect(msg.content).toBe('v1')
    expect(msg.sources).toEqual([{ id: 1 }])
    expect(msg.thinking.elapsed).toBe(1)
    expect(msg.activeVersion).toBe(0)

    expect(applyVersion(msg, 5)).toBe(false)
    expect(msg.content).toBe('v1')
    expect(msg.activeVersion).toBe(0)
  })
})
