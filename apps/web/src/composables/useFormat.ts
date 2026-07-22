/**
 * 通用格式化工具 composable
 */

export function useFormat() {
  function formatFileSize(bytes: number): string {
    if (bytes < 1024) return bytes + ' B'
    if (bytes < 1048576) return (bytes / 1024).toFixed(1) + ' KB'
    return (bytes / 1048576).toFixed(1) + ' MB'
  }

  function fileIcon(type: string): string {
    if (/pdf/i.test(type)) return '📄'
    if (/zip|tar|gz|rar/i.test(type)) return '📦'
    if (/image/i.test(type)) return '🖼️'
    return '📋'
  }

  function truncateText(text: string, maxLen = 30): string {
    return text.length > maxLen ? text.slice(0, maxLen) + '...' : text
  }

  return { formatFileSize, fileIcon, truncateText }
}
