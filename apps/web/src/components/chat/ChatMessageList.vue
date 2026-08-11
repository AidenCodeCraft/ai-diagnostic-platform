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
          <!-- AI 思考过程 -->
          <div v-if="msg.role === 'assistant' && msg.thinking && (msg.thinking.text || msg.thinking.active)" class="think-block">
            <div class="think-header">
              <button class="think-toggle" @click="toggleThink(msg)">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/></svg>
                <span>{{ msg.thinking.active ? '正在思考' : `已思考（用时 ${msg.thinking.elapsed || 1} 秒）` }}</span>
                <span class="think-action">{{ msg._thinkOpen ? '收起' : '展开' }}</span>
                <svg class="think-arrow" :class="{ open: msg._thinkOpen }" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="6 9 12 15 18 9"/></svg>
              </button>
            </div>
            <div v-show="msg._thinkOpen" class="think-body">{{ msg.thinking.text || '正在准备回答…' }}</div>
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
            <div class="msg-content" v-html="renderContent(msg.content, msg.files && msg.files.length > 0, msg.sources, msg.id)"></div>
          </div>
          <div v-if="msg.role === 'assistant' && msg.content && !msg.thinking?.active" class="message-actions">
            <button class="action-btn" :class="{ active: copiedId === msg.id }" @click="copyMessage(msg)" :title="copiedId === msg.id ? '已复制' : '复制回复'">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>
            </button>
            <button class="action-btn" @click="regenerateMessage(msg)" title="重新生成">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="23 4 23 10 17 10"/><polyline points="1 20 1 14 7 14"/><path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/></svg>
            </button>
            <button class="action-btn" :class="{ active: msg._liked }" @click="likeMessage(msg)" title="有帮助">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 9V5a3 3 0 0 0-3-3l-4 9v11h11.28a2 2 0 0 0 2-1.7l1.38-9a2 2 0 0 0-2-2.3zM7 22H4a2 2 0 0 1-2-2v-7a2 2 0 0 1 2-2h3"/></svg>
            </button>
            <button class="action-btn" :class="{ active: msg._disliked }" @click="dislikeMessage(msg)" title="无帮助">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M10 15v4a3 3 0 0 0 3 3l4-9V2H5.72a2 2 0 0 0-2 1.7l-1.38 9a2 2 0 0 0 2 2.3zm7-13h2.67A2.31 2.31 0 0 1 22 4v7a2.31 2.31 0 0 1-2.33 2H17"/></svg>
            </button>
          </div>
          <div v-else-if="msg.role === 'user' && msg.content" class="message-actions">
            <button class="action-btn" @click="editMessage(msg)" title="编辑">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M17 3a2.83 2.83 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5Z"/></svg>
            </button>
            <button class="action-btn" @click="copyMessage(msg)" title="复制">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>
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
      <div
        v-if="tooltip.visible"
        class="ref-tooltip"
        :style="{ top: tooltip.y + 'px', left: tooltip.x + 'px' }"
        @mouseenter="cancelTooltipHide"
        @mouseleave="scheduleTooltipHide"
      >
        <div class="ref-tooltip-title">{{ tooltip.title }}</div>
        <div class="ref-tooltip-source">{{ tooltip.source }}</div>
        <div class="ref-tooltip-excerpt">{{ tooltip.excerpt }}</div>
      </div>
    </Teleport>

    <!-- 右侧文档预览面板 -->
    <Teleport to="body">
      <div v-if="docPanel.visible" class="doc-panel-overlay" @click="closeDocPanel"></div>
      <div v-if="docPanel.visible" class="doc-panel" :class="{ 'doc-panel-loading': docPanel.loading }">
        <div class="doc-panel-header">
          <span class="doc-panel-title">{{ docPanel.title }}</span>
          <button class="doc-panel-close" @click="closeDocPanel" title="关闭">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
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
import { ref, computed, watch, nextTick, onMounted, onBeforeUnmount, reactive } from 'vue'
import { renderMarkdown } from '@/utils/markdown'
import { useFormat } from '@/composables/useFormat'
import { chatApi, type ChatSource } from '@/api/chat'
import { knowledgeApi } from '@/api/knowledge'

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
  (e: 'editMessage', msg: any): void
}>()

// ── 引用文档 Tooltip ──────────────────────────────────────────
const tooltip = reactive({
  visible: false,
  x: 0,
  y: 0,
  title: '',
  source: '',
  excerpt: '',
})
let tooltipTimer: ReturnType<typeof setTimeout> | null = null

// ── 右侧文档预览面板 ──────────────────────────────────────────
const docPanel = reactive({
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

// 鼠标事件处理：通过 data 属性获取引用信息
function handleRefMouseEnter(e: MouseEvent) {
  const target = e.target as HTMLElement
  if (!target.classList.contains('ref-link')) return
  const title = target.getAttribute('data-title') || ''
  const source = target.getAttribute('data-source') || '知识库'
  const excerpt = target.getAttribute('data-excerpt') || ''
  if (!title && !excerpt) return

  const rect = target.getBoundingClientRect()
  tooltip.title = title
  tooltip.source = source
  tooltip.excerpt = excerpt
  // 定位在链接上方
  tooltip.x = rect.left + rect.width / 2
  tooltip.y = rect.top - 8
  tooltip.visible = true
  cancelTooltipHide()
}

function handleRefMouseLeave(_e: MouseEvent) {
  scheduleTooltipHide()
}

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

async function handleRefClick(e: MouseEvent) {
  const target = e.target as HTMLElement
  if (!target.classList.contains('ref-link')) return
  e.preventDefault()

  const docIdStr = target.getAttribute('data-doc-id')
  const title = target.getAttribute('data-title') || ''
  const anchorId = target.getAttribute('data-anchor') || ''

  if (!docIdStr) return

  const docId = parseInt(docIdStr, 10)
  if (isNaN(docId)) return

  tooltip.visible = false
  openDocPanel(docId, title, anchorId)
}

async function openDocPanel(docId: number, title: string, anchorId: string) {
  docPanel.visible = true
  docPanel.title = title
  docPanel.anchorId = anchorId
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
  if (!docPanel.anchorId || !docPanelContentRef.value) return
  // 搜索锚点文本
  const body = docPanelContentRef.value
  const decoded = decodeURIComponent(docPanel.anchorId)
  // 尝试查找包含锚点文本的标题或段落
  const headings = body.querySelectorAll('h1, h2, h3, h4, h5, h6')
  for (const h of headings) {
    if (h.textContent?.includes(decoded)) {
      h.scrollIntoView({ behavior: 'smooth', block: 'start' })
      // 高亮效果
      h.classList.add('doc-anchor-highlight')
      setTimeout(() => h.classList.remove('doc-anchor-highlight'), 3000)
      return
    }
  }
  // 尝试在段落中查找
  const paragraphs = body.querySelectorAll('p, li, td, th')
  for (const p of paragraphs) {
    if (p.textContent?.includes(decoded)) {
      p.scrollIntoView({ behavior: 'smooth', block: 'center' })
      p.classList.add('doc-anchor-highlight')
      setTimeout(() => p.classList.remove('doc-anchor-highlight'), 3000)
      return
    }
  }
}

function closeDocPanel() {
  docPanel.visible = false
  docPanel.anchorId = ''
}

// 全局事件委托：处理 ref:// 链接的 hover 和 click
function onGlobalClick(e: Event) {
  const target = e.target as HTMLElement
  if (target.classList.contains('ref-link')) {
    handleRefClick(e as MouseEvent)
  }
}

function onGlobalMouseOver(e: Event) {
  const target = e.target as HTMLElement
  if (target.classList.contains('ref-link')) {
    handleRefMouseEnter(e as MouseEvent)
  }
}

function onGlobalMouseOut(e: Event) {
  const target = e.target as HTMLElement
  if (target.classList.contains('ref-link')) {
    handleRefMouseLeave(e as MouseEvent)
  }
}

onMounted(() => {
  document.addEventListener('click', onGlobalClick)
  document.addEventListener('mouseover', onGlobalMouseOver)
  document.addEventListener('mouseout', onGlobalMouseOut)
})

onBeforeUnmount(() => {
  document.removeEventListener('click', onGlobalClick)
  document.removeEventListener('mouseover', onGlobalMouseOver)
  document.removeEventListener('mouseout', onGlobalMouseOut)
  cancelTooltipHide()
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

function renderContent(text: string, hasFiles?: boolean, sources: any[] = [], messageId?: string | number): string {
  let display = text
  if (hasFiles) {
    display = display.replace(/\n?\[上传文件:.*?\]/g, '')
  }
  try {
    const content = renderMarkdown(display)
    return processRefLinks(content, sources)
  } catch {
    return display.replace(/\n/g, '<br>')
  }
}

/**
 * 将 Markdown 中 ref:// 协议的链接转换为可点击的引用链接。
 * 支持格式：
 *   [来源：《文档标题》](ref://123)
 *   [来源：《文档标题》— 关键字解释表](ref://123#关键字解释表)
 */
function processRefLinks(html: string, sources: any[]): string {
  // 构建 sources 映射表 (title -> source info)
  const sourceMap = new Map<string, { id: number; excerpt: string; source: string }>()
  for (const s of sources) {
    if (s.id && s.title) {
      sourceMap.set(s.title, {
        id: s.id,
        excerpt: s.excerpt || '',
        source: s.source || '知识库',
      })
    }
  }

  // 替换 ref:// 协议的链接
  return html.replace(
    /<a\s+href="ref:\/\/(\d+)(?:#([^"]*))?"[^>]*>(.*?)<\/a>/gi,
    (_match, docId: string, anchor: string, text: string) => {
      // 从文本中提取标题（去掉"来源："前缀）
      const displayTitle = text.replace(/^来源：/, '').replace(/^来源:/, '')
      // 查找对应的 source 信息
      let excerpt = ''
      let sourceLabel = '知识库'
      // 尝试用 displayTitle 中的文档标题部分匹配
      for (const [title, info] of sourceMap) {
        if (displayTitle.includes(title) || title.includes(displayTitle.replace(/—.*$/, '').trim())) {
          excerpt = info.excerpt
          sourceLabel = info.source
          break
        }
      }
      // 如果没匹配到，取第一个匹配的 source
      if (!excerpt && sourceMap.size > 0) {
        const first = sourceMap.values().next().value
        if (first) {
          excerpt = first.excerpt
          sourceLabel = first.source
        }
      }

      const anchorAttr = anchor ? ` data-anchor="${escapeAttr(anchor)}"` : ''
      const excerptAttr = excerpt ? ` data-excerpt="${escapeAttr(excerpt)}"` : ''
      return `<a class="ref-link" data-doc-id="${escapeAttr(docId)}" data-title="${escapeAttr(displayTitle)}" data-source="${escapeAttr(sourceLabel)}"${excerptAttr}${anchorAttr} href="javascript:void(0)" title="点击查看文档">${text}</a>`
    },
  )

  // 不再添加 "相关参考：" 汇总行和 "参考出处" 列表
}

function escapeAttr(value: string): string {
  return value
    .replace(/&/g, '&amp;')
    .replace(/"/g, '&quot;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/'/g, '&#39;')
}

// Auto-scroll when new messages arrive
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

// 展开/折叠思考区块
function toggleThink(msg: any) {
  msg._thinkOpen = !msg._thinkOpen
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

function editMessage(msg: any) {
  emit('editMessage', msg)
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
.think-toggle:hover { color: var(--chat-msg-text); }
.think-action { margin-left: 4px; color: var(--chat-think-action); }
.think-arrow { transition: transform 0.2s; }
.think-arrow.open { transform: rotate(180deg); }
.think-body {
  padding: 4px 12px 8px 14px;
  font-size: 13px;
  color: var(--chat-think-body);
  line-height: 1.75;
  white-space: pre-wrap;
  max-height: 200px;
  overflow-y: auto;
}

.source-list { margin-top: 20px; padding: 12px 14px; border-radius: 10px; background: var(--chat-source-bg); border: 1px solid var(--chat-source-border); }
.source-title { margin-bottom: 4px; color: var(--chat-source-text); font-size: 13px; font-weight: 600; }
.source-card { display: flex; align-items: center; gap: 10px; padding: 10px 0; margin: 0; border: 0; border-top: 1px solid var(--chat-source-border); color: var(--chat-source-text); }
.source-card:first-of-type { border-top: 0; }
.source-index { display: grid; place-items: center; flex: 0 0 20px; width: 20px; height: 20px; border-radius: 50%; color: var(--chat-source-index-text); background: var(--chat-source-index-bg); font-size: 11px; }
.source-detail { min-width: 0; display: flex; flex-direction: column; gap: 3px; border: 0; padding: 0; background: transparent; color: inherit; text-align: left; cursor: pointer; }
.source-detail strong, .source-detail small { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.source-detail strong { font-size: 12px; font-weight: 600; }
.source-detail small { font-size: 11px; color: var(--chat-source-muted); }
.source-open { margin-left: auto; border: 0; padding: 4px; background: transparent; color: var(--chat-source-link); font-size: 12px; cursor: pointer; white-space: nowrap; }

@media (max-width: 640px) {
  .chat-messages { padding: 28px 16px 16px; }
  .message-row { margin-bottom: 20px; }
  .message-body { max-width: 100%; }
  .source-card { align-items: flex-start; }
  .source-open { display: none; }
}

/* ── 引用文档链接 ──────────────────────────────────────────── */
.msg-content :deep(.ref-link) {
  display: inline;
  color: #2563eb;
  font-size: 12px;
  font-weight: 500;
  text-decoration: none;
  border-bottom: 1px dashed #2563eb;
  cursor: pointer;
  padding: 1px 2px;
  transition: all 0.15s;
  white-space: nowrap;
}
.msg-content :deep(.ref-link:hover) {
  color: #1d4ed8;
  background: #eff6ff;
  border-radius: 3px;
  border-bottom-color: #1d4ed8;
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
  from { opacity: 0; transform: translate(-50%, calc(-100% + 6px)); }
  to   { opacity: 1; transform: translate(-50%, -100%); }
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
  max-height: 120px;
  overflow: hidden;
  display: -webkit-box;
  -webkit-line-clamp: 5;
  -webkit-box-orient: vertical;
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
  from { opacity: 0; }
  to   { opacity: 1; }
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
  from { transform: translateX(100%); }
  to   { transform: translateX(0); }
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
.doc-panel-loading {
  /* no extra style needed */;
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
  to { transform: rotate(360deg); }
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
.doc-panel-content :deep(h1) { font-size: 18px; }
.doc-panel-content :deep(h2) { font-size: 16px; }
.doc-panel-content :deep(h3) { font-size: 14px; }
.doc-panel-content :deep(p) { margin: 4px 0; }
.doc-panel-content :deep(ul),
.doc-panel-content :deep(ol) { padding-left: 20px; margin: 6px 0; }
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
  0%, 100% { background: transparent; }
  30% { background: #fef3c7; }
}

/* 消息操作按钮 */
.message-actions { display: flex; gap: 4px; margin-top: 10px; opacity: 0.7; transition: opacity 0.2s; }
.message-row:hover .message-actions { opacity: 1; }
.action-btn { display: inline-flex; align-items: center; justify-content: center; width: 28px; height: 28px; padding: 0; color: var(--chat-copy-text); background: transparent; border: 0; border-radius: 6px; cursor: pointer; transition: all 0.15s; }
.action-btn:hover { background: var(--chat-copy-hover-bg); color: var(--chat-copy-hover-text); }
.action-btn.active { color: #2563eb; background: #eff6ff; }
.action-btn svg { flex-shrink: 0; }
</style>
