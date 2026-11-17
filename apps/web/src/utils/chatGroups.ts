/**
 * 侧边栏「最近对话」按时间分组（参考 DeepSeek 网页版）：
 *   今天 → 7天内 → 30天内 → 更早按具体月份（YYYY年M月）。
 * 纯函数，便于单元测试。
 */

export interface TimeGroup<T> {
  label: string
  chats: T[]
}

export interface TimeGroupable {
  id: number
  /** 最近更新时间（ISO 字符串）；缺失时按今天处理 */
  updatedAt?: string
}

/** 一天的毫秒数（本地日历日差值按 0 点对齐后计算，不受夏令时影响） */
const DAY_MS = 24 * 60 * 60 * 1000

function timeGroupLabel(updatedAt: string | undefined, startOfToday: number): string {
  const ts = updatedAt ? new Date(updatedAt) : null
  if (!ts || isNaN(ts.getTime())) return '今天'
  const startOfThatDay = new Date(ts.getFullYear(), ts.getMonth(), ts.getDate()).getTime()
  const daysAgo = Math.round((startOfToday - startOfThatDay) / DAY_MS)
  if (daysAgo <= 0) return '今天'
  if (daysAgo <= 7) return '7天内'
  if (daysAgo <= 30) return '30天内'
  return `${ts.getFullYear()}年${ts.getMonth() + 1}月`
}

/**
 * 按时间把会话分组。保持传入顺序（会话列表按最近更新倒序），
 * 同一分组只出现一次（首次出现的位置）。
 */
export function groupChatsByTime<T extends TimeGroupable>(chats: T[], now: Date = new Date()): TimeGroup<T>[] {
  const startOfToday = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime()
  const groups: TimeGroup<T>[] = []
  const byLabel = new Map<string, TimeGroup<T>>()

  for (const chat of chats || []) {
    const label = timeGroupLabel(chat.updatedAt, startOfToday)
    let group = byLabel.get(label)
    if (!group) {
      group = { label, chats: [] }
      byLabel.set(label, group)
      groups.push(group)
    }
    group.chats.push(chat)
  }
  return groups
}
