import { describe, expect, it } from 'vitest'

import {
  normalizeCitationMarkdown,
  processRefLinks,
  splitSourcesFromContent,
} from '@/utils/citations'
import { renderMarkdown } from '@/utils/markdown'

describe('normalizeCitationMarkdown', () => {
  it('converts image-style doc citations to link-style citations', () => {
    expect(normalizeCitationMarkdown('结论![引用](ref://2#启动类型)结束')).toBe(
      '结论[引用](ref://2#启动类型)结束',
    )
  })

  it('keeps real knowledge images (ref://img/<id>)', () => {
    const src = '配图 ![](ref://img/12) 完成'
    expect(normalizeCitationMarkdown(src)).toBe(src)
  })

  it('normalizes full-width parens for ref:// links', () => {
    expect(normalizeCitationMarkdown('![图注]（ref://img/12）')).toBe('![图注](ref://img/12)')
    expect(normalizeCitationMarkdown('[1]（ref://2#sec）')).toBe('[1](ref://2#sec)')
  })

  it('removes empty/bare ![] placeholders', () => {
    expect(normalizeCitationMarkdown('引用![]结束')).toBe('引用结束')
    expect(normalizeCitationMarkdown('引用![]()结束')).toBe('引用结束')
  })

  it('keeps code spans and fenced code untouched', () => {
    expect(normalizeCitationMarkdown('`![]` 保留')).toBe('`![]` 保留')
    const fence = '```\n![]\n```'
    expect(normalizeCitationMarkdown(fence)).toBe(fence)
  })
})

describe('splitSourcesFromContent', () => {
  it('splits trailing 参考来源 lines from the body', () => {
    const text = '正文内容\n\n参考来源：知识库"超速规则"文档\n参考来源：知识库"客流逻辑"文档'
    const { body, sourcesText } = splitSourcesFromContent(text)
    expect(body).toBe('正文内容')
    expect(sourcesText).toBe('参考来源：知识库"超速规则"文档\n参考来源：知识库"客流逻辑"文档')
  })

  it('extracts 参考来源 lines wherever they appear', () => {
    const text = '参考来源：知识库"A"文档\n正文继续'
    const { body, sourcesText } = splitSourcesFromContent(text)
    expect(body).toBe('正文继续')
    expect(sourcesText).toContain('参考来源')
  })
})

const sources = [
  { id: 57, num: 1, title: '超速规则', source: '知识库', excerpt: '摘要A', start_line: 10 },
  { id: 58, num: 2, title: '客流逻辑', source: '知识库', excerpt: '摘要B', start_line: 20 },
]

describe('processRefLinks', () => {

  it('resolves ref://N by retrieval num (not real doc id)', () => {
    const { bodyHtml } = processRefLinks(
      '<p>结论<a href="ref://2#启动类型">1</a></p>',
      '',
      sources,
    )
    expect(bodyHtml).toContain('data-doc-id="58"')
    expect(bodyHtml).not.toContain('data-doc-id="2"')
  })

  it('numbers knowledge points ①②③ in order of appearance', () => {
    const { bodyHtml } = processRefLinks(
      '<p>先<a href="ref://2#启动类型">1</a>后<a href="ref://1#概述">1</a></p>',
      '',
      sources,
    )
    expect(bodyHtml).toContain('>①</a>')
    expect(bodyHtml).toContain('>②</a>')
    expect(bodyHtml.indexOf('①')).toBeLessThan(bodyHtml.indexOf('②'))
  })

  it('dedupes the same knowledge point to one marker at the first (key) position', () => {
    const { bodyHtml } = processRefLinks(
      '<p>一<a href="ref://2#启动类型">1</a>二<a href="ref://2#启动类型">1</a>三<a href="ref://2#启动类型">1</a></p>',
      '',
      sources,
    )
    expect(bodyHtml.match(/ref-seq/g)?.length).toBe(1)
    expect(bodyHtml).toContain('一<a')
    expect(bodyHtml).toContain('二三')
  })

  it('keeps different sections of the same doc as different knowledge points', () => {
    const { bodyHtml } = processRefLinks(
      '<p>一<a href="ref://2#启动类型">1</a>二<a href="ref://2#配置">1</a></p>',
      '',
      sources,
    )
    expect(bodyHtml.match(/ref-seq/g)?.length).toBe(2)
  })

  it('falls back to sources order for legacy messages without num', () => {
    const legacy = [
      { id: 57, title: '超速规则', source: '知识库', excerpt: '' },
      { id: 58, title: '客流逻辑', source: '知识库', excerpt: '' },
    ]
    const { bodyHtml } = processRefLinks(
      '<p>x<a href="ref://2#sec">1</a></p>',
      '',
      legacy,
    )
    expect(bodyHtml).toContain('data-doc-id="58"')
  })

  it('drops unresolvable citations instead of linking the wrong document', () => {
    const { bodyHtml } = processRefLinks(
      '<p>x<a href="ref://99#sec">1</a>y</p>',
      '',
      [{ id: 57, num: 1, title: '唯一文档', source: '知识库', excerpt: '' }],
    )
    expect(bodyHtml).not.toContain('ref-seq')
    expect(bodyHtml).not.toContain('data-doc-id')
  })

  it('renders footer source lines with matching ① numbers and real doc ids', () => {
    const sourcesHtml = renderMarkdown(
      '参考来源：知识库"[客流逻辑](ref://2)"文档中"[启动类型](ref://2#启动类型)"部分',
    )
    const { sourcesHtml: out } = processRefLinks(
      '<p>结论<a href="ref://2#启动类型">1</a></p>',
      sourcesHtml,
      sources,
    )
    expect(out).toContain('ref-source-num">①')
    expect(out).toContain('data-doc-id="58"')
    expect(out).not.toContain('data-doc-id="2"')
    expect(out).toContain('ref-source-doc')
    expect(out).toContain('ref-source-section')
  })

  it('appends fallback source lines when the answer has no citations', () => {
    const { sourcesHtml } = processRefLinks('<p>完全没有引用的回答</p>', '', sources)
    expect(sourcesHtml).toContain('ref-source-line')
    expect(sourcesHtml).toContain('①')
    expect(sourcesHtml).toContain('data-doc-id="57"')
  })
})

describe('renderMarkdown table cells', () => {
  it('renders inline markdown (images/links/bold/code) inside table cells', () => {
    const md = '| 名称 | 说明 |\n|---|---|\n| **加粗** | `code` [1](ref://2#sec) ![](ref://img/12) |'
    const html = renderMarkdown(md)
    expect(html).toContain('<strong>加粗</strong>')
    expect(html).toContain('<code>code</code>')
    expect(html).toContain('<a href="ref://2#sec">')
    expect(html).toContain('class="kb-image"')
    expect(html).not.toContain('![]')
  })
})

describe('end-to-end citation rendering', () => {
  it('turns image-style citations into ① markers and resolves by num', () => {
    const answer =
      '启动类型有三种![引用](ref://2#启动类型)，其中一种![引用](ref://2#启动类型)。\n\n' +
      '参考来源：知识库"[客流逻辑](ref://2)"文档中"[启动类型](ref://2#启动类型)"部分'
    const { body, sourcesText } = splitSourcesFromContent(answer)
    const bodyHtml = renderMarkdown(normalizeCitationMarkdown(body))
    const sourcesHtml = renderMarkdown(normalizeCitationMarkdown(sourcesText))
    const out = processRefLinks(bodyHtml, sourcesHtml, sources)

    // 两个重复引用只留一个 ① 标记
    expect(out.bodyHtml.match(/ref-seq/g)?.length).toBe(1)
    expect(out.bodyHtml).toContain('①')
    expect(out.bodyHtml).toContain('data-doc-id="58"')
    expect(out.sourcesHtml).toContain('ref-source-num">①')
  })
})
