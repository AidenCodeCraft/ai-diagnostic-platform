<template>
  <div class="chat-messages" :class="{ 'is-empty': isEmpty }" ref="container">
    <div v-if="messages.length === 0" class="welcome-full">
      <div class="welcome-inner">
        <div class="welcome-icon">
          <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="#9ca3af" stroke-width="1.5">
            <circle cx="12" cy="12" r="10" />
            <path d="M8 14s1.5 2 4 2 4-2 4-2" />
            <line x1="9" y1="9" x2="9.01" y2="9" />
            <line x1="15" y1="9" x2="15.01" y2="9" />
          </svg>
        </div>
        <h2>有什么可以帮助你的？</h2>
      </div>
    </div>

    <template v-else>
      <div v-for="msg in sorted" :key="msg.id" class="message-row" :class="msg.role">
        <div class="message-body">
          <!-- AI 思维链（默认展开，显示完整推理过程） -->
          <div v-if="msg.role === 'assistant' && msg.thinking && (msg.thinking.text || msg.thinking.active)"
            class="think-block">
            <div class="think-header">
              <button class="think-toggle" @click="toggleThink(msg)">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <circle cx="12" cy="12" r="10" />
                  <path d="M12 6v6l4 2" />
                </svg>
                <span>{{ msg.thinking.active ? '正在思考...' : `已思考（用时 ${msg.thinking.elapsed || 1} 秒）` }}</span>
                <span class="think-action">{{ msg._thinkOpen === false ? '展开' : '收起' }}</span>
                <svg class="think-arrow" :class="{ open: msg._thinkOpen !== false }" width="12" height="12"
                  viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <polyline points="6 9 12 15 18 9" />
                </svg>
              </button>
            </div>
            <div v-show="msg._thinkOpen !== false" class="think-body">{{ msg.thinking.text || '正在准备回答…' }}</div>
          </div>
          <div v-if="msg.files && msg.files.length > 0" class="msg-files">
            <div v-for="(f, i) in msg.files" :key="i" class="msg-file-card" @click="$emit('previewFile', f)"
              :title="'点击预览 ' + f.name">
              <span class="msg-file-icon">{{ fileIconEmoji(f.type) }}</span>
              <span class="msg-file-name">{{ f.name }}</span>
              <span class="msg-file-size">{{ formatSize(f.size) }}</span>
            </div>
          </div>
          <div class="message-bubble">
            <div v-if="editingId === msg.id" class="msg-edit">
              <textarea ref="editTextarea" v-model="editText" class="msg-edit-textarea" rows="1" placeholder="修改提问内容…"
                @input="autoGrowEdit" @keydown.enter.exact.prevent="submitEdit(msg)"
                @keydown.escape="cancelEdit"></textarea>
              <div class="msg-edit-actions">
                <button class="msg-edit-btn" @click="cancelEdit">取消</button>
                <button class="msg-edit-btn primary" :disabled="!editText.trim()" @click="submitEdit(msg)">发送</button>
              </div>
            </div>
            <div v-else class="msg-content"
              v-html="renderContent(msg.content, msg, msg.files && msg.files.length > 0, msg.sources, msg.thinking?.active)"
              @click="onMsgContentClick" @mouseover="onMsgContentMouseOver" @mouseout="onMsgContentMouseOut"></div>
            <div v-if="msg.clarification && msg.clarification.length" class="clarify-block">
              <div v-for="(q, qi) in msg.clarification" :key="qi" class="clarify-item">
                <span class="clarify-label">{{ q.label }}</span>
                <div class="clarify-options">
                  <button v-for="opt in (q.options || [])" :key="opt" type="button" class="clarify-option"
                    @click="pickClarification(opt)">{{ opt }}</button>
                </div>
              </div>
            </div>
            <div v-if="msg._renderedSources && !isNoMatchResponse(msg.content)" class="msg-sources"
              v-html="msg._renderedSources" @click="onMsgContentClick" @mouseover="onMsgContentMouseOver"
              @mouseout="onMsgContentMouseOut"></div>
            <KnowledgeImageGallery
              v-if="msg.role === 'assistant' && msg.content && !loading && !msg.thinking?.active && !isNoMatchResponse(msg.content) && getImages(msg).length > 0"
              :images="getImages(msg)" />
          </div>
          <!-- 版本切换（编辑重发后保留历史提问/回答，‹ › 切换查看） -->
          <div v-if="msg.role === 'user' && editingId !== msg.id && !loading && msg.versions && msg.versions.length > 1"
            class="msg-version-nav">
            <button class="ver-btn" :disabled="(msg.activeVersion ?? 0) <= 0" title="上一版本"
              @click="switchVersion(msg, -1)">‹</button>
            <span class="ver-count">{{ (msg.activeVersion ?? 0) + 1 }} / {{ msg.versions.length }}</span>
            <button class="ver-btn" :disabled="(msg.activeVersion ?? 0) >= msg.versions.length - 1" title="下一版本"
              @click="switchVersion(msg, 1)">›</button>
          </div>
          <div v-if="msg.role === 'assistant' && msg.content && !msg.thinking?.active && !loading"
            class="message-actions">
            <button class="action-btn" :class="{ active: copiedId === msg.id }" @click="copyMessage(msg)"
              :title="copiedId === msg.id ? '已复制' : '复制回复'">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <rect x="9" y="9" width="13" height="13" rx="2" />
                <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
              </svg>
            </button>
            <button class="action-btn" @click="regenerateMessage(msg)" title="重新生成">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <polyline points="23 4 23 10 17 10" />
                <polyline points="1 20 1 14 7 14" />
                <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15" />
              </svg>
            </button>
            <button v-if="msg._persisted" class="action-btn" :class="{ active: msg._resolved }"
              @click="resolveMessage(msg)" :title="msg._resolved ? '已标记解决' : '标记已解决并沉淀知识'">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <polyline points="20 6 9 17 4 12" />
              </svg>
            </button>
            <button class="action-btn" :class="{ active: msg._liked }" @click="likeMessage(msg)" title="有帮助">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path
                  d="M14 9V5a3 3 0 0 0-3-3l-4 9v11h11.28a2 2 0 0 0 2-1.7l1.38-9a2 2 0 0 0-2-2.3zM7 22H4a2 2 0 0 1-2-2v-7a2 2 0 0 1 2-2h3" />
              </svg>
            </button>
            <button class="action-btn" :class="{ active: msg._disliked }" @click="dislikeMessage(msg)" title="无帮助">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path
                  d="M10 15v4a3 3 0 0 0 3 3l4-9V2H5.72a2 2 0 0 0-2 1.7l-1.38 9a2 2 0 0 0 2 2.3zm7-13h2.67A2.31 2.31 0 0 1 22 4v7a2.31 2.31 0 0 1-2.33 2H17" />
              </svg>
            </button>
          </div>
          <div v-else-if="msg.role === 'user' && msg.content && editingId !== msg.id" class="message-actions">
            <button class="action-btn" @click="startEdit(msg)" title="修改">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M17 3a2.83 2.83 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5Z" />
              </svg>
            </button>
            <button class="action-btn" @click="copyMessage(msg)" title="复制">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <rect x="9" y="9" width="13" height="13" rx="2" />
                <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
              </svg>
            </button>
          </div>
        </div>
      </div>
      <div v-if="loading" class="message-row assistant">
        <div class="message-avatar">
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#2563eb" stroke-width="1.5">
            <circle cx="12" cy="12" r="10" />
            <path d="M8 14s1.5 2 4 2 4-2 4-2" />
          </svg>
        </div>
        <div class="message-body">
          <div class="message-bubble typing">
            <span class="dot"></span><span class="dot"></span><span class="dot"></span>
          </div>
        </div>
      </div>
    </template>

    <!-- 引用文档 Tooltip -->
    <Teleport to="body">
      <div v-if="tooltip.visible" class="ref-tooltip" :style="{ top: tooltip.y + 'px', left: tooltip.x + 'px' }"
        @mouseenter="cancelTooltipHide" @mouseleave="scheduleTooltipHide">
        <div class="ref-tooltip-title">{{ tooltip.title }}</div>
        <div class="ref-tooltip-source">{{ tooltip.source }}</div>
        <div class="ref-tooltip-excerpt" v-html="tooltip.excerptRendered"></div>
      </div>
    </Teleport>

    <!-- 右侧文档预览面板 -->
    <Teleport to="body">
      <div v-if="docPanel.visible" class="doc-panel-overlay" @click="closeDocPanel"></div>
      <div v-if="docPanel.visible" class="doc-panel">
        <div class="doc-panel-header">
          <span class="doc-panel-title">{{ docPanel.title }}</span>
          <button class="doc-panel-close" @click="closeDocPanel" title="关闭">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <line x1="18" y1="6" x2="6" y2="18" />
              <line x1="6" y1="6" x2="18" y2="18" />
            </svg>
          </button>
        </div>
        <div class="doc-panel-body">
          <div v-if="docPanel.loading" class="doc-panel-spinner">
            <div class="spinner"></div>
          </div>
          <div v-else-if="docPanel.error" class="doc-panel-error">{{ docPanel.error }}</div>
          <div v-else class="doc-panel-content" v-html="docPanel.renderedContent" ref="docPanelContentRef"></div>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, nextTick, onBeforeUnmount, onMounted, reactive } from 'vue'
import { renderMarkdown } from '@/utils/markdown'
import { anchorCandidate } from '@/utils/markdownLine'
import { splitSourcesFromContent, normalizeCitationMarkdown, processRefLinks } from '@/utils/citations'
import { useFormat } from '@/composables/useFormat'
import { chatApi, type ChatImage } from '@/api/chat'
import { knowledgeApi } from '@/api/knowledge'
import KnowledgeImageGallery from './KnowledgeImageGallery.vue'

const { formatFileSize, fileIcon } = useFormat()

const props = defineProps<{
  messages: any[]
  loading: boolean
  isEmpty?: boolean
  chatId?: number
}>()

const emit = defineEmits<{
  (e: 'previewFile', file: { name: string; size: number; type: string }): void
  (e: 'openKnowledge', source: { id?: number; title: string }): void
  (e: 'regenerate', msg: any): void
  /** 内联编辑完成后重发（携带修改后的文本，由父组件做版本化保存） */
  (e: 'editSend', msg: any, newText: string): void
  /** 切换消息版本（编辑重发历史） */
  (e: 'switchVersion', msg: any, index: number): void
  (e: 'selectClarification', text: string): void
}>()

// ── 引用文档 Tooltip ──────────────────────────────────────────
const tooltip = reactive({
  visible: false,
  x: 0,
  y: 0,
  title: '',
  source: '',
  excerpt: '',
  excerptRendered: '',
})
let tooltipTimer: ReturnType<typeof setTimeout> | null = null

// ── 右侧文档预览面板 ──────────────────────────────────────────
const docPanel = reactive({
  lineNo: 0,
  visible: false,
  loading: false,
  error: '',
  title: '',
  content: '',
  renderedContent: '',
  anchorId: '',
})
const docPanelContentRef = ref<HTMLElement>()

// 缓存已获取的文档内容
const docCache = new Map<number, { title: string; content: string; source: string; excerpt: string }>()

function cancelTooltipHide() {
  if (tooltipTimer) {
    clearTimeout(tooltipTimer)
    tooltipTimer = null
  }
}

function scheduleTooltipHide() {
  cancelTooltipHide()
  tooltipTimer = setTimeout(() => {
    tooltip.visible = false
  }, 200)
}

async function openDocPanel(docId: number, title: string, anchorId: string, lineNo = 0) {
  docPanel.visible = true
  docPanel.title = title
  docPanel.anchorId = anchorId
  docPanel.lineNo = lineNo
  docPanel.error = ''

  // 检查缓存
  const cached = docCache.get(docId)
  if (cached) {
    docPanel.content = cached.content
    docPanel.renderedContent = renderMarkdown(cached.content)
    docPanel.loading = false
    nextTick(() => scrollToDocAnchor())
    return
  }

  docPanel.loading = true
  try {
    const { data } = await knowledgeApi.get(docId)
    const content = data.content || ''
    docCache.set(docId, {
      title: data.title,
      content,
      source: data.category || '知识库',
      excerpt: content.slice(0, 200),
    })
    docPanel.content = content
    docPanel.renderedContent = renderMarkdown(content)
    docPanel.loading = false
    await nextTick()
    scrollToDocAnchor()
  } catch (err: any) {
    docPanel.error = '加载文档失败: ' + (err.response?.data?.detail || err.message)
    docPanel.loading = false
  }
}

function scrollToDocAnchor() {
  // 使用 requestAnimationFrame 确保 v-html 渲染完成后再查找元素
  requestAnimationFrame(() => {
    requestAnimationFrame(() => {
      if (!docPanelContentRef.value) return
      const body = docPanelContentRef.value

      // 如果有明确的锚点名，先尝试精确定位
      if (docPanel.anchorId) {
        const decoded = decodeURIComponent(docPanel.anchorId).trim()
        if (!decoded) { body.scrollTop = 0; return }

        // 优先查找标题（完全匹配或包含）
        const headings = body.querySelectorAll('h1, h2, h3, h4, h5, h6')
        for (const h of headings) {
          const hText = h.textContent?.trim() || ''
          if (hText === decoded || hText.includes(decoded)) {
            h.scrollIntoView({ behavior: 'smooth', block: 'start' })
            h.classList.add('doc-anchor-highlight')
            setTimeout(() => h.classList.remove('doc-anchor-highlight'), 3000)
            tryScrollToLine(body)
            return
          }
        }
        // 查找包含锚点文本的段落/表格/列表
        const elements = body.querySelectorAll('p, li, td, th, strong, em')
        for (const el of elements) {
          const elText = el.textContent?.trim() || ''
          if (elText.includes(decoded)) {
            el.scrollIntoView({ behavior: 'smooth', block: 'center' })
            el.classList.add('doc-anchor-highlight')
            setTimeout(() => el.classList.remove('doc-anchor-highlight'), 3000)
            tryScrollToLine(body)
            return
          }
        }
        // 宽泛匹配：遍历所有包含文本的叶子节点
        const walker = document.createTreeWalker(body, NodeFilter.SHOW_TEXT, null)
        let node: Text | null
        while ((node = walker.nextNode() as Text)) {
          if (node.textContent?.includes(decoded)) {
            const parent = node.parentElement
            if (parent) {
              parent.scrollIntoView({ behavior: 'smooth', block: 'center' })
              parent.classList.add('doc-anchor-highlight')
              setTimeout(() => parent.classList.remove('doc-anchor-highlight'), 3000)
              tryScrollToLine(body)
              return
            }
          }
        }
      }

      // 无锚点 / 锚点未命中时：按 start_line 精确定位
      if (tryScrollToLine(body)) return

      // 无锚点时滚动到顶部
      body.scrollTop = 0
    })
  })
}

/** 按引用命中的 start_line 在已渲染文档中定位到对应段落并高亮 */
function tryScrollToLine(body: HTMLElement): boolean {
  const lineNo = docPanel.lineNo || 0
  if (lineNo <= 0) return false
  const lines = (docPanel.content || '').split('\n')
  const rawLine = (lines[lineNo - 1] || '').trim()
  if (!rawLine) return false
  const needle = anchorCandidate(rawLine)
  if (!needle) return false

  const candidates = body.querySelectorAll('p, li, td, th, h1, h2, h3, h4, h5, h6')
  for (const el of candidates) {
    if ((el.textContent || '').includes(needle)) {
      el.scrollIntoView({ behavior: 'smooth', block: 'center' })
      el.classList.add('doc-anchor-highlight')
      setTimeout(() => el.classList.remove('doc-anchor-highlight'), 3000)
      return true
    }
  }
  return false
}

function closeDocPanel() {
  docPanel.visible = false
  docPanel.anchorId = ''
  docPanel.lineNo = 0
}

// ── Vue 模板级事件委托（处理 v-html 中的 ref-link 元素） ──
function findRefLink(el: HTMLElement): HTMLElement | null {
  if (el.classList.contains('ref-link')) return el
  // 向上查找父级 ref-link（处理序号链接内部可能的子元素）
  let parent = el.parentElement
  while (parent) {
    if (parent.classList.contains('ref-link')) return parent
    parent = parent.parentElement
  }
  return null
}

function onMsgContentClick(e: Event) {
  const target = e.target as HTMLElement
  const refLink = findRefLink(target)
  if (refLink) {
    handleRefClickFor(refLink)
    return
  }
  // 内联知识库图片：点击新标签打开原图
  if (target.tagName === 'IMG' && (target as HTMLImageElement).classList.contains('kb-image')) {
    const src = (target as HTMLImageElement).getAttribute('src')
    if (src && src.startsWith('/api/')) {
      window.open(src, '_blank', 'noopener')
    }
  }
}

function onMsgContentMouseOver(e: Event) {
  const target = e.target as HTMLElement
  const refLink = findRefLink(target)
  if (refLink) {
    handleRefMouseEnterFor(refLink)
  }
}

function onMsgContentMouseOut(e: Event) {
  const target = e.target as HTMLElement
  const refLink = findRefLink(target)
  if (refLink) {
    handleRefMouseLeaveFor()
  }
}

function handleRefClickFor(el: HTMLElement) {
  const docIdStr = el.getAttribute('data-doc-id')
  const title = el.getAttribute('data-title') || ''
  const anchorId = el.getAttribute('data-anchor') || ''
  const lineNo = parseInt(el.getAttribute('data-line') || '0', 10) || 0

  if (!docIdStr) return

  const docId = parseInt(docIdStr, 10)
  if (isNaN(docId)) return

  tooltip.visible = false
  openDocPanel(docId, title, anchorId, lineNo)
}

function handleRefMouseEnterFor(el: HTMLElement) {
  const title = el.getAttribute('data-title') || ''
  const source = el.getAttribute('data-source') || '知识库'
  const excerpt = el.getAttribute('data-excerpt') || ''
  if (!title && !excerpt) return

  const rect = el.getBoundingClientRect()
  tooltip.title = title
  tooltip.source = source
  tooltip.excerpt = excerpt

  // 只提取 excerpt 中的标题行（# ~ #####），过滤掉正文段落
  const headingLines = excerpt
    .split('\n')
    .filter(line => /^#{1,5}\s/.test(line.trim()))
  const excerptDisplay = headingLines.length > 0
    ? headingLines.join('\n')
    : excerpt.slice(0, 200) // 无标题时截取前200字符作为摘要

  try {
    tooltip.excerptRendered = renderMarkdown(excerptDisplay)
  } catch {
    tooltip.excerptRendered = excerptDisplay.replace(/\n/g, '<br>')
  }
  tooltip.x = Math.min(rect.left + rect.width / 2, window.innerWidth - 200)
  tooltip.y = rect.top - 8
  tooltip.visible = true
  cancelTooltipHide()
}

function handleRefMouseLeaveFor() {
  scheduleTooltipHide()
}

onMounted(() => {
  document.addEventListener('error', onImageError, true)
})

onBeforeUnmount(() => {
  cancelTooltipHide()
  document.removeEventListener('error', onImageError, true)
})

// ── 消息排序 ─────────────────────────────────────────────────
const sorted = computed(() => {
  return [...props.messages].sort((a, b) => (a.createdAt || 0) - (b.createdAt || 0))
})

const container = ref<HTMLElement>()

function fileIconEmoji(type: string) {
  return fileIcon(type)
}

function formatSize(bytes: number) {
  return formatFileSize(bytes)
}

// ── 判断是否为无匹配响应 ────────────────────────────────────
function isNoMatchResponse(content: string): boolean {
  if (!content) return false
  return /知识库中暂无.*相关信息/.test(content)
}

// ── 关联图片：从 sources 中扁平化去重 ────────────────────────
function collectImages(sources: any[] | undefined): ChatImage[] {
  if (!Array.isArray(sources)) return []
  const seen = new Set<number>()
  const out: ChatImage[] = []
  for (const s of sources) {
    if (Array.isArray(s?.images)) {
      for (const img of s.images) {
        if (img && typeof img.id === 'number' && img.url && !seen.has(img.id)) {
          seen.add(img.id)
          out.push(img)
        }
      }
    }
  }
  return out
}

// 以 sources 数组引用为键做缓存：流式期间 sources 引用不变 → 图片列表稳定，不闪烁
const imagesCache = new WeakMap<object, ChatImage[]>()
function getImages(msg: any): ChatImage[] {
  if (!msg || !Array.isArray(msg.sources)) return []
  let imgs = imagesCache.get(msg.sources)
  if (!imgs) {
    imgs = collectImages(msg.sources)
    imagesCache.set(msg.sources, imgs)
  }
  return imgs
}

// ── 内联图片 id 校验（过滤 LLM 幻觉 id → 降级为占位） ────────
function validateInlineImages(html: string, sources: any[] = []): string {
  const validIds = new Set<string>()
  for (const s of sources) {
    if (Array.isArray(s?.images)) {
      for (const img of s.images) {
        if (img && img.id != null) validIds.add(String(img.id))
      }
    }
  }
  return html.replace(
    /<img[^>]*class="kb-image"[^>]*data-original-src="ref:\/\/img\/(\d+)"[^>]*>/gi,
    (m, id: string) => (validIds.has(id) ? m : '<span class="img-missing-inline">🖼 图片缺失</span>'),
  )
}

// 内联图片加载失败兜底（img error 不冒泡，需捕获阶段监听）
function onImageError(e: Event) {
  const el = e.target as HTMLElement | null
  if (!el || el.tagName !== 'IMG') return
  if (!(el as HTMLImageElement).classList.contains('kb-image')) return
  if (el.closest('.kb-image-gallery')) return  // 画廊内部自己处理
  const span = document.createElement('span')
  span.className = 'img-missing-inline'
  span.textContent = '🖼 图片缺失'
  el.replaceWith(span)
}

// ── 消息内容渲染 ──────────────────────────────────────────
function renderContent(text: string, msg: any, hasFiles?: boolean, sources: any[] = [], isStreaming = false): string {
  let display = text
  if (hasFiles) {
    display = display.replace(/\n?\[上传文件:.*?\]/g, '')
  }

  // 分离参考来源行 + 引用语法归一化
  const { body, sourcesText } = splitSourcesFromContent(display)

  try {
    let bodyHtml = renderMarkdown(normalizeCitationMarkdown(body))
    bodyHtml = validateInlineImages(bodyHtml, sources)
    const sourcesHtml = sourcesText ? renderMarkdown(normalizeCitationMarkdown(sourcesText)) : ''
    // 处理 ref:// 引用：正文 → ①②③ 标记（同知识点去重）；参考来源 → 带序号的可点击链接
    const processed = processRefLinks(bodyHtml, sourcesHtml, sources, isStreaming)
    msg._renderedBody = processed.bodyHtml
    msg._renderedSources = processed.sourcesHtml

    // 兼容旧版调用（v-html），返回值即正文 HTML
    return msg._renderedBody
  } catch {
    const escaped = display.replace(/\n/g, '<br>')
    msg._renderedBody = escaped
    msg._renderedSources = ''
    return escaped
  }
}

// Auto-scroll when new messages arrive or content grows (streaming)
watch(
  () => props.messages.length,
  () => {
    nextTick(() => {
      if (container.value) {
        container.value.scrollTop = container.value.scrollHeight
      }
    })
  },
)

// Auto-scroll during streaming: watch message content and thinking text changes
watch(
  () => props.messages.map((m: any) => ({
    id: m.id,
    contentLen: (m.content || '').length,
    thinkingLen: (m.thinking?.text || '').length,
    thinkingActive: m.thinking?.active || false,
  })),
  () => {
    nextTick(() => {
      if (container.value) {
        container.value.scrollTop = container.value.scrollHeight
      }
    })
  },
  { deep: false },
)

// 展开/折叠思维链区块（默认展开，只有显式设为 false 才折叠）
function toggleThink(msg: any) {
  msg._thinkOpen = msg._thinkOpen === false ? true : false
}

const copiedId = ref<string | number | null>(null)
async function copyMessage(msg: any) {
  try {
    await navigator.clipboard.writeText(msg.content)
  } catch {
    const textarea = document.createElement('textarea')
    textarea.value = msg.content
    textarea.style.position = 'fixed'
    textarea.style.opacity = '0'
    document.body.appendChild(textarea)
    textarea.select()
    document.execCommand('copy')
    textarea.remove()
  }
  copiedId.value = msg.id
  window.setTimeout(() => { if (copiedId.value === msg.id) copiedId.value = null }, 1600)
}

function regenerateMessage(msg: any) {
  emit('regenerate', msg)
}

// ── 消息内联编辑（DeepSeek 风格：编辑框覆盖在原气泡上，发送/取消在框内） ──
const editingId = ref<string | number | null>(null)
const editText = ref('')
const editTextarea = ref<HTMLTextAreaElement>()

function startEdit(msg: any) {
  editingId.value = msg.id
  // 去掉文件标签，只编辑文字（与旧版填入输入框的行为一致）
  editText.value = (msg.content || '').replace(/\n?\[上传文件:.*?\]/g, '').trim()
  nextTick(() => {
    const el = editTextarea.value
    if (!el) return
    el.style.height = 'auto'
    el.style.height = `${el.scrollHeight}px`
    el.focus()
    el.selectionStart = el.selectionEnd = el.value.length
  })
}

function autoGrowEdit(e: Event) {
  const el = e.target as HTMLTextAreaElement
  el.style.height = 'auto'
  el.style.height = `${el.scrollHeight}px`
}

function cancelEdit() {
  editingId.value = null
  editText.value = ''
}

function submitEdit(msg: any) {
  const text = editText.value.trim()
  if (!text) return
  editingId.value = null
  emit('editSend', msg, text)
}

function switchVersion(msg: any, delta: number) {
  const idx = (msg.activeVersion ?? 0) + delta
  if (idx < 0 || idx >= (msg.versions?.length ?? 0)) return
  emit('switchVersion', msg, idx)
}

function likeMessage(msg: any) {
  const newLiked = !msg._liked
  msg._liked = newLiked
  if (newLiked) msg._disliked = false
  if (props.chatId) {
    chatApi.updateFeedback(props.chatId, msg.id, newLiked ? 'like' : null)
      .catch(e => console.warn('[likeMessage] persist failed:', e))
  }
}

function dislikeMessage(msg: any) {
  const newDisliked = !msg._disliked
  msg._disliked = newDisliked
  if (newDisliked) msg._liked = false
  if (props.chatId) {
    chatApi.updateFeedback(props.chatId, msg.id, newDisliked ? 'dislike' : null)
      .catch(e => console.warn('[dislikeMessage] persist failed:', e))
  }
}

/** 澄清选项芯片：把选项内容回填给父组件（填入输入框） */
function pickClarification(value: string) {
  emit('selectClarification', value)
}

/** 标记「已解决」并触发自进化蒸馏（仅对已持久化的消息可用） */
async function resolveMessage(msg: any) {
  if (!props.chatId || !msg._persisted) return
  try {
    await chatApi.resolveMessage(props.chatId, msg.id, true)
    msg._resolved = true
  } catch (e) {
    console.warn('[resolveMessage] failed:', e)
  }
}

defineExpose({ scrollToBottom })
function scrollToBottom() {
  nextTick(() => {
    if (container.value) {
      container.value.scrollTop = container.value.scrollHeight
    }
  })
}
</script>

<style scoped>
.chat-messages {
  flex: 1;
  overflow-y: auto;
  padding: 42px 24px 24px;
  display: flex;
  flex-direction: column;
  align-items: center;
}

/* 无对话时不自撑满高度，让输入框紧贴提示语下方 */
.chat-messages.is-empty {
  flex: none;
  overflow: visible;
}

.chat-messages.is-empty .welcome-full {
  flex: none;
}

.welcome-full {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 0 24px;
  gap: 24px;
  width: 100%;
  max-width: var(--chat-content-width);
  margin: 0 auto;
}

.welcome-inner {
  text-align: center;
}

.welcome-icon {
  margin-bottom: 12px;
  opacity: 0.5;
}

.welcome-inner h2 {
  font-size: 22px;
  font-weight: 500;
  color: var(--chat-welcome-text);
  margin: 0;
}

.message-row {
  display: flex;
  gap: 10px;
  margin-bottom: 24px;
  width: 100%;
  max-width: var(--chat-content-width);
}

.message-row.user {
  justify-content: flex-end;
}

.message-row.assistant {
  justify-content: flex-start;
}

.message-body {
  flex: 1;
  max-width: 100%;
  min-width: 0;
}

.message-row.user .message-body {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  max-width: 85%;
}

.message-bubble {
  padding: 0;
  border-radius: 14px;
  line-height: 1.8;
  font-size: 15px;
  color: var(--chat-msg-text);
}

.message-row.user .message-bubble {
  max-width: 85%;
  padding: 11px 16px;
  background: var(--chat-msg-user-bg);
  border: 1px solid var(--chat-msg-user-border);
  border-bottom-right-radius: 5px;
}

.message-row.assistant .message-bubble {
  background: transparent;
}

.typing {
  display: flex;
  gap: 5px;
  align-items: center;
  padding: 14px 18px;
}

.dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: #9ca3af;
  animation: bounce 1.4s infinite ease-in-out both;
}

.dot:nth-child(1) {
  animation-delay: -0.32s;
}

.dot:nth-child(2) {
  animation-delay: -0.16s;
}

@keyframes bounce {

  0%,
  80%,
  100% {
    transform: scale(0);
  }

  40% {
    transform: scale(1);
  }
}

.msg-files {
  display: flex;
  flex-direction: column;
  gap: 2px;
  margin-bottom: 4px;
  align-items: flex-end;
}

/* 澄清反问选项 */
.clarify-block {
  margin-top: 10px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.clarify-item {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.clarify-label {
  font-size: 13px;
  font-weight: 600;
  color: #374151;
}

.clarify-options {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.clarify-option {
  padding: 4px 12px;
  border: 1px solid #bfdbfe;
  background: #eff6ff;
  color: #2563eb;
  border-radius: 999px;
  font-size: 13px;
  cursor: pointer;
  transition: all 0.15s;
}

.clarify-option:hover {
  background: #2563eb;
  color: #fff;
  border-color: #2563eb;
}

.msg-file-card {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  background: #edf3fe;
  border: 1px solid #bfdbfe;
  border-radius: 8px;
  cursor: pointer;
  transition: background 0.15s;
  max-width: 280px;
}

.msg-file-card:hover {
  background: #dbeafe;
}

.msg-file-icon {
  font-size: 18px;
  flex-shrink: 0;
}

.msg-file-name {
  font-size: 12px;
  color: #1e40af;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  flex: 1;
}

.msg-file-size {
  font-size: 11px;
  color: #93c5fd;
  flex-shrink: 0;
}

.msg-content :deep(h2) {
  font-size: 17px;
  font-weight: 600;
  margin: 12px 0 6px;
}

.msg-content :deep(h3) {
  font-size: 15px;
  font-weight: 600;
  margin: 10px 0 4px;
}

.msg-content :deep(p) {
  margin: 4px 0;
}

.msg-content :deep(ul),
.msg-content :deep(ol) {
  padding-left: 20px;
  margin: 4px 0;
}

.msg-content :deep(li) {
  margin: 2px 0;
}

/* 行内代码 */
.msg-content :deep(code) {
  background: var(--chat-msg-code-bg);
  padding: 2px 6px;
  border-radius: 4px;
  font-size: 13px;
  font-family: 'Consolas', 'Monaco', 'Courier New', monospace;
}

/* 代码块容器 */
.msg-content :deep(.code-block-wrapper) {
  position: relative;
  margin: 12px 0;
  border-radius: 8px;
  overflow: hidden;
  background: var(--chat-msg-pre-bg);
  border: 1px solid var(--chat-msg-pre-border);
}

.msg-content :deep(.code-block-header) {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 12px;
  background: rgba(0, 0, 0, 0.05);
  border-bottom: 1px solid var(--chat-msg-pre-border);
}

.msg-content :deep(.code-block-lang) {
  font-size: 11px;
  font-weight: 600;
  color: var(--chat-msg-pre-text);
  opacity: 0.7;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.msg-content :deep(.code-block-copy) {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 4px 8px;
  border: 1px solid transparent;
  border-radius: 4px;
  background: transparent;
  color: var(--chat-msg-pre-text);
  font-size: 12px;
  cursor: pointer;
  opacity: 0.6;
  transition: all 0.15s;
}

.msg-content :deep(.code-block-copy:hover) {
  opacity: 1;
  background: rgba(255, 255, 255, 0.1);
}

.msg-content :deep(.code-block-copy.copied) {
  color: #10b981;
}

.msg-content :deep(.code-block-wrapper pre) {
  margin: 0;
  padding: 14px 16px;
  background: var(--chat-msg-pre-bg);
  color: var(--chat-msg-pre-text);
  overflow-x: auto;
  font-size: 13px;
  line-height: 1.6;
}

.msg-content :deep(.code-block-wrapper pre code) {
  background: none;
  padding: 0;
  color: inherit;
  font-family: 'Consolas', 'Monaco', 'Courier New', monospace;
}

/* 兼容旧样式的普通 pre */
.msg-content :deep(pre:not(.code-block-wrapper pre)) {
  background: var(--chat-msg-pre-bg);
  color: var(--chat-msg-pre-text);
  border: 1px solid var(--chat-msg-pre-border);
  padding: 14px 16px;
  border-radius: 8px;
  overflow-x: auto;
  margin: 10px 0;
  font-size: 13px;
  line-height: 1.6;
}

.msg-content :deep(blockquote) {
  border-left: 3px solid var(--chat-msg-blockquote-border);
  padding-left: 10px;
  color: var(--chat-msg-blockquote-text);
  margin: 6px 0;
}

/* 表格容器 - 支持横向滚动 */
.msg-content :deep(.table-wrapper) {
  overflow-x: auto;
  margin: 12px 0;
  border-radius: 8px;
  border: 1px solid var(--chat-msg-table-border);
}

.msg-content :deep(table) {
  border-collapse: collapse;
  width: 100%;
  margin: 0;
  font-size: 13px;
}

.msg-content :deep(thead) {
  background: var(--chat-msg-table-head-bg);
  position: sticky;
  top: 0;
  z-index: 1;
}

.msg-content :deep(th) {
  padding: 10px 12px;
  font-weight: 600;
  text-align: left;
  border: 1px solid var(--chat-msg-table-border);
  white-space: nowrap;
}

.msg-content :deep(td) {
  padding: 8px 12px;
  border: 1px solid var(--chat-msg-table-border);
}

.msg-content :deep(tbody tr:hover) {
  background: rgba(0, 0, 0, 0.02);
}

.msg-content :deep(tbody tr:nth-child(even)) {
  background: rgba(0, 0, 0, 0.01);
}

.msg-content :deep(tbody tr:nth-child(even):hover) {
  background: rgba(0, 0, 0, 0.03);
}

.msg-content :deep(strong) {
  font-weight: 600;
}

/* 知识库图片（回答正文 + 引用文档面板共用） */
.msg-content :deep(img.kb-image),
.doc-panel-content :deep(img.kb-image) {
  max-width: 100%;
  height: auto;
  border-radius: 8px;
  margin: 8px 0;
  display: block;
  cursor: zoom-in;
  transition: opacity 0.2s;
}

/* 内联图片缺失占位 */
.msg-content :deep(.img-missing-inline),
.doc-panel-content :deep(.img-missing-inline) {
  display: inline-block;
  padding: 2px 8px;
  border: 1px dashed #d1d5db;
  border-radius: 4px;
  color: #9ca3af;
  font-size: 12px;
}

/* 思考区块 */
.think-block {
  margin: 0 0 16px;
  border-left: 1px solid var(--chat-think-border);
  overflow: hidden;
}

.think-header {
  padding: 0;
}

.think-toggle {
  width: 100%;
  border: 0;
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px 0 8px 14px;
  font-size: 14px;
  color: var(--chat-think-text);
  user-select: none;
  background: transparent;
  cursor: pointer;
  text-align: left;
}

.think-toggle:hover {
  color: var(--chat-msg-text);
}

.think-action {
  margin-left: 4px;
  color: var(--chat-think-action);
}

.think-arrow {
  transition: transform 0.2s;
}

.think-arrow.open {
  transform: rotate(180deg);
}

.think-body {
  padding: 4px 12px 12px 14px;
  font-size: 13px;
  color: var(--chat-think-body);
  line-height: 1.75;
  white-space: pre-wrap;
  overflow-y: visible;
}

.source-list {
  margin-top: 20px;
  padding: 12px 14px;
  border-radius: 10px;
  background: var(--chat-source-bg);
  border: 1px solid var(--chat-source-border);
}

.source-title {
  margin-bottom: 4px;
  color: var(--chat-source-text);
  font-size: 13px;
  font-weight: 600;
}

.source-card {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 0;
  margin: 0;
  border: 0;
  border-top: 1px solid var(--chat-source-border);
  color: var(--chat-source-text);
}

.source-card:first-of-type {
  border-top: 0;
}

.source-index {
  display: grid;
  place-items: center;
  flex: 0 0 20px;
  width: 20px;
  height: 20px;
  border-radius: 50%;
  color: var(--chat-source-index-text);
  background: var(--chat-source-index-bg);
  font-size: 11px;
}

.source-detail {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 3px;
  border: 0;
  padding: 0;
  background: transparent;
  color: inherit;
  text-align: left;
  cursor: pointer;
}

.source-detail strong,
.source-detail small {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.source-detail strong {
  font-size: 12px;
  font-weight: 600;
}

.source-detail small {
  font-size: 11px;
  color: var(--chat-source-muted);
}

.source-open {
  margin-left: auto;
  border: 0;
  padding: 4px;
  background: transparent;
  color: var(--chat-source-link);
  font-size: 12px;
  cursor: pointer;
  white-space: nowrap;
}

@media (max-width: 640px) {
  .chat-messages {
    padding: 28px 16px 16px;
  }

  .message-row {
    margin-bottom: 20px;
  }

  .message-body {
    max-width: 100%;
  }

  .source-card {
    align-items: flex-start;
  }

  .source-open {
    display: none;
  }
}

/* ── 引用序号标记（正文中的 ①②③） ───────────────────────── */
.msg-content :deep(.ref-link.ref-seq) {
  display: inline-block;
  margin: 0 1px;
  padding: 0 1px;
  font-size: 15px;
  font-weight: 600;
  line-height: 1;
  color: #2563eb;
  text-decoration: none;
  cursor: pointer;
  vertical-align: baseline;
  transition: transform 0.15s;
}

.msg-content :deep(.ref-link.ref-seq:hover) {
  transform: scale(1.2);
}

/* ── 参考来源独立区域 ──────────────────────────────────────── */
.msg-sources {
  margin-top: 8px;
  padding-top: 6px;
  border-top: 1px dashed #e5e7eb;
}

/* ── 参考来源行（管道符包裹的灰色文本） ────────────────────── */
.msg-content :deep(.ref-source-line),
.msg-sources :deep(.ref-source-line) {
  display: block;
  margin: 2px 0;
  font-size: 13px;
  line-height: 1.5;
  color: #9ca3af;
}

.msg-content :deep(.ref-source-line .ref-link.ref-source-doc),
.msg-content :deep(.ref-source-line .ref-link.ref-source-section),
.msg-sources :deep(.ref-source-line .ref-link.ref-source-doc),
.msg-sources :deep(.ref-source-line .ref-link.ref-source-section) {
  display: inline;
  color: #6b7280;
  font-size: inherit;
  font-weight: 500;
  text-decoration: none;
  border-bottom: 1px dashed #6b7280;
  cursor: pointer;
  padding: 1px 0;
  transition: all 0.15s;
}

.msg-content :deep(.ref-source-line .ref-link.ref-source-doc:hover),
.msg-content :deep(.ref-source-line .ref-link.ref-source-section:hover),
.msg-sources :deep(.ref-source-line .ref-link.ref-source-doc:hover),
.msg-sources :deep(.ref-source-line .ref-link.ref-source-section:hover) {
  color: #2563eb;
  background: #eff6ff;
  border-radius: 3px;
  border-bottom-color: #2563eb;
}

/* ── 参考来源行的 ①②③ 序号 ─────────────────────────────── */
.msg-content :deep(.ref-source-line .ref-source-num),
.msg-sources :deep(.ref-source-line .ref-source-num) {
  color: #2563eb;
  font-weight: 600;
  margin-right: 2px;
  font-size: inherit;
}

/* ── 引用浮框 Tooltip ──────────────────────────────────────── */
.ref-tooltip {
  position: fixed;
  z-index: 9999;
  max-width: 360px;
  padding: 12px 14px;
  background: #fff;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.12);
  transform: translate(-50%, -100%);
  pointer-events: auto;
  animation: tooltipIn 0.15s ease;
}

@keyframes tooltipIn {
  from {
    opacity: 0;
    transform: translate(-50%, calc(-100% + 6px));
  }

  to {
    opacity: 1;
    transform: translate(-50%, -100%);
  }
}

.ref-tooltip-title {
  font-size: 13px;
  font-weight: 600;
  color: #1f2937;
  margin-bottom: 4px;
}

.ref-tooltip-source {
  font-size: 11px;
  color: #9ca3af;
  margin-bottom: 6px;
}

.ref-tooltip-excerpt {
  font-size: 12px;
  color: #6b7280;
  line-height: 1.55;
  max-height: 160px;
  overflow-y: auto;
}

.ref-tooltip-excerpt :deep(p) {
  margin: 3px 0;
}

.ref-tooltip-excerpt :deep(ul),
.ref-tooltip-excerpt :deep(ol) {
  padding-left: 16px;
  margin: 3px 0;
}

.ref-tooltip-excerpt :deep(strong) {
  font-weight: 600;
  color: #4b5563;
}

.ref-tooltip-excerpt :deep(code) {
  background: #f3f4f6;
  padding: 1px 4px;
  border-radius: 2px;
  font-size: 11px;
}

/* ── 右侧文档预览面板 ──────────────────────────────────────── */
.doc-panel-overlay {
  position: fixed;
  inset: 0;
  z-index: 9990;
  background: rgba(0, 0, 0, 0.15);
  animation: overlayIn 0.2s ease;
}

@keyframes overlayIn {
  from {
    opacity: 0;
  }

  to {
    opacity: 1;
  }
}

.doc-panel {
  position: fixed;
  top: 0;
  right: 0;
  width: 30%;
  min-width: 380px;
  max-width: 600px;
  height: 100vh;
  z-index: 9991;
  background: #fff;
  border-left: 1px solid #e5e7eb;
  box-shadow: -4px 0 24px rgba(0, 0, 0, 0.1);
  display: flex;
  flex-direction: column;
  animation: panelIn 0.25s ease;
}

@keyframes panelIn {
  from {
    transform: translateX(100%);
  }

  to {
    transform: translateX(0);
  }
}

.doc-panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 18px;
  border-bottom: 1px solid #f0f0f0;
  flex-shrink: 0;
}

.doc-panel-title {
  font-size: 15px;
  font-weight: 600;
  color: #1f2937;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  flex: 1;
  margin-right: 12px;
}

.doc-panel-close {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  border: 0;
  background: transparent;
  color: #9ca3af;
  border-radius: 6px;
  cursor: pointer;
  flex-shrink: 0;
  transition: all 0.15s;
}

.doc-panel-close:hover {
  background: #f3f4f6;
  color: #374151;
}

.doc-panel-body {
  flex: 1;
  overflow-y: auto;
  padding: 18px;
}

.doc-panel-spinner {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
}

.spinner {
  width: 32px;
  height: 32px;
  border: 3px solid #e5e7eb;
  border-top-color: #2563eb;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

.doc-panel-error {
  color: #ef4444;
  font-size: 13px;
  padding: 16px;
  text-align: center;
}

.doc-panel-content {
  font-size: 14px;
  line-height: 1.75;
  color: #374151;
}

.doc-panel-content :deep(h1),
.doc-panel-content :deep(h2),
.doc-panel-content :deep(h3) {
  margin: 16px 0 8px;
  font-weight: 600;
  color: #1f2937;
}

.doc-panel-content :deep(h1) {
  font-size: 18px;
}

.doc-panel-content :deep(h2) {
  font-size: 16px;
}

.doc-panel-content :deep(h3) {
  font-size: 14px;
}

.doc-panel-content :deep(p) {
  margin: 4px 0;
}

.doc-panel-content :deep(ul),
.doc-panel-content :deep(ol) {
  padding-left: 20px;
  margin: 6px 0;
}

.doc-panel-content :deep(table) {
  width: 100%;
  border-collapse: collapse;
  margin: 10px 0;
  font-size: 13px;
}

.doc-panel-content :deep(th),
.doc-panel-content :deep(td) {
  border: 1px solid #e5e7eb;
  padding: 8px 10px;
  text-align: left;
}

.doc-panel-content :deep(th) {
  background: #f9fafb;
  font-weight: 600;
}

.doc-panel-content :deep(pre) {
  background: #f9fafb;
  border: 1px solid #e5e7eb;
  border-radius: 6px;
  padding: 12px;
  overflow-x: auto;
  font-size: 12px;
}

.doc-panel-content :deep(code) {
  background: #f3f4f6;
  padding: 1px 5px;
  border-radius: 3px;
  font-size: 12px;
}

.doc-panel-content :deep(pre code) {
  background: transparent;
  padding: 0;
}

/* 锚点定位高亮 */
.doc-panel-content :deep(.doc-anchor-highlight) {
  animation: anchorFlash 1.5s ease;
}

@keyframes anchorFlash {

  0%,
  100% {
    background: transparent;
  }

  30% {
    background: #fef3c7;
  }
}

/* 消息操作按钮 */
.message-actions {
  display: flex;
  gap: 4px;
  margin-top: 10px;
  opacity: 0.7;
  transition: opacity 0.2s;
}

.message-row:hover .message-actions {
  opacity: 1;
}

.action-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  padding: 0;
  color: var(--chat-copy-text);
  background: transparent;
  border: 0;
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.15s;
}

.action-btn:hover {
  background: var(--chat-copy-hover-bg);
  color: var(--chat-copy-hover-text);
}

.action-btn.active {
  color: #2563eb;
  background: #eff6ff;
}

.action-btn svg {
  flex-shrink: 0;
}

/* ── 消息内联编辑（编辑框覆盖在原气泡上，参照 DeepSeek） ──── */
.msg-edit {
  width: 100%;
  min-width: 240px;
  background: var(--chat-input-bg);
  border: 1px solid var(--chat-input-focus-border);
  border-radius: 14px;
  padding: 10px 14px;
  box-shadow: 0 0 0 3px var(--chat-input-focus-ring);
}

.msg-edit-textarea {
  width: 100%;
  border: none;
  outline: none;
  resize: none;
  background: transparent;
  color: var(--chat-input-text);
  font-size: 14px;
  line-height: 1.8;
  font-family: inherit;
  max-height: 40vh;
  overflow-y: auto;
}

.msg-edit-textarea::placeholder {
  color: var(--chat-input-placeholder);
}

.msg-edit-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 8px;
}

.msg-edit-btn {
  padding: 6px 16px;
  border-radius: 8px;
  border: 1px solid var(--chat-input-action-border);
  background: var(--chat-input-action-bg);
  color: var(--chat-input-action-text);
  font-size: 13px;
  cursor: pointer;
  transition: all 0.15s;
}

.msg-edit-btn:hover:not(:disabled) {
  background: var(--chat-input-action-hover-bg);
  color: var(--chat-input-action-hover-text);
}

.msg-edit-btn.primary {
  background: var(--chat-input-send-active-bg);
  border-color: var(--chat-input-send-active-border);
  color: #fff;
}

.msg-edit-btn.primary:hover:not(:disabled) {
  filter: brightness(1.05);
}

.msg-edit-btn.primary:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* ── 消息版本切换（‹ 1/2 ›，参照 DeepSeek） ───────────────── */
.msg-version-nav {
  display: inline-flex;
  align-items: center;
  gap: 2px;
  margin-top: 6px;
  padding: 2px 6px;
  border: 1px solid var(--chat-input-action-border);
  border-radius: 10px;
  background: var(--chat-input-action-bg);
}

.ver-btn {
  width: 22px;
  height: 22px;
  border: none;
  background: transparent;
  color: var(--chat-input-action-text);
  border-radius: 6px;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 15px;
  line-height: 1;
  transition: all 0.15s;
}

.ver-btn:hover:not(:disabled) {
  background: var(--chat-input-action-hover-bg);
  color: var(--chat-input-action-hover-text);
}

.ver-btn:disabled {
  opacity: 0.35;
  cursor: default;
}

.ver-count {
  font-size: 12px;
  color: var(--chat-copy-text);
  min-width: 36px;
  text-align: center;
  user-select: none;
}
</style>