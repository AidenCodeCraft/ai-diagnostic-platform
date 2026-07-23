<template>
  <div class="input-container">
    <!-- 附件列表 -->
    <div v-if="files.length > 0" class="upload-area">
      <div v-for="fa in files" :key="fa.id" class="upload-file-card">
        <div class="ufc-icon">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
            <polyline points="14 2 14 8 20 8"/>
          </svg>
        </div>
        <div class="ufc-info">
          <span class="ufc-name">{{ fa.name }}</span>
          <span class="ufc-size">{{ formatSize(fa.file.size) }}</span>
          <div class="ufc-progress-wrap" v-if="fa.status !== 'pending'">
            <div class="ufc-progress">
              <div class="ufc-progress-bar" :class="fa.status" :style="{ width: fa.progress + '%' }"></div>
            </div>
            <span class="ufc-status" :class="fa.status">
              {{ statusText(fa) }}
            </span>
          </div>
          <span v-if="fa.error" class="ufc-error">{{ fa.error }}</span>
        </div>
        <button class="ufc-remove" @click="$emit('removeFile', fa.id)" :disabled="fa.status === 'uploading'">&times;</button>
      </div>
    </div>

    <!-- 输入框 -->
    <div class="input-box" :class="{ 'has-uploads': files.length > 0 }">
      <textarea
        ref="textareaRef"
        v-model="model"
        placeholder="输入问题或拖拽日志文件..."
        class="msg-textarea"
        :rows="1"
        @keydown.enter.exact.prevent="$emit('send')"
        @input="autoResize"
      ></textarea>
      <div class="input-actions">
        <div class="actions-left">
          <el-select
            :model-value="selectedModel"
            size="small"
            class="model-select"
            popper-class="model-select-popper"
            @update:model-value="emit('modelChange', $event as string)"
          >
            <el-option label="Mock (开发模式)" value="mock" />
            <el-option label="DeepSeek" value="deepseek" />
          </el-select>
          <button class="action-btn report-btn" :disabled="!canReport" title="生成诊断报告" @click="$emit('generateReport')">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
              <polyline points="14 2 14 8 20 8" />
            </svg>
            <span v-if="hasMessages">生成报告</span>
          </button>
        </div>
        <div class="actions-right">
          <label class="action-btn attach-btn" title="上传文件 (最大 200MB)">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="m21.44 11.05-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48" />
            </svg>
            <input type="file" accept=".log,.txt,.zip" @change="$emit('fileInput', $event)" hidden multiple />
          </label>
          <button
            class="action-btn send-btn"
            :disabled="!model.trim() || isUploading"
            :class="{ active: model.trim() && !isUploading }"
            @click="$emit('send')"
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor" stroke="none">
              <path d="M2.01 21 23 12 2.01 3 2 10l15 2-15 2z" />
            </svg>
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useFormat } from '@/composables/useFormat'
import type { FileAttachment } from './types'

const { formatFileSize } = useFormat()

const props = defineProps<{
  modelValue: string
  files: FileAttachment[]
  selectedModel: string
  isUploading: boolean
  canReport: boolean
  hasMessages: boolean
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', value: string): void
  (e: 'send'): void
  (e: 'fileInput', event: Event): void
  (e: 'removeFile', id: string): void
  (e: 'modelChange', model: string): void
  (e: 'generateReport'): void
}>()

const model = computed({
  get: () => props.modelValue,
  set: (v) => emit('update:modelValue', v),
})

const textareaRef = ref<HTMLTextAreaElement>()

function autoResize() {
  if (!textareaRef.value) return
  textareaRef.value.style.height = 'auto'
  textareaRef.value.style.height = Math.min(textareaRef.value.scrollHeight, 200) + 'px'
}

function formatSize(bytes: number) {
  return formatFileSize(bytes)
}

function statusText(fa: FileAttachment): string {
  switch (fa.status) {
    case 'uploading': return `上传中 ${fa.progress}%`
    case 'parsing': return '解析中...'
    case 'done': return '✓ 完成'
    case 'error': return '✕ 失败'
    default: return ''
  }
}
</script>

<style scoped>
.input-container {
  width: 100%;
  max-width: var(--chat-content-width);
  margin: 0 auto;
}

.upload-area {
  display: flex;
  flex-direction: column;
  gap: 1px;
  background: var(--chat-upload-area-bg);
  border: 1px solid var(--chat-upload-area-border);
  border-bottom: none;
  border-radius: 10px 10px 0 0;
  overflow: hidden;
  max-height: 200px;
  overflow-y: auto;
}

.upload-file-card {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 14px;
  background: var(--chat-upload-card-bg);
  border-bottom: 1px solid var(--chat-upload-card-border);
}

.ufc-icon { color: var(--chat-upload-icon); flex-shrink: 0; }
.ufc-info { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 2px; }
.ufc-name { font-size: 13px; color: var(--chat-upload-name); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.ufc-size { font-size: 11px; color: var(--chat-upload-size); }
.ufc-progress-wrap { display: flex; align-items: center; gap: 8px; margin-top: 2px; }
.ufc-progress { flex: 1; height: 4px; background: var(--chat-upload-progress-bg); border-radius: 2px; overflow: hidden; }
.ufc-progress-bar { height: 100%; border-radius: 2px; transition: width 0.3s; background: var(--chat-upload-progress-bar); }
.ufc-progress-bar.done { background: #22c55e; }
.ufc-progress-bar.error { background: #ef4444; }
.ufc-status { font-size: 11px; white-space: nowrap; }
.ufc-status.uploading, .ufc-status.parsing { color: #2563eb; }
.ufc-status.done { color: #22c55e; }
.ufc-status.error { color: #ef4444; }
.ufc-error { font-size: 11px; color: #ef4444; }
.ufc-remove {
  background: none; border: none; font-size: 18px; cursor: pointer; color: #9ca3af; padding: 0 4px; flex-shrink: 0;
}
.ufc-remove:hover { color: #ef4444; }
.ufc-remove:disabled { opacity: 0.3; cursor: not-allowed; }

.upload-area + .input-box {
  border-radius: 0 0 12px 12px;
  border-top: none;
}

.input-box {
  border: 1px solid var(--chat-input-border);
  border-radius: 16px;
  background: var(--chat-input-bg);
  box-shadow: var(--chat-input-shadow);
  transition: border-color 0.15s, box-shadow 0.15s;
  overflow: hidden;
}

.input-box:focus-within {
  border-color: var(--chat-input-focus-border);
  box-shadow: 0 0 0 3px var(--chat-input-focus-ring);
}

.msg-textarea {
  width: 100%;
  border: none;
  outline: none;
  resize: none;
  padding: 14px 16px 8px;
  font-size: 15px;
  line-height: 1.6;
  font-family: inherit;
  color: var(--chat-input-text);
  background: transparent;
  min-height: 48px;
}

.msg-textarea::placeholder { color: var(--chat-input-placeholder); }

.input-actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 4px 12px 10px;
}

.actions-left, .actions-right {
  display: flex;
  align-items: center;
  gap: 6px;
}

.model-select { width: 150px; }

:deep(.model-select .el-input__wrapper) {
  border-radius: 20px;
  box-shadow: none !important;
  border: 1px solid var(--chat-select-border);
  background: var(--chat-select-bg);
  padding: 0 12px;
  height: 30px;
  font-size: 13px;
}

:deep(.model-select .el-input__inner) {
  color: var(--chat-select-text);
}

:deep(.model-select .el-input__wrapper:hover) {
  border-color: var(--chat-select-hover-border);
}

.action-btn {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  height: 30px;
  padding: 0 10px;
  border-radius: 20px;
  border: 1px solid var(--chat-input-action-border);
  background: var(--chat-input-action-bg);
  color: var(--chat-input-action-text);
  cursor: pointer;
  font-size: 13px;
  transition: all 0.15s;
}

.action-btn:hover { background: var(--chat-input-action-hover-bg); color: var(--chat-input-action-hover-text); }
.action-btn:disabled { opacity: 0.4; cursor: not-allowed; }

.attach-btn {
  width: auto; min-width: 30px;
  padding: 0 8px;
  justify-content: center;
  cursor: pointer;
  gap: 4px;
  position: relative;
}

.attach-btn input[type="file"] {
  display: none;
}

.send-btn { width: 30px; padding: 0; justify-content: center; }

.send-btn.active {
  background: var(--chat-input-send-active-bg);
  border-color: var(--chat-input-send-active-border);
  color: #fff;
}

.send-btn.active:hover { filter: brightness(1.08); }
</style>
