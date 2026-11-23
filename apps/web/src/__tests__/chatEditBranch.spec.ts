import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { createPinia } from 'pinia'

import ChatLayout from '@/layouts/ChatLayout.vue'

const stub = vi.hoisted(() => ({
  template: '<div />',
  methods: { scrollToBottom() {} },
}))

/** 消息列表桩：暴露当前展示的消息，提供编辑重发 / 切换版本两个入口 */
const listStub = vi.hoisted(() => ({
  props: ['messages'],
  emits: ['editSend', 'switchVersion'],
  template: `
    <div class="list-stub">
      <span class="count">{{ messages.length }}</span>
      <button class="edit-q2" @click="$emit('editSend', messages[2], '改过的第二个问题')">编辑</button>
      <button class="ver-1" @click="$emit('switchVersion', messages[2], 0)">切回旧版本</button>
    </div>`,
}))

vi.mock('@/api/client', () => ({ default: { get: vi.fn(), post: vi.fn() } }))

const chatApiMock = vi.hoisted(() => ({
  listSessions: vi.fn(),
  getMessages: vi.fn(),
  saveMessage: vi.fn(),
  createSession: vi.fn(),
  deleteSession: vi.fn(),
  updateSession: vi.fn(),
  updateMessage: vi.fn(),
  sendMessageStream: vi.fn(),
}))
vi.mock('@/api/chat', () => ({ chatApi: chatApiMock }))
vi.mock('@/api/admin', () => ({ adminApi: { updateUser: vi.fn() } }))
vi.mock('@/stores/user', () => ({
  useUserStore: () => ({ userName: '测试用户', isAdmin: false, user: null, logout: vi.fn() }),
}))
vi.mock('@/utils/export', () => ({ exportChat: vi.fn() }))
vi.mock('@/composables/useChatBranch', () => ({
  useChatBranch: () => ({
    state: { currentBranchId: 'main' }, currentBranch: null, branchCount: 1,
    createBranch: vi.fn(), switchBranch: vi.fn(), getBranches: () => [], reset: vi.fn(), deleteBranch: vi.fn(),
  }),
}))

vi.mock('@/components/chat/ChatSidebar.vue', () => ({ default: stub }))
vi.mock('@/components/chat/ChatMessageList.vue', () => ({ default: listStub }))
vi.mock('@/components/chat/ChatInputArea.vue', () => ({ default: stub }))
vi.mock('@/components/common/UserMenu.vue', () => ({ default: stub }))
vi.mock('@/components/common/SettingsDialog.vue', () => ({ default: stub }))
vi.mock('@/components/common/HelpDialog.vue', () => ({ default: stub }))
vi.mock('@/components/common/DownloadDialog.vue', () => ({ default: stub }))
vi.mock('@/components/common/ReportDialog.vue', () => ({ default: stub }))
vi.mock('@/components/common/BranchPanel.vue', () => ({ default: stub }))

vi.mock('element-plus', () => ({
  ElMessage: { success: vi.fn(), error: vi.fn(), warning: vi.fn() },
  ElMessageBox: { prompt: vi.fn(), confirm: vi.fn() },
}))

async function mountChat() {
  const pinia = createPinia()
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{
      path: '/', component: ChatLayout,
      children: [
        { path: 'chat', component: stub },
        { path: 'knowledge', component: stub },
        { path: 'reports', component: stub },
      ],
    }],
  })
  router.push('/chat')
  await router.isReady()
  const wrapper = mount({ template: '<router-view />' }, { global: { plugins: [router, pinia] } })
  await flushPromises()
  await flushPromises()
  return wrapper
}

describe('ChatLayout 编辑重发的分支语义', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    sessionStorage.clear()
    sessionStorage.setItem('user', JSON.stringify({ username: '测试用户' }))
    sessionStorage.setItem('activeChatId:测试用户', '42')
    chatApiMock.listSessions.mockResolvedValue({
      data: { items: [{ id: 42, title: '三个问题', model: 'mock' }] },
    })
    // 三个提问：只有编辑第二个，第三个属于旧分支
    chatApiMock.getMessages.mockResolvedValue({
      data: [
        { id: 1, role: 'user', content: '问题一', created_at: '2026-01-01T00:00:00Z' },
        { id: 2, role: 'assistant', content: '答一', created_at: '2026-01-01T00:00:10Z' },
        { id: 3, role: 'user', content: '问题二', created_at: '2026-01-01T00:01:00Z' },
        { id: 4, role: 'assistant', content: '答二', created_at: '2026-01-01T00:01:10Z' },
        { id: 5, role: 'user', content: '问题三', created_at: '2026-01-01T00:02:00Z' },
        { id: 6, role: 'assistant', content: '答三', created_at: '2026-01-01T00:02:10Z' },
      ],
    })
    chatApiMock.sendMessageStream.mockResolvedValue(undefined)
    chatApiMock.updateMessage.mockResolvedValue({ data: {} })
  })

  it('编辑第二个问题后，第三个问题不再显示；切回旧版本又显示', async () => {
    const wrapper = await mountChat()
    const list = () => wrapper.findComponent(listStub).props('messages') as any[]

    expect(list().length).toBe(6)

    await wrapper.find('.edit-q2').trigger('click')
    await flushPromises()

    // 新分支停在第二个问题：第三个问题及其回答被隐藏（数据仍在内存里，切版本可回）
    expect(list().map(m => m.id)).toEqual(['1', '2', '3', '4'])

    // 提问版本被记下来，且新版本带分支起点标记
    const edited = list().find(m => m.id === '3')!
    expect(edited.versions.length).toBe(2)
    expect(edited.versions[1].truncates).toBeGreaterThan(0)

    await wrapper.find('.ver-1').trigger('click')
    await flushPromises()

    // 切回第一版：后续三个问题恢复可见
    expect(list().length).toBe(6)
  })
})
