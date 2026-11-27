<template>
  <div v-if="items.length" class="user-image-strip">
    <button
      v-for="it in items"
      :key="it.id"
      type="button"
      class="uimg-thumb"
      :class="{ 'is-loading': it.loading, 'is-failed': it.failed }"
      :title="it.failed ? '图片加载失败' : '点击查看大图'"
      @click="open(it)"
    >
      <img v-if="it.url" :src="it.url" alt="提问截图" loading="lazy" decoding="async" />
      <span v-else-if="it.failed" class="uimg-placeholder">图片不可用</span>
      <span v-else class="uimg-skeleton" />
    </button>

    <Teleport to="body">
      <div v-if="preview" class="uimg-lightbox" @click.self="preview = ''">
        <img :src="preview" alt="提问截图" />
        <button type="button" class="uimg-close" title="关闭 (Esc)" @click="preview = ''">×</button>
      </div>
    </Teleport>
  </div>
</template>

<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { chatApi } from '@/api/chat'

interface StripItem {
  id: number
  url?: string
  loading: boolean
  failed?: boolean
}

const props = defineProps<{ imageIds: number[] }>()

const items = ref<StripItem[]>([])
const preview = ref('')
let urls: string[] = []

function revoke() {
  urls.forEach((u) => URL.revokeObjectURL(u))
  urls = []
}

async function load(ids: number[]) {
  revoke()
  items.value = (ids || []).map((id) => ({ id, loading: true }))
  for (const item of items.value) {
    try {
      const url = await chatApi.getChatImageFile(item.id)
      // 组件在请求期间被切换（watcher 重新加载）时丢弃过期结果
      if (!items.value.includes(item)) {
        URL.revokeObjectURL(url)
        continue
      }
      urls.push(url)
      item.url = url
      item.loading = false
    } catch {
      item.loading = false
      item.failed = true
    }
  }
}

watch(() => props.imageIds, (ids) => load(ids), { immediate: true })

function open(it: StripItem) {
  if (it.url) preview.value = it.url
}

function onKey(e: KeyboardEvent) {
  if (e.key === 'Escape') preview.value = ''
}

onMounted(() => window.addEventListener('keydown', onKey))
onBeforeUnmount(() => {
  window.removeEventListener('keydown', onKey)
  revoke()
})
</script>

<style scoped>
.user-image-strip {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 8px;
}
.uimg-thumb {
  position: relative;
  width: 148px;
  height: 100px;
  padding: 0;
  border: 1px solid var(--chat-source-border, #e5e7eb);
  border-radius: 8px;
  background: var(--chat-source-bg, #f9fafb);
  overflow: hidden;
  cursor: zoom-in;
}
.uimg-thumb img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}
.uimg-thumb.is-loading {
  cursor: default;
}
.uimg-skeleton {
  position: absolute;
  inset: 0;
  background: linear-gradient(
    90deg,
    var(--chat-upload-area-bg, #f3f4f6) 25%,
    var(--chat-upload-area-border, #e5e7eb) 50%,
    var(--chat-upload-area-bg, #f3f4f6) 75%
  );
  background-size: 200% 100%;
  animation: uimg-shimmer 1.2s infinite;
}
@keyframes uimg-shimmer {
  to { background-position: -200% 0; }
}
.uimg-placeholder {
  position: absolute;
  inset: 0;
  display: grid;
  place-items: center;
  font-size: 12px;
  color: var(--chat-copy-text, #9ca3af);
}
.uimg-lightbox {
  position: fixed;
  inset: 0;
  z-index: 10000;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
  background: rgba(0, 0, 0, 0.82);
}
.uimg-lightbox img {
  max-width: min(94vw, 1200px);
  max-height: 92vh;
  object-fit: contain;
  border-radius: 6px;
}
.uimg-close {
  position: absolute;
  top: 16px;
  right: 20px;
  width: 36px;
  height: 36px;
  border: none;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.14);
  color: #fff;
  font-size: 22px;
  line-height: 1;
  cursor: pointer;
}
.uimg-close:hover {
  background: rgba(255, 255, 255, 0.26);
}
</style>
