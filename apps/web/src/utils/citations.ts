/**
 * 引用（ref://）渲染工具。
 *
 * 约定：
 *  - LLM 输出的引用形如 `[n](ref://文档ID#章节名)`，
 *    底部参考来源形如 `参考来源：知识库"[文档标题](ref://文档ID)"文档中"[章节名](ref://文档ID#章节名)"部分`。
 *  - 「文档ID」是知识库检索结果列表中的数字编号（每个文档标题前的 `1.`、`2.`、`3.`…），
 *    通过 source.num 与检索结果编号对齐（旧数据无 num 时按 sources 顺序回退）。
 *  - 正文引用渲染为 ①②③ 序号标记：
 *    同一知识点（文档+章节）只在最关键处（首次出现）保留一个标记，
 *    不同知识点按出现顺序编号。
 */

export interface CitationSource {
  id?: number
  /** 检索结果编号（与 LLM 看到的文档编号一致） */
  num?: number
  title: string
  source?: string
  excerpt?: string
  section?: string
  start_line?: number
}

interface RefInfo {
  id?: number
  num?: number
  title: string
  excerpt: string
  source: string
  start_line?: number
}

const CIRCLED_NUMS = '①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳'

export function circledNum(n: number): string {
  return n >= 1 && n <= 20 ? CIRCLED_NUMS[n - 1] : `(${n})`
}

function safeDecode(value: string): string {
  try {
    return decodeURIComponent(value || '')
  } catch {
    return value || ''
  }
}

/** 章节锚点归一化（%20 解码、去空白、小写），用于知识点去重与编号匹配 */
function normKey(anchor: string | undefined): string {
  return safeDecode(anchor || '').trim().replace(/\s+/g, ' ').toLowerCase()
}

function escapeAttr(value: string): string {
  return value
    .replace(/&/g, '&amp;')
    .replace(/"/g, '&quot;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/'/g, '&#39;')
}

function escapeHtml(value: string): string {
  return value
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')
}

// ── 分离参考来源行 ──────────────────────────────────────────
// 从 LLM 输出中提取底部参考来源行，返回 { body, sourcesText } 两部分
export function splitSourcesFromContent(text: string): { body: string; sourcesText: string } {
  const lines = text.split('\n')
  const sourceLines: string[] = []
  const bodyLines: string[] = []

  // 从末尾向前扫描，收集连续的参考来源行
  for (let i = lines.length - 1; i >= 0; i--) {
    const trimmed = lines[i].trim()
    if (/^\|?\s*参考来源：/.test(trimmed)) {
      sourceLines.unshift(lines[i])
    } else if (trimmed === '') {
      // 跳过参考来源行之间的空行
      if (sourceLines.length > 0 && i < lines.length - 1 && /^\|?\s*参考来源：/.test(lines[i + 1]?.trim() || '')) {
        continue
      }
      bodyLines.unshift(lines[i])
    } else {
      bodyLines.unshift(lines[i])
    }
  }

  return {
    body: bodyLines.join('\n').trim(),
    sourcesText: sourceLines.join('\n').trim(),
  }
}

// ── 引用语法归一化（renderMarkdown 之前调用） ───────────────
/**
 * 处理 LLM 输出中不规范的引用/图片语法：
 *  1. 全角括号链接 `![x]（ref://…）` / `[x]（ref://…）` → 半角括号
 *  2. 图片式引用 `![x](ref://文档ID#章节)`（非 ref://img/）→ 链接式引用，避免渲染成坏图
 *  3. 移除空图片占位 `![]()` / `![]`（LLM 幻觉的"引用图标"残留）
 * 代码块与行内代码中的内容保持原样。
 */
export function normalizeCitationMarkdown(text: string): string {
  const transform = (segment: string): string => {
    let out = segment
    // 1. 全角括号 → 半角（仅 ref:// 链接）
    out = out.replace(/(!?\[[^\]]*\])（(ref:\/\/[^）]*)）/g, '$1($2)')
    // 2. 图片式引用 → 链接式引用（ref://img/ 的真图片保留）
    out = out.replace(/!\[([^\]]*)\]\((ref:\/\/(?!img\/)[^)]*)\)/g, '[$1]($2)')
    // 3a. 空图片占位（空 alt + 空 URL）
    out = out.replace(/!\[\]\(\s*\)/g, '')
    // 3b. 无 URL 的裸 `![]`
    out = out.replace(/!\[\](?!\()/g, '')
    return out
  }

  const outLines: string[] = []
  let inFence = false
  for (const line of text.split('\n')) {
    if (/^\s*(```|~~~)/.test(line)) {
      inFence = !inFence
      outLines.push(line)
      continue
    }
    if (inFence) {
      outLines.push(line)
      continue
    }
    // 行内代码片段（`...`）保持原样，只处理代码外的片段
    const parts = line.split(/(`[^`]*`)/)
    for (let i = 0; i < parts.length; i++) {
      if (i % 2 === 0) parts[i] = transform(parts[i])
    }
    outLines.push(parts.join(''))
  }
  return outLines.join('\n')
}

// ── ref:// 链接处理 ─────────────────────────────────────────
/**
 * 处理 ref:// 协议的引用链接：
 *  1. 正文中的引用链接 → ①②③ 序号标记（同一知识点只保留最关键处的一个标记）；
 *  2. 参考来源行中的文档/章节链接 → 可点击链接，并带上对应的 ①②③ 序号；
 *  3. 无法定位到来源的引用 → 移除标记（不再错链到无关文档）。
 */
export function processRefLinks(
  bodyHtml: string,
  sourcesHtml: string,
  sources: CitationSource[],
  isStreaming = false,
): { bodyHtml: string; sourcesHtml: string } {
  // ── 构建映射表 ──
  // byNum: 检索结果编号 → source（LLM 的 ref://N 即检索结果编号）
  // byId:  真实文档 ID → source
  // titleMap: 文档标题 → source（LLM 输出 ref://FAQ 等非数字 ID 时反查）
  const byNum = new Map<string, RefInfo>()
  const byId = new Map<string, RefInfo>()
  const titleMap = new Map<string, RefInfo>()
  const ordered: RefInfo[] = []
  for (const s of sources || []) {
    if (!s || !s.title) continue
    const id = typeof s.id === 'number' ? s.id : parseInt(String(s.id ?? ''), 10)
    const info: RefInfo = {
      id: Number.isFinite(id) ? id : undefined,
      num: typeof s.num === 'number' ? s.num : undefined,
      title: s.title,
      excerpt: s.excerpt || '',
      source: s.source || '知识库',
      start_line: typeof s.start_line === 'number' ? s.start_line : undefined,
    }
    if (info.id != null) byId.set(String(info.id), info)
    if (info.num != null) byNum.set(String(info.num), info)
    ordered.push(info)
    const t = (s.title || '').trim().toLowerCase()
    if (t && !titleMap.has(t)) titleMap.set(t, info)
    // 简化版标题（去掉括号内容等）
    const simplified = (s.title || '').replace(/[（(][^)）]*[)）]/g, '').trim().toLowerCase()
    if (simplified && !titleMap.has(simplified)) titleMap.set(simplified, info)
  }
  const hasNum = byNum.size > 0

  /**
   * 根据 ref:// 后的 ID 文本解析出来源信息。
   * 数字 ID 的语义是「检索结果编号」：优先按 num 匹配，
   * 旧数据（无 num）按 sources 顺序回退，最后尝试真实文档 ID / 标题。
   * 无法解析时返回 null —— 绝不猜测映射到无关文档。
   */
  function resolveDocId(rawId: string): RefInfo | null {
    const byNumHit = byNum.get(rawId)
    if (byNumHit) return byNumHit
    const n = parseInt(rawId, 10)
    if (!hasNum && !isNaN(n) && n >= 1 && n <= ordered.length) {
      // 旧数据：LLM 只见过检索结果序号，sources 顺序与检索结果顺序一致
      return ordered[n - 1]
    }
    const byIdHit = byId.get(rawId)
    if (byIdHit) return byIdHit
    const decoded = safeDecode(rawId).trim().toLowerCase()
    if (!decoded) return null
    const byTitle = titleMap.get(decoded)
    if (byTitle) return byTitle
    for (const info of ordered) {
      const t = info.title.toLowerCase()
      if (t.includes(decoded) || decoded.includes(t)) return info
    }
    return null
  }

  function makeSeqMarker(n: number, info: RefInfo, anchor: string | undefined): string {
    const realId = info.id != null ? String(info.id) : ''
    const anchorAttr = anchor ? ` data-anchor="${escapeAttr(anchor)}"` : ''
    const excerptAttr = info.excerpt ? ` data-excerpt="${escapeAttr(info.excerpt)}"` : ''
    const lineAttr = info.start_line ? ` data-line="${info.start_line}"` : ''
    return (
      `<a class="ref-link ref-seq" data-doc-id="${escapeAttr(realId)}"` +
      ` data-title="${escapeAttr(info.title)}" data-source="${escapeAttr(info.source)}"` +
      `${excerptAttr}${anchorAttr}${lineAttr}` +
      ` href="javascript:void(0)" title="点击查看文档">${circledNum(n)}</a>`
    )
  }

  // ── 知识点编号（按正文出现顺序分配 ①②③…） ──
  // 知识点 = 文档 + 章节；同一知识点重复引用只保留首个（最关键）标记
  const knowledgeNumbers = new Map<string, number>()
  const numberKeyByDoc = new Map<string, number>()
  let nextNum = 1

  function numberFor(realId: string, anchor: string): number {
    const key = `${realId}|${normKey(anchor)}`
    const existing = knowledgeNumbers.get(key)
    if (existing != null) return existing
    const docFallback = realId ? numberKeyByDoc.get(realId) : undefined
    if (docFallback != null) return docFallback
    const n = nextNum++
    knowledgeNumbers.set(key, n)
    if (realId && !numberKeyByDoc.has(realId)) numberKeyByDoc.set(realId, n)
    return n
  }

  // ── 第一步：正文中的引用链接 → ①②③ 序号标记 ──
  bodyHtml = bodyHtml.replace(
    /<a\s+href="ref:\/\/([^"#]+)(?:#([^"]*))?"[^>]*>([\s\S]*?)<\/a>/gi,
    (match, rawId: string, anchor: string) => {
      if (match.includes('class="ref-link')) return match
      const info = resolveDocId(rawId)
      if (!info) return '' // 无法定位来源 → 移除标记，避免错链
      const realId = info.id != null ? String(info.id) : ''
      const key = `${realId}|${normKey(anchor)}`
      if (knowledgeNumbers.has(key)) return '' // 同一知识点重复引用 → 只保留最关键处（首个）
      const n = numberFor(realId, anchor || '')
      return makeSeqMarker(n, info, anchor)
    },
  )

  // ── 第二步：参考来源行中的文档链接 → 带 ①②③ 序号的可点击链接 ──
  // 情况A：LLM 使用了 Markdown 链接语法 [文档名](ref://id)
  sourcesHtml = sourcesHtml.replace(
    /(?:<p>)?\|?\s*参考来源：知识库(?:&quot;|"|\u201C|\u201D)<a\s+href="ref:\/\/([^"\s#]+)"[^>]*>([^<]*)<\/a>(?:&quot;|"|\u201C|\u201D)文档(?:中(?:&quot;|"|\u201C|\u201D)<a\s+href="ref:\/\/([^"\s#]+)(?:#([^"]*))?"[^>]*>([^<]*)<\/a>(?:&quot;|"|\u201C|\u201D)部分)?\s*\|?(?:<\/p>)?/gi,
    (_match, rawDocId: string, docTitle: string, rawSectionId: string, sectionAnchor: string, sectionTitle: string) => {
      const info = resolveDocId(rawDocId)
      const docId = info && info.id != null ? String(info.id) : ''
      const plain = docTitle || (info ? info.title : rawDocId)
      if (!docId) {
        // 无法定位 → 纯文本展示，不生成错链
        return sectionTitle
          ? `<span class="ref-source-line"><span style="color: gray;">参考来源：知识库“${escapeHtml(plain)}”文档中“${escapeHtml(sectionTitle)}”部分</span></span>`
          : `<span class="ref-source-line"><span style="color: gray;">参考来源：知识库“${escapeHtml(plain)}”文档</span></span>`
      }
      const n = numberFor(docId, sectionAnchor || sectionTitle || '')
      const excerptAttr = info?.excerpt ? ` data-excerpt="${escapeAttr(info.excerpt)}"` : ''
      const lineAttr = info?.start_line ? ` data-line="${info.start_line}"` : ''
      const docLink = `<a class="ref-link ref-source-doc" data-doc-id="${escapeAttr(docId)}" data-title="${escapeAttr(plain)}" data-source="${escapeAttr(info?.source || '知识库')}"${excerptAttr}${lineAttr} href="javascript:void(0)">${escapeHtml(plain)}</a>`

      if (sectionTitle && rawSectionId) {
        const sectionInfo = resolveDocId(rawSectionId) || info
        const sectionId = sectionInfo && sectionInfo.id != null ? String(sectionInfo.id) : docId
        const sectionAnchorAttr = sectionAnchor ? ` data-anchor="${escapeAttr(sectionAnchor)}"` : ` data-anchor="${escapeAttr(encodeURIComponent(sectionTitle))}"`
        const sectionLineAttr = sectionInfo?.start_line ? ` data-line="${sectionInfo.start_line}"` : lineAttr
        const sectionLink = `<a class="ref-link ref-source-section" data-doc-id="${escapeAttr(sectionId)}" data-title="${escapeAttr(sectionTitle)}" data-source="${escapeAttr(info?.source || '知识库')}"${sectionAnchorAttr}${excerptAttr}${sectionLineAttr} href="javascript:void(0)">${escapeHtml(sectionTitle)}</a>`
        return `<span class="ref-source-line"><span class="ref-source-num">${circledNum(n)}</span><span style="color: gray;">参考来源：知识库“${docLink}”文档中“${sectionLink}”部分</span></span>`
      }
      return `<span class="ref-source-line"><span class="ref-source-num">${circledNum(n)}</span><span style="color: gray;">参考来源：知识库“${docLink}”文档</span></span>`
    },
  )

  // 情况B（兜底）：LLM 没有使用 Markdown 链接，纯文本格式
  {
    // 引号 alternation（&quot;、英文直引号、中文弯引号），内容排除尖括号与引号
    const pattern = /(?:<p>)?\|?\s*参考来源：知识库(?:&quot;|"|“|”)([^<>“”"]+?)(?:&quot;|"|“|”)文档(?:中(?:&quot;|"|“|”)([^<>“”"]+?)(?:&quot;|"|“|”)部分)?\s*\|?(?:<\/p>)?/gi
    sourcesHtml = sourcesHtml.replace(pattern, (_match, docTitleRaw: string, sectionTitleRaw: string) => {
      const docTitle = (docTitleRaw || '').trim()
      const sectionTitle = (sectionTitleRaw || '').trim()
      if (!docTitle) return _match

      const info = resolveDocId(docTitle)
      const docId = info && info.id != null ? String(info.id) : ''
      if (!docId) {
        return sectionTitle
          ? `<span class="ref-source-line"><span style="color: gray;">参考来源：知识库“${escapeHtml(docTitle)}”文档中“${escapeHtml(sectionTitle)}”部分</span></span>`
          : `<span class="ref-source-line"><span style="color: gray;">参考来源：知识库“${escapeHtml(docTitle)}”文档</span></span>`
      }
      const n = numberFor(docId, sectionTitle)
      const excerptAttr = info?.excerpt ? ` data-excerpt="${escapeAttr(info.excerpt)}"` : ''
      const lineAttr = info?.start_line ? ` data-line="${info.start_line}"` : ''
      const docLink = `<a class="ref-link ref-source-doc" data-doc-id="${escapeAttr(docId)}" data-title="${escapeAttr(docTitle)}" data-source="${escapeAttr(info?.source || '知识库')}"${excerptAttr}${lineAttr} href="javascript:void(0)">${escapeHtml(docTitle)}</a>`

      if (sectionTitle) {
        const sectionLink = `<a class="ref-link ref-source-section" data-doc-id="${escapeAttr(docId)}" data-title="${escapeAttr(sectionTitle)}" data-source="${escapeAttr(info?.source || '知识库')}" data-anchor="${escapeAttr(encodeURIComponent(sectionTitle))}"${excerptAttr}${lineAttr} href="javascript:void(0)">${escapeHtml(sectionTitle)}</a>`
        return `<span class="ref-source-line"><span class="ref-source-num">${circledNum(n)}</span><span style="color: gray;">参考来源：知识库“${docLink}”文档中“${sectionLink}”部分</span></span>`
      }
      return `<span class="ref-source-line"><span class="ref-source-num">${circledNum(n)}</span><span style="color: gray;">参考来源：知识库“${docLink}”文档</span></span>`
    })
  }

  // ── 兜底：有来源但回答中没有任何引用/参考来源行时，追加参考来源 ──
  if (
    ordered.length > 0 &&
    !isStreaming &&
    knowledgeNumbers.size === 0 &&
    !sourcesHtml.includes('class="ref-link') &&
    bodyHtml.trim().length > 0 &&
    !/知识库中暂无/.test(bodyHtml)
  ) {
    const sourceLines = ordered.map((info) => {
      const docId = info.id != null ? String(info.id) : ''
      const n = numberFor(docId, '')
      const lineAttr = info.start_line ? ` data-line="${info.start_line}"` : ''
      const docLink = `<a class="ref-link ref-source-doc" data-doc-id="${escapeAttr(docId)}" data-title="${escapeAttr(info.title)}" data-source="${escapeAttr(info.source)}" data-excerpt="${escapeAttr(info.excerpt)}"${lineAttr} href="javascript:void(0)">${escapeHtml(info.title)}</a>`
      return `<span class="ref-source-line"><span class="ref-source-num">${circledNum(n)}</span><span style="color: gray;">参考来源：知识库“${docLink}”文档</span></span>`
    })
    sourcesHtml = (sourcesHtml || '') + sourceLines.join('')
  }

  // ref-source-line 为块级元素：marked 的行间软换行（<br>）夹在两个来源行之间
  // 会额外渲染出一行空白（①② 之间的空行），统一清除
  sourcesHtml = sourcesHtml
    .replace(/<br\s*\/?>\s*(?=<span class="ref-source-line")/gi, '')
    .replace(/(<\/span>)\s*<br\s*\/?>\s*(?=<span class="ref-source-line"|<\/p>|$)/gi, '$1')

  return { bodyHtml, sourcesHtml }
}