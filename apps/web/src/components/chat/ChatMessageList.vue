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
          <div v-if="msg.role === 'assistant' && msg.sources?.length" class="source-list">
            <div class="source-title">参考出处</div>
            <blockquote v-for="(source, index) in msg.sources" :id="sourceTarget(index, msg.id)" :key="`${source.id || source.title}-${index}`" class="source-card">
              <span class="source-index">{{ index + 1 }}</span>
              <button class="source-detail" @click="$emit('openKnowledge', source)">
                <strong>{{ source.title }}</strong>
                <small>{{ source.source }}<template v-if="source.excerpt"> · {{ source.excerpt }}</template></small>
              </button>
              <button class="source-open" @click="$emit('openKnowledge', source)">查看来源 ↗</button>
            </blockquote>
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
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, nextTick } from 'vue'
import { renderMarkdown } from '@/utils/markdown'
import { useFormat } from '@/composables/useFormat'

const { formatFileSize, fileIcon } = useFormat()

const props = defineProps<{
  messages: any[]
  loading: boolean
  isEmpty?: boolean
}>()

const emit = defineEmits<{
  (e: 'previewFile', file: { name: string; size: number; type: string }): void
  (e: 'openKnowledge', source: { id?: number; title: string }): void
  (e: 'regenerate', msg: any): void
  (e: 'editMessage', msg: any): void
}>()

// 按 createdAt 升序排列
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
    return addInlineCitations(content, sources, messageId)
  } catch {
    return display.replace(/\n/g, '<br>')
  }
}

function escapeRegExp(value: string) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}

function escapeHtml(value: string) {
  return value.replace(/[&<>'"]/g, (character) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;' })[character] || character)
}

function sourceTarget(index: number, messageId?: string | number) {
  return `reference-${messageId ?? 'message'}-${index + 1}`
}

function addInlineCitations(content: string, sources: any[], messageId?: string | number) {
  if (!sources?.length) return content

  let output = content
  const unlinked: number[] = []

  sources.forEach((source, index) => {
    const label = `[${index + 1}]`
    const title = escapeHtml(String(source.title || '参考出处'))
    const reference = `<a class="inline-citation" href="#${sourceTarget(index, messageId)}" title="查看出处：${title}">${label}</a>`
    const matchText = [source.title, source.excerpt]
      .filter((value: string | undefined) => value && value.length > 4)
      .sort((left: string, right: string) => right.length - left.length)[0]

    if (matchText && !output.includes(reference)) {
      const matcher = new RegExp(escapeRegExp(matchText), 'i')
      if (matcher.test(output)) {
        output = output.replace(matcher, (value) => `${value}${reference}`)
        return
      }
    }
    unlinked.push(index)
  })

  if (unlinked.length) {
    const references = unlinked
      .map((index) => `<a class="inline-citation" href="#${sourceTarget(index, messageId)}" title="查看出处：${escapeHtml(String(sources[index].title || '参考出处'))}">[${index + 1}]</a>`)
      .join('')
    output += `<p class="citation-summary">相关参考：${references}</p>`
  }

  return output
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
  msg._liked = !msg._liked
  if (msg._liked) msg._disliked = false
  // TODO: 后端持久化点赞状态
}

function dislikeMessage(msg: any) {
  msg._disliked = !msg._disliked
  if (msg._disliked) msg._liked = false
  // TODO: 后端持久化点踩状态
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
.message-actions { display: flex; gap: 4px; margin-top: 10px; opacity: 0.7; transition: opacity 0.2s; }
.message-row:hover .message-actions { opacity: 1; }
.action-btn { display: inline-flex; align-items: center; justify-content: center; width: 28px; height: 28px; padding: 0; color: var(--chat-copy-text); background: transparent; border: 0; border-radius: 6px; cursor: pointer; transition: all 0.15s; }
.action-btn:hover { background: var(--chat-copy-hover-bg); color: var(--chat-copy-hover-text); }
.action-btn.active { color: #2563eb; background: #eff6ff; }
.action-btn svg { flex-shrink: 0; }

.msg-content :deep(.inline-citation) { display: inline-flex; align-items: center; justify-content: center; min-width: 19px; height: 19px; margin-left: 3px; padding: 0 4px; border-radius: 5px; background: var(--chat-citation-bg); color: var(--chat-citation-text); font-size: 11px; font-weight: 600; line-height: 1; text-decoration: none; vertical-align: middle; }
.msg-content :deep(.inline-citation:hover) { background: var(--chat-citation-hover-bg); color: var(--chat-citation-hover-text); }
.msg-content :deep(.citation-summary) { margin-top: 12px; color: var(--chat-source-muted); font-size: 13px; }

@media (max-width: 640px) {
  .chat-messages { padding: 28px 16px 16px; }
  .message-row { margin-bottom: 20px; }
  .message-body { max-width: 100%; }
  .source-card { align-items: flex-start; }
  .source-open { display: none; }
}
</style>
