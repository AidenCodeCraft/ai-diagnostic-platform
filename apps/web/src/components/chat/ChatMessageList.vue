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
        <div class="message-avatar" v-if="msg.role === 'assistant'">
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#2563eb" stroke-width="1.5">
            <circle cx="12" cy="12" r="10" />
            <path d="M8 14s1.5 2 4 2 4-2 4-2" />
          </svg>
        </div>
        <div class="message-body">
          <!-- AI 思考过程 -->
          <div v-if="msg.role === 'assistant' && msg.thinking" class="think-block">
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
            <div class="msg-content" v-html="renderContent(msg.content, msg.files && msg.files.length > 0)"></div>
          </div>
          <div v-if="msg.role === 'assistant' && msg.sources?.length" class="source-list">
            <div class="source-title">引用来源</div>
            <button v-for="(source, index) in msg.sources" :key="`${source.id || source.title}-${index}`" class="source-card" @click="$emit('openKnowledge', source)">
              <span class="source-index">{{ index + 1 }}</span>
              <span class="source-detail"><strong>{{ source.title }}</strong><small>{{ source.source }}<template v-if="source.excerpt"> · {{ source.excerpt }}</template></small></span>
              <span class="source-open">查看</span>
            </button>
          </div>
          <div v-if="msg.role === 'assistant' && msg.content" class="message-actions">
            <button class="copy-button" :class="{ copied: copiedId === msg.id }" @click="copyMessage(msg)">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>
              {{ copiedId === msg.id ? '已复制' : '复制' }}
            </button>
          </div>
        </div>
        <div class="message-avatar" v-if="msg.role === 'user'">
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#6b7280" stroke-width="1.5">
            <circle cx="12" cy="8" r="4" />
            <path d="M4 20c0-4 4-7 8-7s8 3 8 7" />
          </svg>
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
import { marked } from 'marked'
import { useFormat } from '@/composables/useFormat'

const { formatFileSize, fileIcon } = useFormat()

const props = defineProps<{
  messages: any[]
  loading: boolean
  isEmpty?: boolean
}>()

defineEmits<{
  (e: 'previewFile', file: { name: string; size: number; type: string }): void
  (e: 'openKnowledge', source: { id?: number; title: string }): void
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

function renderContent(text: string, hasFiles?: boolean): string {
  let display = text
  if (hasFiles) {
    display = display.replace(/\n?\[上传文件:.*?\]/g, '')
  }
  try {
    return marked.parse(display) as string
  } catch {
    return display.replace(/\n/g, '<br>')
  }
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
  padding: 24px;
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
  max-width: 768px;
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
  color: #374151;
  margin: 0;
}

.message-row {
  display: flex;
  gap: 10px;
  margin-bottom: 24px;
  width: 100%;
  max-width: 768px;
}

.message-row.user {
  justify-content: flex-end;
}

.message-row.assistant {
  justify-content: flex-start;
}

.message-avatar {
  flex-shrink: 0;
  width: 30px;
  height: 30px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.message-body {
  max-width: 85%;
}

.message-bubble {
  padding: 12px 16px;
  border-radius: 12px;
  line-height: 1.65;
  font-size: 14px;
  color: #1f2937;
}

.message-row.user .message-bubble {
  background: #eff6ff;
  border: 1px solid #bfdbfe;
  border-bottom-right-radius: 4px;
}

.message-row.assistant .message-bubble {
  background: #fff;
  border: 1px solid #e5e7eb;
  border-bottom-left-radius: 4px;
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
  background: #eff6ff;
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

.msg-content :deep(code) {
  background: #f3f4f6;
  padding: 1px 5px;
  border-radius: 3px;
  font-size: 13px;
}

.msg-content :deep(pre) {
  background: #1e293b;
  color: #e2e8f0;
  padding: 10px 14px;
  border-radius: 6px;
  overflow-x: auto;
  margin: 6px 0;
}

.msg-content :deep(pre code) {
  background: none;
  padding: 0;
  color: inherit;
}

.msg-content :deep(blockquote) {
  border-left: 3px solid #d1d5db;
  padding-left: 10px;
  color: #6b7280;
  margin: 6px 0;
}

.msg-content :deep(table) {
  border-collapse: collapse;
  width: 100%;
  margin: 6px 0;
}

.msg-content :deep(th),
.msg-content :deep(td) {
  border: 1px solid #d1d5db;
  padding: 6px 10px;
  font-size: 13px;
}

.msg-content :deep(th) {
  background: #f3f4f6;
  font-weight: 600;
}

.msg-content :deep(strong) {
  font-weight: 600;
}

/* 思考区块 */
.think-block {
  margin-bottom: 6px;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  overflow: hidden;
  background: #f9fafb;
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
  padding: 7px 12px;
  font-size: 12px;
  color: #6b7280;
  user-select: none;
  background: transparent;
  cursor: pointer;
  text-align: left;
}
.think-toggle:hover { background: #f3f4f6; }
.think-action { margin-left: auto; color: #2563eb; }
.think-arrow { transition: transform 0.2s; }
.think-arrow.open { transform: rotate(180deg); }
.think-body {
  padding: 8px 12px 10px;
  font-size: 12px;
  color: #9ca3af;
  line-height: 1.5;
  border-top: 1px solid #e5e7eb;
  white-space: pre-wrap;
  max-height: 200px;
  overflow-y: auto;
}

.source-list { margin-top: 10px; border: 1px solid #dbeafe; border-radius: 8px; overflow: hidden; }
.source-title { padding: 7px 10px; color: #1d4ed8; background: #eff6ff; font-size: 12px; font-weight: 600; }
.source-card { width: 100%; display: flex; align-items: center; gap: 8px; padding: 8px 10px; border: 0; border-top: 1px solid #dbeafe; background: #fff; cursor: pointer; text-align: left; color: #374151; }
.source-card:hover { background: #f8fbff; }
.source-index { display: grid; place-items: center; flex: 0 0 18px; width: 18px; height: 18px; border-radius: 50%; color: #fff; background: #3b82f6; font-size: 11px; }
.source-detail { min-width: 0; display: flex; flex-direction: column; gap: 2px; }
.source-detail strong, .source-detail small { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.source-detail strong { font-size: 12px; font-weight: 600; }
.source-detail small { font-size: 11px; color: #6b7280; }
.source-open { margin-left: auto; color: #2563eb; font-size: 12px; }
.message-actions { display: flex; margin-top: 6px; }
.copy-button { display: inline-flex; align-items: center; gap: 4px; padding: 4px 7px; color: #6b7280; background: transparent; border: 0; border-radius: 5px; font-size: 12px; cursor: pointer; }
.copy-button:hover { background: #f3f4f6; color: #374151; }
.copy-button.copied { color: #16a34a; }
</style>
