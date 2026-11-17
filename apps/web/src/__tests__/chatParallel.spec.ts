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

/** ChatMessageList 桩：渲染消息内容，便于断言输出归属哪个对话 */
const messageListStub = vi.hoisted(() => ({
  props: ['messages', 'loading', 'isEmpty', 'chatId'],
  template: '<div class="mlist">{{ messages.map(m => m.content).join("|") }}</div>',
  methods: { scrollToBottom() {} },
}))

/** ChatSidebar 桩：按钮触发会话切换 */
const sidebarStub = vi.hoisted(() => ({
  props: ['chats', 'activeChatId'],
  emits: ['selectChat', 'newChat', 'toggleSearch', 'navigate', 'chatMenu', 'toggleUserMenu', 'searchChats'],
  template: '<div><button v-for="c in chats" :key="c.id" class="side" @click="$emit(\'selectChat\', c.id)">{{ c.title }}</button></div>',
}))

/** ChatInputArea 桩：模拟输入并发送 */
const inputStub = vi.hoisted(() => ({
  props: ['modelValue', 'isStreaming'],
  emits: ['update:modelValue', 'send', 'stop'],
  template: '<div><button class="fill" @click="$emit(\'update:modelValue\', \'问题\')">输入</button><button v-if="isStreaming" class="stop" @click="$emit(\'stop\')">停止</button><button v-else class="send" @click="$emit(\'send\')">发送</button></div>',
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

const adminApiMock = vi.hoisted(() => ({
  updateUser: vi.fn(),
  getSystemConfig: vi.fn(),
}))
vi.mock('@/api/admin', () => ({ adminApi: adminApiMock }))

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

vi.mock('@/components/chat/ChatSidebar.vue', () => ({ default: sidebarStub }))
vi.mock('@/components/chat/ChatMessageList.vue', () => ({ default: messageListStub }))
vi.mock('@/components/chat/ChatInputArea.vue', () => ({ default: inputStub }))
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

/** 按会话捕获 sendMessageStream 的回调（onDone/onError 包装为触发后结束等待，模拟真实 chat.ts） */
const streams = vi.hoisted(() => new Map<number, {
  content: string
  onToken: (t: string) => void
  onDone: (m: string) => void
  onError: (e: string) => void
}>())

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
  return wrapper
}

async function sendInCurrentChat(wrapper: any) {
  await wrapper.find('.fill').trigger('click')
  await wrapper.find('.send').trigger('click')
  await flushPromises()
}

describe('多对话并行提问', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    sessionStorage.clear()
    sessionStorage.setItem('activeChatId', '1')
    streams.clear()
    chatApiMock.listSessions.mockResolvedValue({
      data: {
        items: [
          { id: 1, title: '对话一', model: 'mock' },
          { id: 2, title: '对话二', model: 'mock' },
        ],
      },
    })
    chatApiMock.getMessages.mockResolvedValue({ data: [] })
    chatApiMock.saveMessage.mockResolvedValue({ data: {} })
    chatApiMock.sendMessageStream.mockImplementation(
      (
        sessionId: number, content: string, _model: string,
        onToken: (t: string) => void, onDone: (m: string) => void, onError: (e: string) => void,
        _logAnalysis: any, _onReasoning: any, _onSources: any, _onClarification: any,
        onStopped?: () => void, signal?: AbortSignal,
      ) => {
        // 流持续进行中，直到完成/出错/停止（模拟真实 chat.ts 的 promise 语义）
        let resolveFn: () => void = () => {}
        const pending = new Promise<void>((res) => { resolveFn = res })
        streams.set(sessionId, {
          content,
          onToken,
          onDone: (m: string) => { onDone(m); resolveFn() },
          onError: (e: string) => { onError(e); resolveFn() },
        })
        signal?.addEventListener('abort', () => { onStopped?.(); resolveFn() })
        return pending
      },
    )
    adminApiMock.getSystemConfig.mockResolvedValue({
      data: { parallel_chat_enabled: true, max_parallel_chats: 3, max_online_users: 200 },
    })
  })

  it('两个对话同时提问：输出互不干扰，完成后各自保存到正确的会话', async () => {
    const wrapper = await mountChat()

    // 对话1 发起提问
    await sendInCurrentChat(wrapper)
    expect(chatApiMock.sendMessageStream.mock.calls.map(c => c[0])).toEqual([1])

    // 切换到对话2 再发起提问（并行开启）
    await wrapper.findAll('.side')[1].trigger('click')
    await flushPromises()
    await sendInCurrentChat(wrapper)
    expect(chatApiMock.sendMessageStream.mock.calls.map(c => c[0])).toEqual([1, 2])

    // 两个流分别向自己的对话写入输出
    streams.get(1)!.onToken('回复一')
    streams.get(2)!.onToken('回复二')
    await flushPromises()
    expect(wrapper.find('.mlist').text()).toContain('回复二')
    expect(wrapper.find('.mlist').text()).not.toContain('回复一')

    // 切回对话1：流式输出仍在（不被打断），且继续增长
    await wrapper.findAll('.side')[0].trigger('click')
    await flushPromises()
    expect(wrapper.find('.mlist').text()).toContain('回复一')
    streams.get(1)!.onToken('继续一')
    await flushPromises()
    expect(wrapper.find('.mlist').text()).toContain('继续一')

    // 流完成：各自保存到发起提问的会话
    streams.get(1)!.onDone('mock')
    streams.get(2)!.onDone('mock')
    await flushPromises()

    const save1 = chatApiMock.saveMessage.mock.calls.find(c => c[0] === 1 && c[1] === 'assistant')
    expect(save1?.[2]).toBe('回复一继续一')
    const save2 = chatApiMock.saveMessage.mock.calls.find(c => c[0] === 2 && c[1] === 'assistant')
    expect(save2?.[2]).toBe('回复二')
  })

  it('未开启多对话并行：另一对话不能同时发起提问', async () => {
    adminApiMock.getSystemConfig.mockResolvedValue({
      data: { parallel_chat_enabled: false, max_parallel_chats: 3, max_online_users: 200 },
    })
    const wrapper = await mountChat()

    await sendInCurrentChat(wrapper)
    expect(chatApiMock.sendMessageStream).toHaveBeenCalledTimes(1)

    // 切换到对话2 尝试发送：被并发保护拦截，不发起第二个流
    await wrapper.findAll('.side')[1].trigger('click')
    await flushPromises()
    await sendInCurrentChat(wrapper)
    expect(chatApiMock.sendMessageStream).toHaveBeenCalledTimes(1)
  })

  it('停止生成：中止当前对话的流并保存已生成的部分内容', async () => {
    const wrapper = await mountChat()
    await sendInCurrentChat(wrapper)
    streams.get(1)!.onToken('部分内容')
    await flushPromises()

    // 流式中输入区显示停止按钮，点击后中止
    await wrapper.find('.stop').trigger('click')
    await flushPromises()

    const save = chatApiMock.saveMessage.mock.calls.find(c => c[0] === 1 && c[1] === 'assistant')
    expect(save?.[2]).toBe('部分内容')

    // 停止后可再次发起提问
    await sendInCurrentChat(wrapper)
    expect(chatApiMock.sendMessageStream.mock.calls.length).toBe(2)
  })

  it('流式出错：保留已生成内容并追加中断提示', async () => {
    const wrapper = await mountChat()
    await sendInCurrentChat(wrapper)
    streams.get(1)!.onToken('部分内容')
    streams.get(1)!.onError('boom')
    await flushPromises()

    const text = wrapper.find('.mlist').text()
    expect(text).toContain('部分内容')
    expect(text).toContain('流式回复中断')
  })

  it('并行开启但超过上限：提示并拦截', async () => {
    adminApiMock.getSystemConfig.mockResolvedValue({
      data: { parallel_chat_enabled: true, max_parallel_chats: 1, max_online_users: 200 },
    })
    const wrapper = await mountChat()

    await sendInCurrentChat(wrapper)
    expect(chatApiMock.sendMessageStream).toHaveBeenCalledTimes(1)

    await wrapper.findAll('.side')[1].trigger('click')
    await flushPromises()
    await sendInCurrentChat(wrapper)
    expect(chatApiMock.sendMessageStream).toHaveBeenCalledTimes(1)
  })
})
