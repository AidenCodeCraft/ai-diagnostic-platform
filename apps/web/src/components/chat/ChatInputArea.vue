<template>
  <div class="input-container">
    <!-- 附件列表 -->
    <div v-if="files.length > 0" class="upload-area">
      <div v-for="fa in files" :key="fa.id" class="upload-file-card">
        <div class="ufc-icon">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
            <polyline points="14 2 14 8 20 8" />
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
        <button class="ufc-remove" @click="$emit('removeFile', fa.id)"
          :disabled="fa.status === 'uploading'">&times;</button>
      </div>
    </div>

    <!-- 截图列表（识别结果作为现场证据参与诊断） -->
    <div v-if="images.length > 0" class="image-area">
      <div v-for="img in images" :key="img.id" class="image-card">
        <img :src="img.previewUrl" :alt="img.name" class="image-thumb" />
        <div class="image-meta">
          <span class="image-name">{{ img.name }}</span>
          <span class="image-status" :class="img.status">{{ imageStatusText(img) }}</span>
          <span v-if="img.error" class="ufc-error">{{ img.error }}</span>
        </div>
        <button class="ufc-remove" :disabled="img.status === 'uploading'"
          @click="emit('removeImage', img.id)">&times;</button>
      </div>
    </div>

    <!-- 输入框 -->
    <div class="input-box" :class="{ 'has-uploads': files.length > 0 || images.length > 0 }">
      <textarea ref="textareaRef" v-model="model" placeholder="输入问题...（可直接粘贴截图）" class="msg-textarea" :rows="1"
        @keydown.enter.exact.prevent="$emit('send')" @input="autoResize" @paste="onPaste"></textarea>
      <div class="input-actions">
        <div class="actions-left">
          <el-select :model-value="selectedModel" size="small" class="model-select" popper-class="model-select-popper"
            @update:model-value="emit('modelChange', $event as string)">
            <el-option v-for="m in availableModels" :key="m.value" :label="m.label" :value="m.value" />
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
          <label class="action-btn attach-btn" title="上传截图（PNG/JPG/WebP，可粘贴）">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <rect x="3" y="3" width="18" height="18" rx="2" />
              <circle cx="8.5" cy="8.5" r="1.5" />
              <path d="m21 15-5-5L5 21" />
            </svg>
            <input type="file" accept="image/png,image/jpeg,image/webp" multiple @change="onImageChange" hidden />
          </label>
          <label class="action-btn attach-btn" title="上传文件 (最大 200MB)">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path
                d="m21.44 11.05-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48" />
            </svg>
            <input type="file" accept=".log,.txt,.zip" @change="$emit('fileInput', $event)" hidden multiple />
          </label>
          <button v-if="isStreaming" class="action-btn stop-btn" title="停止生成" @click="$emit('stop')">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor" stroke="none">
              <rect x="6" y="6" width="12" height="12" rx="2" />
            </svg>
            <span>停止</span>
          </button>
          <button v-else class="action-btn send-btn" :disabled="!model.trim() || isUploading || imagesBusy"
            :class="{ active: model.trim() && !isUploading && !imagesBusy }" @click="$emit('send')">
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
import { computed, ref, onMounted, onUnmounted } from 'vue'
import { useFormat } from '@/composables/useFormat'
import { adminApi, type ModelOption } from '@/api/admin'
import type { FileAttachment, ImageAttachment } from './types'

const { formatFileSize } = useFormat()

const props = defineProps<{
  modelValue: string
  files: FileAttachment[]
  images?: ImageAttachment[]
  selectedModel: string
  isUploading: boolean
  canReport: boolean
  hasMessages: boolean
  /** 当前对话正在流式生成中 */
  isStreaming?: boolean
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', value: string): void
  (e: 'send'): void
  (e: 'stop'): void
  (e: 'fileInput', event: Event): void
  (e: 'imageInput', files: File[]): void
  (e: 'removeImage', id: string): void
  (e: 'removeFile', id: string): void
  (e: 'modelChange', model: string): void
  (e: 'generateReport'): void
}>()

const model = computed({
  get: () => props.modelValue,
  set: (v) => emit('update:modelValue', v),
})

const textareaRef = ref<HTMLTextAreaElement>()
const modelsLoading = ref(false)
const availableModels = ref<ModelOption[]>([
  { label: 'DeepSeek V4 Flash', value: 'deepseek-v4-flash', isDefault: true },
  { label: 'DeepSeek V4 Pro', value: 'deepseek-v4-pro', isDefault: false },
])

const MAX_FILE_SIZE = 200 * 1024 * 1024  // 200MB

const images = computed(() => props.images || [])

/** 截图是否还在识别：识别未完成不允许发送，避免证据缺失 */
const imagesBusy = computed(() => images.value.some(i => i.status === 'uploading'))

function imageStatusText(img: ImageAttachment): string {
  if (img.status === 'uploading') return '识别中…'
  if (img.status === 'error') return '识别失败（可移除后重试）'
  const label = img.path === 'vision' ? '图像理解' : img.path === 'ocr+vision' ? 'OCR+图像理解' : 'OCR 识别'
  const lines = (img.text || '').split('\n').filter(Boolean).length
  return lines ? `${label} · ${lines} 行` : label
}

function onImageChange(e: Event) {
  const input = e.target as HTMLInputElement
  if (input.files && input.files.length) {
    emit('imageInput', Array.from(input.files))
  }
  input.value = ''
}

/** 直接粘贴截图（Ctrl+V）：剪贴板里是文件而不是文本时才拦截默认行为 */
function onPaste(e: ClipboardEvent) {
  const items = e.clipboardData?.items
  if (!items) return
  const files: File[] = []
  for (const item of Array.from(items)) {
    if (item.kind === 'file' && item.type.startsWith('image/')) {
      const file = item.getAsFile()
      if (file) files.push(file)
    }
  }
  if (files.length) {
    e.preventDefault()
    emit('imageInput', files)
  }
}

async function loadAvailableModels() {
  modelsLoading.value = true
  try {
    const { data } = await adminApi.getAvailableModels()
    if (data?.models?.length) {
      availableModels.value = data.models
    } else {
      console.warn('[ChatInputArea] API returned empty models, using defaults')
    }
  } catch (err) {
    console.error('[ChatInputArea] Failed to load models:', err)
  } finally {
    modelsLoading.value = false
  }
}

function handleConfigUpdate() {
  loadAvailableModels()
}

onMounted(() => {
  loadAvailableModels()
  window.addEventListener('llm-config-updated', handleConfigUpdate)
})

onUnmounted(() => {
  window.removeEventListener('llm-config-updated', handleConfigUpdate)
})

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

.image-area {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  padding: 8px 12px 0;
}

.image-card {
  display: flex;
  align-items: center;
  gap: 8px;
  max-width: 320px;
  padding: 6px 8px;
  border-radius: 8px;
  border: 1px solid var(--chat-upload-area-border, #e5e7eb);
  background: var(--chat-upload-card-bg, #fff);
}

.image-thumb {
  width: 40px;
  height: 40px;
  object-fit: cover;
  border-radius: 6px;
  flex: none;
}

.image-meta {
  display: flex;
  flex-direction: column;
  min-width: 0;
  gap: 2px;
}

.image-name {
  font-size: 12px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.image-status {
  font-size: 11px;
  color: var(--chat-upload-icon, #6b7280);
}

.image-status.done { color: #16a34a; }
.image-status.error { color: #dc2626; }

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

.ufc-icon {
  color: var(--chat-upload-icon);
  flex-shrink: 0;
}

.ufc-info {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.ufc-name {
  font-size: 13px;
  color: var(--chat-upload-name);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.ufc-size {
  font-size: 11px;
  color: var(--chat-upload-size);
}

.ufc-progress-wrap {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 2px;
}

.ufc-progress {
  flex: 1;
  height: 4px;
  background: var(--chat-upload-progress-bg);
  border-radius: 2px;
  overflow: hidden;
}

.ufc-progress-bar {
  height: 100%;
  border-radius: 2px;
  transition: width 0.3s;
  background: var(--chat-upload-progress-bar);
}

.ufc-progress-bar.done {
  background: #22c55e;
}

.ufc-progress-bar.error {
  background: #ef4444;
}

.ufc-status {
  font-size: 11px;
  white-space: nowrap;
}

.ufc-status.uploading,
.ufc-status.parsing {
  color: #2563eb;
}

.ufc-status.done {
  color: #22c55e;
}

.ufc-status.error {
  color: #ef4444;
}

.ufc-error {
  font-size: 11px;
  color: #ef4444;
}

.ufc-remove {
  background: none;
  border: none;
  font-size: 18px;
  cursor: pointer;
  color: #9ca3af;
  padding: 0 4px;
  flex-shrink: 0;
}

.ufc-remove:hover {
  color: #ef4444;
}

.ufc-remove:disabled {
  opacity: 0.3;
  cursor: not-allowed;
}

.upload-area+.input-box {
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

.msg-textarea::placeholder {
  color: var(--chat-input-placeholder);
}

.input-actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 4px 12px 10px;
}

.actions-left,
.actions-right {
  display: flex;
  align-items: center;
  gap: 6px;
}

.model-select {
  width: 175px;
}

/* Element Plus 2.7+ 的 el-select 使用 .el-select__wrapper（旧版为 .el-input__wrapper），
   颜色全部走 chat-theme 的 --chat-select-* 变量，深浅色主题下均正确显示 */
:deep(.model-select .el-select__wrapper) {
  border-radius: 20px;
  box-shadow: none !important;
  border: none;
  background: var(--chat-select-bg);
  color: var(--chat-select-text);
  padding: 0 12px;
  min-height: 30px;
  height: 30px;
  font-size: 13px;
}

:deep(.model-select .el-select__wrapper:hover),
:deep(.model-select .el-select__wrapper.is-focused) {
  box-shadow: none !important;
  background: var(--chat-select-bg);
}

:deep(.model-select .el-select__selected-item) {
  color: var(--chat-select-text);
}

:deep(.model-select .el-select__placeholder) {
  color: var(--chat-input-placeholder);
}

:deep(.model-select .el-select__caret) {
  color: var(--chat-select-text);
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

.action-btn:hover {
  background: var(--chat-input-action-hover-bg);
  color: var(--chat-input-action-hover-text);
}

.action-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.attach-btn {
  width: auto;
  min-width: 30px;
  padding: 0 8px;
  justify-content: center;
  cursor: pointer;
  gap: 4px;
  position: relative;
}

.attach-btn input[type="file"] {
  display: none;
}

.stop-btn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  color: #dc2626;
  border: 1px solid #fca5a5;
  background: #fef2f2;
}
.stop-btn:hover {
  background: #fee2e2;
}

.send-btn {
  width: 30px;
  padding: 0;
  justify-content: center;
}

.send-btn.active {
  background: var(--chat-input-send-active-bg);
  border-color: var(--chat-input-send-active-border);
  color: #fff;
}

.send-btn.active:hover {
  filter: brightness(1.08);
}
</style>
