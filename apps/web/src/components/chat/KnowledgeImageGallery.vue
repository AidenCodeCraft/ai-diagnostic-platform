<template>
  <div v-if="items.length" class="kb-image-gallery">
    <div class="gallery-label">
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <rect x="3" y="3" width="18" height="18" rx="2" />
        <circle cx="8.5" cy="8.5" r="1.5" />
        <path d="M21 15l-5-5L5 21" />
      </svg>
      关联图片
      <span class="gallery-count">{{ items.length }}</span>
    </div>

    <div class="gallery-grid">
      <figure
        v-for="(img, i) in items"
        :key="img.id"
        class="gallery-item"
        :class="{ 'is-feedbacked': img._feedback }"
        @click="open(i)"
      >
        <div class="gallery-thumb">
          <img
            v-if="!img._broken && !img._feedback"
            :src="img.url"
            :alt="img.caption || '知识库图片'"
            loading="lazy"
            decoding="async"
            @load="img._loaded = true"
            @error="img._broken = true"
          />
          <div v-else-if="img._feedback" class="gallery-feedbacked">已标记为不相关</div>
          <div v-else class="gallery-broken">
            <span>🖼 图片缺失</span>
            <button type="button" @click.stop="retry(img, i)">重试</button>
          </div>
          <div v-if="!img._loaded && !img._broken && !img._feedback" class="gallery-skeleton" />
          <button
            v-if="!img._feedback"
            type="button"
            class="gallery-feedback-btn"
            title="标记为不相关"
            @click.stop="feedback(img)"
          >不相关</button>
        </div>
        <figcaption v-if="img.caption" class="gallery-caption">{{ img.caption }}</figcaption>
      </figure>
    </div>

    <!-- 灯箱 -->
    <Teleport to="body">
      <Transition name="lb-fade">
        <div v-if="lightbox.visible" class="img-lightbox-overlay" @click.self="close">
          <div class="img-lightbox">
            <button class="lb-btn lb-close" @click="close" title="关闭 (Esc)">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" /></svg>
            </button>
            <button v-if="items.length > 1" class="lb-btn lb-prev" @click="prev" title="上一张 (←)">
              <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="15 18 9 12 15 6" /></svg>
            </button>
            <img class="lb-img" :src="current.url" :alt="current.caption || ''" />
            <button v-if="items.length > 1" class="lb-btn lb-next" @click="next" title="下一张 (→)">
              <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="9 18 15 12 9 6" /></svg>
            </button>
            <div class="lb-footer">
              <div v-if="current.caption" class="lb-caption">{{ current.caption }}</div>
              <div class="lb-meta">
                <a class="lb-download" :href="current.url" download :title="'下载'">
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" /><polyline points="7 10 12 15 17 10" /><line x1="12" y1="15" x2="12" y2="3" /></svg>
                  下载
                </a>
                <span class="lb-index">{{ lightbox.index + 1 }} / {{ items.length }}</span>
              </div>
            </div>
          </div>
        </div>
      </Transition>
    </Teleport>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import type { ChatImage } from '@/api/chat'
import { knowledgeApi } from '@/api/knowledge'

interface GalleryImage extends ChatImage {
  _broken?: boolean
  _loaded?: boolean
  _feedback?: boolean
}

const props = defineProps<{ images: ChatImage[] }>()

const items = ref<GalleryImage[]>([])
watch(
  () => props.images,
  (v) => {
    items.value = (v || []).map((im) => ({ ...im, _broken: false, _loaded: false }))
  },
  { immediate: true },
)

const lightbox = ref({ visible: false, index: 0 })
const current = computed<GalleryImage>(() => items.value[lightbox.value.index] || ({} as GalleryImage))

function open(i: number) {
  lightbox.value = { visible: true, index: i }
}
function close() {
  lightbox.value.visible = false
}
function prev() {
  const n = items.value.length
  lightbox.value.index = (lightbox.value.index - 1 + n) % n
}
function next() {
  const n = items.value.length
  lightbox.value.index = (lightbox.value.index + 1) % n
}

function retry(img: GalleryImage, _i: number) {
  img._broken = false
  img._loaded = false
  // 追加查询串强制重新请求，绕过缓存
  const sep = img.url.includes('?') ? '&' : '?'
  img.url = `${img.url}${sep}retry=${Date.now()}`
}

async function feedback(img: GalleryImage) {
  if (img._feedback) return
  try {
    await knowledgeApi.feedbackImage(img.id, 'irrelevant')
    img._feedback = true
  } catch (e: any) {
    console.warn('[KnowledgeImageGallery] feedback failed:', e)
  }
}

function onKey(e: KeyboardEvent) {
  if (!lightbox.value.visible) return
  if (e.key === 'Escape') close()
  else if (e.key === 'ArrowLeft') prev()
  else if (e.key === 'ArrowRight') next()
}

onMounted(() => window.addEventListener('keydown', onKey))
onBeforeUnmount(() => window.removeEventListener('keydown', onKey))
</script>

<style scoped>
.kb-image-gallery {
  margin-top: 12px;
  padding: 10px 12px;
  border: 1px solid var(--chat-source-border, #e5e7eb);
  border-radius: 10px;
  background: var(--chat-source-bg, #f9fafb);
}
.gallery-label {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  font-weight: 600;
  color: #6b7280;
  margin-bottom: 8px;
}
.gallery-count {
  font-size: 11px;
  color: #9ca3af;
  font-weight: 500;
}
.gallery-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}
.gallery-item {
  margin: 0;
  width: 200px;
  max-width: 100%;
  cursor: zoom-in;
}
.gallery-thumb {
  position: relative;
  width: 100%;
  aspect-ratio: 4 / 3;
  background: #f3f4f6;
  border-radius: 8px;
  overflow: hidden;
  border: 1px solid #e5e7eb;
}
.gallery-thumb img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
  transition: transform 0.15s ease, opacity 0.3s ease;
}
.gallery-item:hover .gallery-thumb img {
  transform: scale(1.03);
}
.gallery-skeleton {
  position: absolute;
  inset: 0;
  background: linear-gradient(90deg, #f3f4f6 25%, #e5e7eb 50%, #f3f4f6 75%);
  background-size: 200% 100%;
  animation: shimmer 1.2s infinite;
}
@keyframes shimmer {
  to { background-position: -200% 0; }
}
.gallery-broken {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 6px;
  color: #9ca3af;
  font-size: 12px;
}
.gallery-broken button {
  border: 1px solid #d1d5db;
  background: #fff;
  color: #374151;
  border-radius: 4px;
  padding: 2px 8px;
  font-size: 11px;
  cursor: pointer;
}
.gallery-feedback-btn {
  position: absolute;
  top: 6px;
  right: 6px;
  border: 1px solid rgba(0, 0, 0, 0.08);
  background: rgba(255, 255, 255, 0.92);
  color: #6b7280;
  border-radius: 4px;
  padding: 2px 8px;
  font-size: 11px;
  cursor: pointer;
  opacity: 0;
  transition: opacity 0.15s;
}
.gallery-item:hover .gallery-feedback-btn { opacity: 1; }
.gallery-feedback-btn:hover { color: #dc2626; border-color: #fecaca; }
.gallery-feedbacked {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #9ca3af;
  font-size: 12px;
  background: #f9fafb;
}
.gallery-caption {
  margin-top: 4px;
  font-size: 11px;
  color: #9ca3af;
  text-align: center;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* 灯箱 */
.img-lightbox-overlay {
  position: fixed;
  inset: 0;
  z-index: 10000;
  background: rgba(0, 0, 0, 0.82);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
}
.img-lightbox {
  position: relative;
  max-width: min(92vw, 1100px);
  max-height: 92vh;
  display: flex;
  flex-direction: column;
  align-items: center;
}
.lb-img {
  max-width: 100%;
  max-height: calc(92vh - 80px);
  object-fit: contain;
  border-radius: 6px;
}
.lb-btn {
  position: absolute;
  top: 50%;
  transform: translateY(-50%);
  z-index: 2;
  display: grid;
  place-items: center;
  width: 44px;
  height: 44px;
  border: none;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.12);
  color: #fff;
  cursor: pointer;
  transition: background 0.15s;
}
.lb-btn:hover { background: rgba(255, 255, 255, 0.24); }
.lb-close { top: 0; right: 0; transform: none; width: 36px; height: 36px; }
.lb-prev { left: 8px; }
.lb-next { right: 8px; }
.lb-footer {
  margin-top: 12px;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  width: 100%;
}
.lb-caption {
  color: #e5e7eb;
  font-size: 13px;
  text-align: center;
  max-width: 90%;
}
.lb-meta {
  display: flex;
  align-items: center;
  gap: 16px;
}
.lb-download {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  color: #d1d5db;
  font-size: 12px;
  text-decoration: none;
  padding: 4px 10px;
  border: 1px solid rgba(255, 255, 255, 0.25);
  border-radius: 6px;
  transition: all 0.15s;
}
.lb-download:hover { color: #fff; border-color: #fff; }
.lb-index { color: #9ca3af; font-size: 12px; }

.lb-fade-enter-active,
.lb-fade-leave-active { transition: opacity 0.18s ease; }
.lb-fade-enter-from,
.lb-fade-leave-to { opacity: 0; }

@media (max-width: 640px) {
  .gallery-item { width: 140px; }
}
</style>
