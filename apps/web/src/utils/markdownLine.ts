/** 从 Markdown 源行提取可用于定位的纯文本（去掉标题/列表/引用标记）。 */

export function normalizeAnchorLine(rawLine: string): string {
  return (rawLine || '')
    .trim()
    .replace(/^#{1,6}\s*/, '')
    .replace(/^[-*+>]\s*/, '')
    .replace(/^\d+\.\s*/, '')
    .trim()
}

export function anchorCandidate(rawLine: string, maxLength = 60): string {
  const normalized = normalizeAnchorLine(rawLine)
  if (normalized.length < 2) return ''
  return normalized.slice(0, maxLength)
}
