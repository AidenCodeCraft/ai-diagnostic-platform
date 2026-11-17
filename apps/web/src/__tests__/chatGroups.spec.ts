import { describe, expect, it } from 'vitest'

import { groupChatsByTime } from '@/utils/chatGroups'

// 固定“现在”：2026-11-17 15:00 本地时间
const NOW = new Date(2026, 10, 17, 15, 0, 0)

/** 本地时间的 ISO 字符串（与后端 updated_at 序列化格式一致） */
function iso(y: number, m: number, d: number): string {
  return new Date(y, m - 1, d, 10, 0, 0).toISOString()
}

function chat(id: number, updatedAt?: string) {
  return { id, title: `对话${id}`, updatedAt }
}

describe('groupChatsByTime 侧边栏时间分组', () => {
  it('按 今天 / 7天内 / 30天内 / 具体月份 分组', () => {
    const groups = groupChatsByTime(
      [
        chat(1, iso(2026, 11, 17)), // 今天
        chat(2, iso(2026, 11, 14)), // 3 天前 → 7天内
        chat(3, iso(2026, 11, 10)), // 7 天前 → 7天内
        chat(4, iso(2026, 11, 9)), // 8 天前 → 30天内
        chat(5, iso(2026, 10, 18)), // 30 天前 → 30天内
        chat(6, iso(2026, 10, 8)), // 40 天前 → 2026年10月
        chat(7, iso(2026, 5, 1)), // 半年前 → 2026年5月
      ],
      NOW,
    )
    expect(groups.map(g => g.label)).toEqual(['今天', '7天内', '30天内', '2026年10月', '2026年5月'])
    expect(groups[0].chats.map(c => c.id)).toEqual([1])
    expect(groups[1].chats.map(c => c.id)).toEqual([2, 3])
    expect(groups[2].chats.map(c => c.id)).toEqual([4, 5])
    expect(groups[3].chats.map(c => c.id)).toEqual([6])
    expect(groups[4].chats.map(c => c.id)).toEqual([7])
  })

  it('同月的更早会话合并到一个月份分组', () => {
    const groups = groupChatsByTime(
      [chat(1, iso(2026, 9, 30)), chat(2, iso(2026, 9, 2))],
      NOW,
    )
    expect(groups).toHaveLength(1)
    expect(groups[0].label).toBe('2026年9月')
    expect(groups[0].chats.map(c => c.id)).toEqual([1, 2])
  })

  it('缺失时间戳的会话归入「今天」，分组保持首次出现顺序', () => {
    const groups = groupChatsByTime(
      [chat(1), chat(2, iso(2026, 11, 17)), chat(3, iso(2026, 11, 15))],
      NOW,
    )
    expect(groups.map(g => g.label)).toEqual(['今天', '7天内'])
    expect(groups[0].chats.map(c => c.id)).toEqual([1, 2])
  })

  it('空列表返回空分组', () => {
    expect(groupChatsByTime([], NOW)).toEqual([])
    expect(groupChatsByTime(undefined as any, NOW)).toEqual([])
  })
})
