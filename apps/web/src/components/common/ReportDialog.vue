<template>
  <teleport to="body">
    <div v-if="visible" class="menu-overlay" @click="$emit('close')"></div>
    <transition name="report-modal">
      <div v-if="visible" class="report-dialog">
        <div class="report-header">
          <div>
            <h3>生成诊断报告</h3>
            <p class="report-subtitle">选择需要包含在报告中的对话消息</p>
          </div>
          <button class="report-close" @click="$emit('close')">&times;</button>
        </div>

        <!-- 快捷操作栏 -->
        <div class="report-toolbar">
          <button class="toolbar-btn" @click="selectAll">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="9 11 12 14 22 4"/><path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"/></svg>
            全选
          </button>
          <button class="toolbar-btn" @click="deselectAll">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
            取消全选
          </button>
          <button class="toolbar-btn" @click="selectUserOnly">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>
            仅选用户消息
          </button>
          <button class="toolbar-btn" @click="selectAssistantOnly">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 2a10 10 0 1 0 10 10A10 10 0 0 0 12 2z"/><path d="M8 12h8"/><path d="M12 8v8"/></svg>
            仅选AI回复
          </button>
          <span class="toolbar-count">{{ selectedCount }} / {{ messages.length }} 条已选</span>
        </div>

        <!-- 消息列表 -->
        <div class="report-message-list" v-if="messages.length > 0">
          <div
            v-for="msg in messages"
            :key="msg.id"
            class="report-msg-item"
            :class="{ selected: selectedIds.has(msg.id) }"
            @click="toggle(msg.id)"
          >
            <div class="msg-check">
              <div class="check-box" :class="{ checked: selectedIds.has(msg.id) }">
                <svg v-if="selectedIds.has(msg.id)" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3"><polyline points="20 6 9 17 4 12"/></svg>
              </div>
            </div>
            <div class="msg-body">
              <div class="msg-meta">
                <span class="msg-role" :class="msg.role">{{ msg.role === 'user' ? '👤 用户' : '🤖 AI助手' }}</span>
                <span class="msg-time">{{ formatMsgTime(msg.createdAt) }}</span>
              </div>
              <div class="msg-preview">{{ truncate(msg.content, 120) }}</div>
            </div>
          </div>
        </div>

        <!-- 空状态 -->
        <div v-else class="report-empty">
          <div class="empty-icon">📋</div>
          <div>当前对话暂无消息</div>
        </div>

        <!-- 底部操作 -->
        <div class="report-footer">
          <el-button @click="$emit('close')">取消</el-button>
          <div class="report-footer-right">
            <el-button :disabled="selectedCount === 0" @click="generate('markdown')">
              Markdown ({{ selectedCount }} 条)
            </el-button>
            <el-button type="primary" :disabled="selectedCount === 0" @click="generate('pdf')">
              PDF ({{ selectedCount }} 条)
            </el-button>
          </div>
        </div>
      </div>
    </transition>
  </teleport>
</template>

<script setup lang="ts">
import { ref, watch, computed } from 'vue'
import { ElButton, ElMessage } from 'element-plus'

interface SelectableMessage {
  id: string
  role: string
  content: string
  createdAt: number
}

const props = defineProps<{
  visible: boolean
  messages: SelectableMessage[]
  chatTitle: string
  model: string
}>()

const emit = defineEmits<{
  (e: 'close'): void
  (e: 'generate', selectedIds: Set<string>, format: 'markdown' | 'pdf'): void
}>()

const selectedIds = ref(new Set<string>())
const selectedCount = computed(() => selectedIds.value.size)

watch(() => props.visible, (v) => {
  if (v) {
    selectedIds.value = new Set(props.messages.map(m => m.id))
  }
})

function toggle(id: string) {
  const next = new Set(selectedIds.value)
  if (next.has(id)) { next.delete(id) } else { next.add(id) }
  selectedIds.value = next
}

function selectAll() {
  selectedIds.value = new Set(props.messages.map(m => m.id))
}

function deselectAll() {
  selectedIds.value = new Set()
}

function selectUserOnly() {
  selectedIds.value = new Set(props.messages.filter(m => m.role === 'user').map(m => m.id))
}

function selectAssistantOnly() {
  selectedIds.value = new Set(props.messages.filter(m => m.role === 'assistant').map(m => m.id))
}

function generate(format: 'markdown' | 'pdf' = 'markdown') {
  if (selectedCount.value === 0) {
    ElMessage.warning('请至少选择一条消息')
    return
  }
  emit('generate', selectedIds.value, format)
}

function formatMsgTime(ts: number) {
  const d = new Date(ts)
  return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
}

function truncate(text: string, maxLen: number) {
  if (!text) return '(空消息)'
  const cleaned = text.replace(/\n+/g, ' ').trim()
  return cleaned.length > maxLen ? cleaned.slice(0, maxLen) + '...' : cleaned
}
</script>

<style scoped>
.menu-overlay {
  position: fixed; inset: 0; z-index: 99; background: var(--rd-overlay-bg);
}

.report-dialog {
  position: fixed; top: 50%; left: 50%; transform: translate(-50%, -50%);
  z-index: 100; background: var(--rd-panel-bg); border-radius: 14px;
  box-shadow: var(--rd-panel-shadow);
  width: 560px; max-height: 80vh;
  display: flex; flex-direction: column; overflow: hidden;
}

.report-modal-enter-active { transition: all 0.2s cubic-bezier(0.22, 0.61, 0.36, 1); }
.report-modal-leave-active { transition: all 0.15s cubic-bezier(0.55, 0, 1, 0.45); }
.report-modal-enter-from,
.report-modal-leave-to { opacity: 0; transform: translate(-50%, -50%) scale(0.92); }

.report-header {
  display: flex; align-items: flex-start; justify-content: space-between;
  padding: 18px 24px; border-bottom: 1px solid var(--rd-divider); flex-shrink: 0;
}

.report-header h3 { font-size: 17px; font-weight: 600; color: var(--rd-title); margin: 0 0 4px; }
.report-subtitle { font-size: 12px; color: var(--rd-muted); margin: 0; }

.report-close {
  background: none; border: none; font-size: 22px; color: var(--rd-muted);
  cursor: pointer; padding: 0 4px; line-height: 1; border-radius: 6px; transition: all 0.12s;
}
.report-close:hover { color: var(--rd-hover-text); background: var(--rd-hover-bg); }

/* 工具栏 */
.report-toolbar {
  display: flex; align-items: center; gap: 6px;
  padding: 10px 24px; border-bottom: 1px solid var(--rd-divider); flex-shrink: 0; flex-wrap: wrap;
}

.toolbar-btn {
  display: inline-flex; align-items: center; gap: 4px;
  padding: 4px 10px; border-radius: 6px;
  border: 1px solid var(--rd-btn-border); background: var(--rd-btn-bg);
  font-size: 12px; color: var(--rd-btn-text); cursor: pointer; transition: all 0.12s;
}
.toolbar-btn:hover { background: var(--rd-hover-bg); border-color: var(--rd-btn-border-hover); }

.toolbar-count {
  margin-left: auto; font-size: 12px; color: var(--rd-count); white-space: nowrap;
}

/* 消息列表 */
.report-message-list {
  flex: 1; overflow-y: auto; padding: 8px 24px; min-height: 0;
}

.report-msg-item {
  display: flex; gap: 10px; padding: 10px 12px; border-radius: 8px;
  cursor: pointer; transition: background 0.1s; margin-bottom: 2px;
  border: 1px solid transparent;
}
.report-msg-item:hover { background: var(--rd-item-hover-bg); }
.report-msg-item.selected { background: var(--rd-item-selected-bg); border-color: var(--rd-item-selected-border); }

.msg-check { display: flex; align-items: flex-start; padding-top: 2px; flex-shrink: 0; }

.check-box {
  width: 18px; height: 18px; border-radius: 4px;
  border: 2px solid var(--rd-check-border); display: flex; align-items: center; justify-content: center;
  transition: all 0.12s; color: var(--rd-check-icon);
}
.check-box.checked { background: var(--rd-check-on-bg); border-color: var(--rd-check-on-bg); }

.msg-body { flex: 1; min-width: 0; }
.msg-meta { display: flex; align-items: center; gap: 8px; margin-bottom: 2px; }
.msg-role { font-size: 12px; font-weight: 500; }
.msg-role.user { color: var(--rd-role-user); }
.msg-role.assistant { color: var(--rd-role-assistant); }
.msg-time { font-size: 11px; color: var(--rd-muted); }

.msg-preview {
  font-size: 12px; color: var(--rd-preview-text); overflow: hidden; text-overflow: ellipsis;
  white-space: nowrap; line-height: 1.5;
}

/* 空状态 */
.report-empty {
  flex: 1; display: flex; flex-direction: column; align-items: center;
  justify-content: center; color: var(--rd-muted); font-size: 14px; gap: 8px;
}
.empty-icon { font-size: 40px; opacity: 0.5; }

/* 底部 */
.report-footer {
  display: flex; justify-content: space-between; align-items: center; gap: 8px;
  padding: 14px 24px; border-top: 1px solid var(--rd-divider); flex-shrink: 0;
}

.report-footer-right { display: flex; gap: 8px; }
</style>

<style>
/* Report dialog theme tokens — unscoped on purpose: the dialog and its overlay
   are teleported to <body>, and [data-theme] lives on <html>. */
.menu-overlay {
  --rd-overlay-bg: rgba(0, 0, 0, 0.3);
}

.report-dialog {
  --rd-panel-bg: #fff;
  --rd-panel-shadow: 0 16px 48px rgba(0, 0, 0, 0.18);
  --rd-divider: #f3f4f6;
  --rd-title: #1f2937;
  --rd-muted: #9ca3af;
  --rd-hover-bg: #f3f4f6;
  --rd-hover-text: #374151;
  --rd-btn-bg: #fff;
  --rd-btn-border: #e5e7eb;
  --rd-btn-border-hover: #d1d5db;
  --rd-btn-text: #4b5563;
  --rd-count: #6b7280;
  --rd-item-hover-bg: #f9fafb;
  --rd-item-selected-bg: #eff6ff;
  --rd-item-selected-border: #bfdbfe;
  --rd-check-border: #d1d5db;
  --rd-check-on-bg: #2563eb;
  --rd-check-icon: #fff;
  --rd-role-user: #2563eb;
  --rd-role-assistant: #10b981;
  --rd-preview-text: #6b7280;
}

[data-theme='dark'] .menu-overlay {
  --rd-overlay-bg: rgba(0, 0, 0, 0.55);
}

[data-theme='dark'] .report-dialog {
  --rd-panel-bg: #292a2e;
  --rd-panel-shadow: 0 16px 48px rgba(0, 0, 0, 0.4);
  --rd-divider: #3a3b40;
  --rd-title: #e7e9ee;
  --rd-muted: #9298a5;
  --rd-hover-bg: #393a40;
  --rd-hover-text: #e7e9ee;
  --rd-btn-bg: #222326;
  --rd-btn-border: #46474d;
  --rd-btn-border-hover: #5a5b62;
  --rd-btn-text: #c2c7d0;
  --rd-count: #9298a5;
  --rd-item-hover-bg: #323338;
  --rd-item-selected-bg: #303a5b;
  --rd-item-selected-border: #4a5a94;
  --rd-check-border: #46474d;
  --rd-check-on-bg: #6688fa;
  --rd-check-icon: #fff;
  --rd-role-user: #8ea9ff;
  --rd-role-assistant: #34d399;
  --rd-preview-text: #aeb4c0;
}
</style>
