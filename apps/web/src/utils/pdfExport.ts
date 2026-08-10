/**
 * PDF 报告导出工具
 *
 * 将对话消息导出为格式化 PDF，支持中文（使用内置字体或 Unicode 字符）。
 */

import { jsPDF } from 'jspdf'

export interface PdfExportOptions {
  title?: string
  model?: string
  includeMetadata?: boolean
  pageSize?: [number, number] // [width, height] in mm
  fontSize?: number
}

export interface PdfMessage {
  role: string
  content: string
  createdAt?: number
}

/** 移除 Markdown 标记，保留纯文本（用于 PDF 渲染） */
function stripMarkdown(text: string): string {
  return text
    .replace(/#{1,6}\s/g, '')        // 标题
    .replace(/\*\*(.+?)\*\*/g, '$1')  // 粗体
    .replace(/\*(.+?)\*/g, '$1')      // 斜体
    .replace(/`{1,3}[^`]*`{1,3}/g, '') // 代码
    .replace(/\[(.+?)\]\(.+?\)/g, '$1') // 链接
    .replace(/!\[.*?\]\(.+?\)/g, '')   // 图片
    .replace(/>\s/g, '')               // 引用
    .replace(/[-*+]\s/g, '• ')         // 无序列表
    .replace(/^\d+\.\s/gm, '')         // 有序列表
    .replace(/---+/g, '─────────')     // 分割线
    .replace(/\n{3,}/g, '\n\n')        // 压缩多余空行
    .trim()
}

/**
 * 导出消息列表为 PDF 并触发下载
 */
export async function exportToPdf(
  messages: PdfMessage[],
  options: PdfExportOptions = {},
): Promise<void> {
  const {
    title = '诊断报告',
    model = '',
    includeMetadata = true,
    pageSize = [210, 297], // A4
    fontSize = 11,
  } = options

  const doc = new jsPDF({ unit: 'mm', format: pageSize })
  const pageWidth = pageSize[0]
  const marginLeft = 20
  const marginRight = 20
  const contentWidth = pageWidth - marginLeft - marginRight
  const lineHeight = fontSize * 0.45 // mm per line

  let y = 25

  // ── 标题 ──
  doc.setFontSize(18)
  doc.setFont('helvetica', 'bold')
  doc.text(title, marginLeft, y)
  y += 10

  // ── 元数据 ──
  if (includeMetadata) {
    doc.setFontSize(9)
    doc.setFont('helvetica', 'normal')
    doc.setTextColor(100, 100, 100)
    const exportTime = new Date().toLocaleString('zh-CN')
    doc.text(`导出时间: ${exportTime}`, marginLeft, y)
    y += 5
    if (model) {
      doc.text(`模型: ${model}`, marginLeft, y)
      y += 5
    }
    doc.text(`消息数量: ${messages.length}`, marginLeft, y)
    y += 5
    doc.text(`生成自: AI Diagnostic Platform`, marginLeft, y)
    y += 5
    doc.setTextColor(0, 0, 0)

    // 分割线
    y += 3
    doc.setDrawColor(200, 200, 200)
    doc.line(marginLeft, y, pageWidth - marginRight, y)
    y += 8
  }

  doc.setFontSize(fontSize)

  for (let i = 0; i < messages.length; i++) {
    const msg = messages[i]
    const roleLabel = msg.role === 'user' ? '用户' : 'AI 助手'
    const cleanContent = stripMarkdown(msg.content || '')

    if (!cleanContent) continue

    // 分页检查（预留至少 30mm 空间）
    if (y > pageSize[1] - 30) {
      doc.addPage()
      y = 20
    }

    // 角色标签
    doc.setFont('helvetica', 'bold')
    doc.setTextColor(msg.role === 'user' ? 37 : 16, msg.role === 'user' ? 99 : 185, msg.role === 'user' ? 235 : 129)
    const roleText = `[${roleLabel}]`
    doc.text(roleText, marginLeft, y)
    y += lineHeight + 1

    // 消息正文（分行渲染）
    doc.setFont('helvetica', 'normal')
    doc.setTextColor(30, 30, 30)

    const lines = doc.splitTextToSize(cleanContent, contentWidth)
    for (const line of lines) {
      if (y > pageSize[1] - 20) {
        doc.addPage()
        y = 20
      }
      // 跳过纯空行
      if (typeof line === 'string' && !line.trim()) {
        y += lineHeight * 0.6
        continue
      }
      doc.text(line, marginLeft, y)
      y += lineHeight
    }

    y += 6 // 消息间距

    // 消息分隔线（非最后一条）
    if (i < messages.length - 1) {
      doc.setDrawColor(230, 230, 230)
      doc.line(marginLeft + 5, y, pageWidth - marginRight - 5, y)
      y += 6
    }
  }

  // ── 页脚 ──
  const pageCount = doc.getNumberOfPages()
  for (let p = 1; p <= pageCount; p++) {
    doc.setPage(p)
    doc.setFontSize(8)
    doc.setFont('helvetica', 'normal')
    doc.setTextColor(160, 160, 160)
    doc.text(
      `AI Diagnostic Platform - ${title}`,
      marginLeft,
      pageSize[1] - 10,
    )
    doc.text(
      `${p} / ${pageCount}`,
      pageWidth - marginRight,
      pageSize[1] - 10,
      { align: 'right' },
    )
  }

  // ── 触发下载 ──
  const filename = `${title.replace(/[\\/:*?"<>|]/g, '_')}.pdf`
  doc.save(filename)
}
