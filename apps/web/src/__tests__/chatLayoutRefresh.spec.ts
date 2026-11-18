import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { createPinia } from 'pinia'

import { ElMessage } from 'element-plus'
import ChatLayout from '@/layouts/ChatLayout.vue'

/** 无 UI 组件桩：提供 scrollToBottom 等 ChatLayout 会调用的方法 */
const stub = vi.hoisted(() => ({
  template: '<div />',
  methods: { scrollToBottom() {} },
}))

vi.mock('@/api/client', () => ({ default: { get: vi.fn(), post: vi.fn() } }))

const chatApiMock = vi.hoisted(() => ({
  listSessions: vi.fn(),
  getMessages: vi.fn(),
  saveMessage: vi.fn(),
  createSession: vi.fn(),
  deleteSession: vi.fn(),
  updateSession: vi.fn(),
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
vi.mock('@/components/chat/ChatMessageList.vue', () => ({ default: stub }))
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

async function mountAt(path: string) {
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
  router.push(path)
  await router.isReady()

  const wrapper = mount({ template: '<router-view />' }, {
    global: { plugins: [router, pinia] },
  })
  await flushPromises()
  await flushPromises()
  return { wrapper, router }
}

describe('ChatLayout 刷新恢复会话', () => {
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
        { id: 1, role: 'user', content: '你好', created_at: '2026-01-01T00:00:00Z' },
        { id: 2, role: 'assistant', content: '在', created_at: '2026-01-01T00:00:01Z' },
      ],
    })
  })

  it('在知识库页刷新：停留在知识库页，同时恢复最近对话的消息', async () => {
    const { router } = await mountAt('/knowledge')

    expect(chatApiMock.getMessages).toHaveBeenCalledWith(42)
    expect(router.currentRoute.value.path).toBe('/knowledge')
  })

  it('在诊断报告页刷新：停留在诊断报告页', async () => {
    const { router } = await mountAt('/reports')

    expect(router.currentRoute.value.path).toBe('/reports')
  })

  it('在对话页刷新：仍停在对话页并恢复消息', async () => {
    const { router } = await mountAt('/chat')

    expect(chatApiMock.getMessages).toHaveBeenCalledWith(42)
    expect(router.currentRoute.value.path).toBe('/chat')
  })

  it('上次会话已不在列表中：不发起消息请求，并清除恢复状态', async () => {
    chatApiMock.listSessions.mockResolvedValue({ data: { items: [] } })

    await mountAt('/chat')

    expect(chatApiMock.getMessages).not.toHaveBeenCalled()
    expect(sessionStorage.getItem('activeChatId:测试用户')).toBeNull()
  })

  it('会话存在但消息接口 404：静默清理，不弹错误提示', async () => {
    chatApiMock.getMessages.mockRejectedValue({
      response: { status: 404, data: { detail: '会话不存在' } },
    })

    await mountAt('/chat')

    expect(sessionStorage.getItem('activeChatId:测试用户')).toBeNull()
    expect(ElMessage.error).not.toHaveBeenCalled()
  })
})
