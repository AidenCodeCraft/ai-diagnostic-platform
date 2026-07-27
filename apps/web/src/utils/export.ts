/**
 * 对话导出工具
 * 支持导出为 Markdown 格式
 */

export interface ExportMessage {
  role: 'user' | 'assistant' | 'system'
  content: string
  createdAt: number
  sources?: Array<{
    title: string
    source: string
    excerpt?: string
  }>
  thinking?: {
    text: string
    elapsed: number
  }
}

export interface ExportOptions {
  title?: string
  model?: string
  includeMetadata?: boolean
  includeSources?: boolean
  includeThinking?: boolean
}

/**
 * 导出对话为 Markdown 格式
 */
export function exportToMarkdown(
  messages: ExportMessage[],
  options: ExportOptions = {}
): string {
  const {
    title = '对话记录',
    model = 'AI Assistant',
    includeMetadata = true,
    includeSources = true,
    includeThinking = false,
  } = options

  const lines: string[] = []

  // 标题和元数据
  lines.push(`# ${title}`)
  lines.push('')

  if (includeMetadata) {
    lines.push(`> **模型**: ${model}`)
    lines.push(`> **导出时间**: ${new Date().toLocaleString('zh-CN')}`)
    lines.push(`> **消息数量**: ${messages.length}`)
    lines.push('')
  }

  lines.push('---')
  lines.push('')

  // 遍历消息
  messages.forEach((msg, index) => {
    const time = new Date(msg.createdAt).toLocaleTimeString('zh-CN', {
      hour: '2-digit',
      minute: '2-digit',
    })

    // 消息头部
    if (msg.role === 'user') {
      lines.push(`## 👤 用户 (${time})`)
    } else if (msg.role === 'assistant') {
      lines.push(`## 🤖 AI助手 (${time})`)
    } else {
      lines.push(`## 🔧 系统 (${time})`)
    }
    lines.push('')

    // 思维过程（可选）
    if (includeThinking && msg.thinking && msg.thinking.text) {
      lines.push('> **思考过程** ' + `(${msg.thinking.elapsed}秒)`)
      lines.push('>')
      msg.thinking.text.split('\n').forEach(line => {
        lines.push(`> ${line}`)
      })
      lines.push('')
    }

    // 消息内容
    lines.push(msg.content)
    lines.push('')

    // 引用来源（可选）
    if (includeSources && msg.sources && msg.sources.length > 0) {
      lines.push('**参考出处:**')
      lines.push('')
      msg.sources.forEach((source, idx) => {
        lines.push(`${idx + 1}. **${source.title}** - ${source.source}`)
        if (source.excerpt) {
          lines.push(`   > ${source.excerpt.slice(0, 100)}...`)
        }
      })
      lines.push('')
    }

    // 分隔线（除了最后一条消息）
    if (index < messages.length - 1) {
      lines.push('---')
      lines.push('')
    }
  })

  // 页脚
  lines.push('')
  lines.push('---')
  lines.push('')
  lines.push('*导出自 AI Diagnostic Platform*')

  return lines.join('\n')
}

/**
 * 下载文本文件
 */
export function downloadTextFile(content: string, filename: string) {
  const blob = new Blob([content], { type: 'text/plain;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
  URL.revokeObjectURL(url)
}

/**
 * 生成文件名
 */
export function generateFilename(title: string, extension: string): string {
  const cleanTitle = title
    .replace(/[<>:"/\\|?*]/g, '') // 移除非法字符
    .slice(0, 50) // 限制长度
    .trim()
  const timestamp = new Date()
    .toISOString()
    .slice(0, 19)
    .replace(/:/g, '-')
  return `${cleanTitle}_${timestamp}.${extension}`
}

/**
 * 导出对话（主函数）
 */
export async function exportChat(
  messages: ExportMessage[],
  options: ExportOptions = {}
): Promise<void> {
  const title = options.title || '对话记录'
  const markdown = exportToMarkdown(messages, options)
  const filename = generateFilename(title, 'md')
  downloadTextFile(markdown, filename)
}

export default exportChat
