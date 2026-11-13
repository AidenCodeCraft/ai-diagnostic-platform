/** 通用格式化与状态映射（供管理页与测试复用）。 */

export function formatBytes(size: number | null | undefined): string {
  if (size == null) return '—'
  if (size < 1024) return `${size} B`
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`
  return `${(size / 1024 / 1024).toFixed(1)} MB`
}

export function formatDateTime(ts: string | null | undefined): string {
  if (!ts) return ''
  try {
    return new Date(ts).toLocaleString()
  } catch {
    return ts
  }
}

export function analysisStatusLabel(status: string): string {
  const map: Record<string, string> = {
    pending: '排队中',
    running: '分析中',
    completed: '已完成',
    failed: '失败',
  }
  return map[status] || status
}

export function analysisStatusType(status: string): 'info' | 'warning' | 'success' | 'danger' {
  const map: Record<string, 'info' | 'warning' | 'success' | 'danger'> = {
    pending: 'info',
    running: 'warning',
    completed: 'success',
    failed: 'danger',
  }
  return map[status] || 'info'
}
