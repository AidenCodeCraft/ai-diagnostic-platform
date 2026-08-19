/**
 * Markdown 渲染增强配置
 * 支持：代码高亮、表格、数学公式（当依赖安装后）
 */

import { marked } from 'marked'

// 配置 marked 选项
marked.setOptions({
  breaks: true, // 支持 GFM 换行
  gfm: true, // 启用 GitHub Flavored Markdown（已内置表格支持）
  pedantic: false,
})

// 自定义渲染器
const renderer = new marked.Renderer()

// 增强代码块渲染 - 添加语言标签和复制按钮
renderer.code = function ({ text, lang }: { text: string; lang?: string }) {
  const language = lang || 'text'
  const langLabel = language.toUpperCase()

  // 转义 HTML 字符
  const escaped = text
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
      <pre><code class="language-${language}">${escaped}</code></pre>
    </div>
  `
}

// 增强表格渲染 - 添加滚动容器
// marked v18+ renderer.table 接收 Table token，手动构建 HTML 以包裹 wrapper
renderer.table = function (token) {
  const align = token.align || []
  const headerHtml = token.header
    .map((cell, i) => `<th${align[i] ? ` align="${align[i]}"` : ''}>${cell.text}</th>`)
    .join('')
  const bodyHtml = token.rows
    .map(row => `<tr>${row.map((cell, i) => `<td${align[i] ? ` align="${align[i]}"` : ''}>${cell.text}</td>`).join('')}</tr>`)
    .join('')
  return `<div class="table-wrapper"><table><thead><tr>${headerHtml}</tr></thead><tbody>${bodyHtml}</tbody></table></div>`
}

// 增强链接渲染 - 外部链接新窗口打开
renderer.link = function ({ href, title, text }: { href: string; title?: string | null; text: string }) {
  const isExternal = href.startsWith('http://') || href.startsWith('https://')
  const titleAttr = title ? ` title="${title}"` : ''
  const targetAttr = isExternal ? ' target="_blank" rel="noopener noreferrer"' : ''
  return `<a href="${href}"${titleAttr}${targetAttr}>${text}</a>`
}

// 增强图片渲染 - 解析 ref://img/<id> 与平台相对路径，懒加载 + 失败降级
renderer.image = function ({ href, title, text }: { href: string; title?: string | null; text: string }) {
  const alt = (text || title || '图片').replace(/"/g, '&quot;')
  const titleAttr = title ? ` title="${escapeHtml(title)}"` : ''
  const src = resolveImageUrl(href)
  return `<img class="kb-image" src="${src}" alt="${alt}"${titleAttr} loading="lazy" decoding="async" data-original-src="${escapeHtml(href)}" />`
}

/**
 * 把图片 href 解析为浏览器可直接访问的 URL：
 *  - ref://img/<id>   → /api/v1/knowledge/images/<id>
 *  - http(s)/data/绝对路径 → 原样
 *  - 其它相对路径      → 原样（通常由后端在入库时已重写为平台 URL）
 */
function resolveImageUrl(href: string): string {
  if (!href) return ''
  const refImg = href.match(/^ref:\/\/img\/(\d+)$/)
  if (refImg) return `/api/v1/knowledge/images/${refImg[1]}`
  return href
}

function escapeHtml(value: string): string {
  return value
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
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
