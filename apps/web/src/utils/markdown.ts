/**
 * Markdown 渲染增强配置
 * 支持：代码高亮、表格、数学公式（当依赖安装后）
 */

import { marked } from 'marked'

// 配置 marked 选项
marked.setOptions({
  breaks: true, // 支持 GFM 换行
  gfm: true, // 启用 GitHub Flavored Markdown
  tables: true, // 支持表格
  pedantic: false,
})

// 自定义渲染器
const renderer = new marked.Renderer()

// 增强代码块渲染 - 添加语言标签和复制按钮
const originalCode = renderer.code.bind(renderer)
renderer.code = function (code: string, language: string | undefined) {
  const lang = language || 'text'
  const langLabel = lang.toUpperCase()
  
  // 转义 HTML 字符
  const escaped = code
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')
  
  return `
    <div class="code-block-wrapper">
      <div class="code-block-header">
        <span class="code-block-lang">${langLabel}</span>
        <button class="code-block-copy" onclick="copyCode(this)" title="复制代码">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <rect x="9" y="9" width="13" height="13" rx="2"/>
            <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/>
          </svg>
        </button>
      </div>
      <pre><code class="language-${lang}">${escaped}</code></pre>
    </div>
  `
}

// 增强表格渲染 - 添加滚动容器
const originalTable = renderer.table.bind(renderer)
renderer.table = function (header: string, body: string) {
  const table = originalTable(header, body)
  return `<div class="table-wrapper">${table}</div>`
}

// 增强链接渲染 - 外部链接新窗口打开
const originalLink = renderer.link.bind(renderer)
renderer.link = function (href: string, title: string | null | undefined, text: string) {
  const isExternal = href.startsWith('http://') || href.startsWith('https://')
  const titleAttr = title ? ` title="${title}"` : ''
  const targetAttr = isExternal ? ' target="_blank" rel="noopener noreferrer"' : ''
  return `<a href="${href}"${titleAttr}${targetAttr}>${text}</a>`
}

marked.use({ renderer })

/**
 * 渲染 Markdown 文本
 */
export function renderMarkdown(text: string): string {
  try {
    return marked.parse(text) as string
  } catch (error) {
    console.error('Markdown render error:', error)
    return text.replace(/\n/g, '<br>')
  }
}

/**
 * 全局复制代码函数（供内联 onclick 调用）
 */
declare global {
  interface Window {
    copyCode: (btn: HTMLButtonElement) => void
  }
}

if (typeof window !== 'undefined') {
  window.copyCode = async function (btn: HTMLButtonElement) {
    const wrapper = btn.closest('.code-block-wrapper')
    const code = wrapper?.querySelector('code')?.textContent || ''
    
    try {
      await navigator.clipboard.writeText(code)
      btn.classList.add('copied')
      btn.innerHTML = `
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <polyline points="20 6 9 17 4 12"/>
        </svg>
      `
      setTimeout(() => {
        btn.classList.remove('copied')
        btn.innerHTML = `
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <rect x="9" y="9" width="13" height="13" rx="2"/>
            <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/>
          </svg>
        `
      }, 2000)
    } catch (error) {
      console.error('Copy failed:', error)
    }
  }
}

export default renderMarkdown
