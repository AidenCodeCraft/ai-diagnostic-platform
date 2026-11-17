import { describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'

import ChatMessageList from '@/components/chat/ChatMessageList.vue'

// ── 重依赖打桩：只关心「关联图片何时渲染」 ──────────────────
vi.mock('@/utils/markdown', () => ({
  renderMarkdown: (text: string) => `<p>${text}</p>`,
}))
vi.mock('@/utils/markdownLine', () => ({ anchorCandidate: () => null }))
vi.mock('@/composables/useFormat', () => ({
  useFormat: () => ({ formatFileSize: () => '0 B', fileIcon: () => '📄' }),
}))
vi.mock('@/api/chat', () => ({ chatApi: {} }))
vi.mock('@/api/knowledge', () => ({ knowledgeApi: {} }))
vi.mock('../components/chat/KnowledgeImageGallery.vue', () => ({
  default: { name: 'KnowledgeImageGallery', template: '<div class="stub-gallery" />' },
}))

const SOURCES = [
  {
    id: 1,
    title: '长沙',
    source: '知识库',
    excerpt: 'GPS 上传间隔',
    images: [{ id: 7, url: '/api/v1/knowledge/images/7', caption: '' }],
  },
]

function assistantMsg(overrides: Record<string, any> = {}) {
  return {
    id: 'a1',
    role: 'assistant',
    createdAt: 1,
    content: '',
    sources: SOURCES,
    ...overrides,
  }
}

describe('关联图片的展示时机', () => {
  it('流式进行中（答案还没出来）不显示关联图片', async () => {
    const wrapper = mount(ChatMessageList, {
      props: {
        messages: [assistantMsg({ thinking: { active: true, text: '', elapsed: 0 } })],
        loading: true,
      },
    })
    await flushPromises()

    expect(wrapper.find('.stub-gallery').exists()).toBe(false)
  })

  it('答案已完成时才显示关联图片', async () => {
    const wrapper = mount(ChatMessageList, {
      props: {
        messages: [
          assistantMsg({
            content: '答案正文',
            thinking: { active: false, text: '思考过程', elapsed: 2 },
          }),
        ],
        loading: false,
      },
    })
    await flushPromises()

    expect(wrapper.find('.stub-gallery').exists()).toBe(true)
  })

  it('图片出现在正文之后（不会先于答案渲染）', async () => {
    const wrapper = mount(ChatMessageList, {
      props: {
        messages: [
          assistantMsg({
            content: '答案正文',
            thinking: { active: false, text: '思考过程', elapsed: 2 },
          }),
        ],
        loading: false,
      },
    })
    await flushPromises()

    const html = wrapper.html()
    const contentIdx = html.indexOf('答案正文')
    const galleryIdx = html.indexOf('stub-gallery')
    expect(contentIdx).toBeGreaterThan(-1)
    expect(galleryIdx).toBeGreaterThan(contentIdx)
  })
})
