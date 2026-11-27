import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { createPinia } from 'pinia'

import ChatLayout from '@/layouts/ChatLayout.vue'

/** 无 UI 组件桩：提供 scrollToBottom 等 ChatLayout 会调用的方法 */
const stub = vi.hoisted(() => ({
  template: '<div />',
  methods: { scrollToBottom() {} },
}))

/** 消息列表桩：暴露 messages，并用按钮触发「重新生成」（等同于点击回答下方按钮） */
const listStub = vi.hoisted(() => ({
  props: ['messages'],
  emits: ['regenerate'],
  template: `
    <div class="list-stub">
      <button class="regen-btn" @click="$emit('regenerate', messages[1])">重新生成</button>
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
  useUserStore: () => ({
    userName: '测试用户',
    isAdmin: false,
    user: null,
    logout: vi.fn(),
  }),
}))

vi.mock('@/utils/export', () => ({ exportChat: vi.fn() }))

vi.mock('@/composables/useChatBranch', () => ({
  useChatBranch: () => ({
    state: { currentBranchId: 'main' },
    currentBranch: null,
    branchCount: 1,
    createBranch: vi.fn(),
    switchBranch: vi.fn(),
    getBranches: () => [],
    reset: vi.fn(),
    deleteBranch: vi.fn(),
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
    routes: [
      {
        path: '/',
        component: ChatLayout,
        children: [
          { path: 'chat', component: stub },
          { path: 'knowledge', component: stub },
          { path: 'reports', component: stub },
        ],
      },
    ],
  })
  router.push('/chat')
  await router.isReady()

  const wrapper = mount({ template: '<router-view />' }, {
    global: { plugins: [router, pinia] },
  })
  await flushPromises()
  await flushPromises()
  return wrapper
}

describe('ChatLayout 重新生成', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    sessionStorage.clear()
    sessionStorage.setItem('user', JSON.stringify({ username: '测试用户' }))
    sessionStorage.setItem('activeChatId:测试用户', '42')
    chatApiMock.listSessions.mockResolvedValue({
      data: { items: [{ id: 42, title: '测试对话', model: 'mock' }] },
    })
    chatApiMock.getMessages.mockResolvedValue({
      data: [
        { id: 1, role: 'user', content: '为什么报超速', created_at: '2026-01-01T00:00:00Z' },
        { id: 2, role: 'assistant', content: '旧回答', created_at: '2026-01-01T00:00:01Z' },
      ],
    })
    chatApiMock.sendMessageStream.mockResolvedValue(undefined)
    chatApiMock.updateMessage.mockResolvedValue({ data: {} })
  })

  it('在原有消息上生成新版本，而不是删掉旧消息再插一条', async () => {
    const wrapper = await mountChat()

    await wrapper.find('.regen-btn').trigger('click')
    await flushPromises()

    // 关键回归点：旧回答所在的那一行被复用（updateMessage 带 active_version=1），
    // 而不是 insert 一条新消息 —— 否则切走会话再回来旧回答会“复活”。
    const resetCall = chatApiMock.updateMessage.mock.calls.find(
      ([, msgId, body]) => msgId === 2 && body?.active_version === 1,
    )
    expect(resetCall).toBeTruthy()
    expect(resetCall![2].content).toBe('')

    // 重新生成仍然是对同一条用户提问发起的
    expect(chatApiMock.sendMessageStream).toHaveBeenCalledTimes(1)
    expect(chatApiMock.sendMessageStream.mock.calls[0][1]).toBe('为什么报超速')

    // 没有新增消息行（saveMessage 只可能在流式结束后按版本更新，不应新建回答）
    expect(chatApiMock.saveMessage).not.toHaveBeenCalled()
  })
})
