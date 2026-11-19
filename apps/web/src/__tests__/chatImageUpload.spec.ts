import { describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'

import ChatInputArea from '@/components/chat/ChatInputArea.vue'
import type { ImageAttachment } from '@/components/chat/types'

vi.mock('@/api/admin', () => ({
  adminApi: { getAvailableModels: vi.fn().mockResolvedValue({ data: [] }) },
}))

function mountInput(images: ImageAttachment[] = []) {
  return mount(ChatInputArea, {
    props: {
      modelValue: '',
      files: [],
      images,
      selectedModel: 'deepseek-v4-flash',
      isUploading: false,
      canReport: false,
      hasMessages: false,
    },
    global: {
      stubs: { 'el-select': true, 'el-option': true },
    },
  })
}

function imageFile(name = 'shot.png') {
  return new File([new Uint8Array([0x89, 0x50, 0x4e, 0x47])], name, { type: 'image/png' })
}

describe('ChatInputArea 截图入口', () => {
  it('选择图片后抛出 imageInput 事件', async () => {
    const wrapper = mountInput()
    const input = wrapper.find('input[type="file"][accept*="image/png"]')
    const file = imageFile()

    Object.defineProperty(input.element, 'files', { value: [file] })
    await input.trigger('change')

    const events = wrapper.emitted('imageInput')
    expect(events).toBeTruthy()
    expect((events![0][0] as File[])[0].name).toBe('shot.png')
  })

  it('粘贴截图（剪贴板图片）同样抛出 imageInput', async () => {
    const wrapper = mountInput()
    const file = imageFile('paste.png')
    const event = new Event('paste') as ClipboardEvent
    Object.defineProperty(event, 'clipboardData', {
      value: { items: [{ kind: 'file', type: 'image/png', getAsFile: () => file }] },
    })

    wrapper.find('textarea').element.dispatchEvent(event)
    await wrapper.vm.$nextTick()

    const events = wrapper.emitted('imageInput')
    expect(events).toBeTruthy()
    expect((events![0][0] as File[])[0].name).toBe('paste.png')
  })

  it('识别未完成时禁止发送', () => {
    const wrapper = mountInput([
      {
        id: 'a',
        file: imageFile(),
        name: 'shot.png',
        previewUrl: 'blob:fake',
        status: 'uploading',
      },
    ])
    const send = wrapper.find('.send-btn')
    expect(send.attributes('disabled')).toBeDefined()
  })

  it('点击移除抛出 removeImage', async () => {
    const wrapper = mountInput([
      {
        id: 'img-1',
        file: imageFile(),
        name: 'shot.png',
        previewUrl: 'blob:fake',
        status: 'done',
        path: 'ocr',
        text: 'a\nb',
      },
    ])

    await wrapper.find('.image-card .ufc-remove').trigger('click')

    expect(wrapper.emitted('removeImage')![0]).toEqual(['img-1'])
    expect(wrapper.text()).toContain('OCR 识别 · 2 行')
  })
})
