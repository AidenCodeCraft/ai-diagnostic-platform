<template>
  <div class="chat-layout">
    <!-- 左侧边栏 -->
    <ChatSidebar v-model:collapsed="sidebarCollapsed" :chats="recentChats"
      :activeChatId="isChatRoute ? currentChatId : 0"
      :userName="userName" :userInitial="userInitial" :isAdmin="userStore.isAdmin" @toggleSearch="toggleSearch"
      @newChat="newChat" @navigate="navigateTo" @selectChat="selectChat" @chatMenu="openChatMenu"
      @toggleUserMenu="showUserMenu = !showUserMenu" />

    <button v-if="sidebarCollapsed" class="float-open-btn" @click="sidebarCollapsed = false" title="展开侧栏">
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <rect x="3" y="3" width="18" height="18" rx="2" />
        <path d="M9 3v18" />
      </svg>
    </button>

    <!-- 用户菜单 -->
    <UserMenu :visible="showUserMenu" @close="showUserMenu = false" @action="handleUserAction" />

    <!-- 对话菜单 -->
    <teleport to="body">
      <div v-if="chatMenu.visible" class="menu-overlay" @click="closeChatMenu"></div>
      <div v-if="chatMenu.visible" class="chat-menu-popup" :style="{ top: chatMenu.y + 'px', left: chatMenu.x + 'px' }">
        <button @click="renameChat">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M17 3a2.83 2.83 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5Z" />
          </svg> 重命名
        </button>
        <button @click="pinChat">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <line x1="12" y1="5" x2="12" y2="19" />
            <polyline points="19 12 12 19 5 12" />
          </svg> 置顶
        </button>
        <button @click="analyzeChat">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <polyline points="22 12 18 12 15 21 9 3 6 12 2 12" />
          </svg> 分析
        </button>
        <hr />
        <button class="danger" @click="deleteChat">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <polyline points="3 6 5 6 21 6" />
            <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
          </svg> 删除
        </button>
      </div>
    </teleport>

    <!-- 设置弹窗 -->
    <SettingsDialog :visible="showSettings" :userName="userName" @close="showSettings = false"
      @changePassword="changePwd" @clearData="clearData" />

    <!-- ============================================================ -->
    <!-- 对话主区域                                                    -->
    <!-- ============================================================ -->
    <main class="chat-main">
      <template v-if="$route.path === '/chat' || $route.path === '/'">
        <div class="chat-content" :class="{ 'chat-empty': displayMessages.length === 0 }">
          <ChatMessageList ref="msgListRef" :key="'cl-' + currentChatId + '-' + displayMessages.length"
            :messages="displayMessages" :loading="loading" :isEmpty="displayMessages.length === 0"
            @previewFile="previewFile" @openKnowledge="openKnowledge" />
          <div class="input-wrapper">
            <ChatInputArea v-model="inputText" :files="attachedFiles" :selectedModel="selectedModel"
              :isUploading="isUploading" :canReport="canGenerateReport" :hasMessages="messages.length > 0"
              @send="sendMessage" @fileInput="onFileInput" @removeFile="removeFile" @modelChange="onModelChange"
              @generateReport="generateDiagnosticReport" />
          </div>
        </div>
      </template>
      <template v-else>
        <div class="sub-page">
          <router-view />
        </div>
      </template>
    </main>

    <!-- 文件预览弹窗 -->
    <el-dialog v-model="previewVisible" :title="previewName" width="700px" top="5vh">
      <pre class="file-preview-content">{{ previewContent }}</pre>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted, reactive, nextTick } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import client from '@/api/client'
import { chatApi, type ChatSource } from '@/api/chat'
import { useUserStore } from '@/stores/user'

import ChatSidebar from '@/components/chat/ChatSidebar.vue'
import ChatMessageList from '@/components/chat/ChatMessageList.vue'
import ChatInputArea from '@/components/chat/ChatInputArea.vue'
import UserMenu from '@/components/common/UserMenu.vue'
import SettingsDialog from '@/components/common/SettingsDialog.vue'
import type { ChatRecord, FileAttachment, MsgAttachment } from '@/components/chat/types'

// ── State ──────────────────────────────────────────────────────

const router = useRouter()
const route = useRoute()
const userStore = useUserStore()

const isChatRoute = computed(() => route.path === '/chat' || route.path === '/')

// 诊断：路由变化时打印消息状态
watch(
  () => route.path,
  (path) => {
    console.log(
      `[route→${path}] messages=${messages.value.length} display=${displayMessages.value.length}`,
      messages.value.map((m: any) => `${m.role}:${(m.content || '').slice(0, 20)}`),
    )
  },
)

const sidebarCollapsed = ref(false)
const selectedModel = ref(localStorage.getItem('selectedModel') || 'mock')
const inputText = ref('')
const loading = ref(false)
const messages = ref<any[]>([])
const currentChatId = ref(0)
const canGenerateReport = ref(false)
const lastAnalysis = ref<any>(null)

// 去重 + 按 createdAt 升序
const displayMessages = computed(() => {
  const seen = new Set<string>()
  return [...messages.value]
    .filter(m => {
      const hash = `${m.role}|${(m.content || '').slice(0, 200)}`
      if (seen.has(hash)) return false
      seen.add(hash)
      return true
    })
    .sort((a, b) => (a.createdAt || 0) - (b.createdAt || 0))
})
const messageIds = new Set<string>()

const attachedFiles = ref<FileAttachment[]>([])
const showUserMenu = ref(false)
const showSettings = ref(false)

const recentChats = ref<ChatRecord[]>([])
const chatMenu = reactive({ visible: false, x: 0, y: 0, chatId: 0 })

const msgListRef = ref<InstanceType<typeof ChatMessageList>>()

const isUploading = computed(() => attachedFiles.value.some(f => f.status === 'uploading'))
const userName = computed(() => userStore.userName)
const userInitial = computed(() => userName.value.charAt(0).toUpperCase())

// ── UI Actions ────────────────────────────────────────────────

function toggleSearch() { /* placeholder */ }
function navigateTo(path: string) { router.push(path) }
function openKnowledge(source: { id?: number }) {
  router.push(source.id ? `/knowledge?document=${source.id}` : '/knowledge')
}
function onModelChange(model: string) { selectedModel.value = model; localStorage.setItem('selectedModel', model) }

function handleUserAction(action: 'download' | 'settings' | 'help' | 'logout') {
  switch (action) {
    case 'settings': showSettings.value = true; break
    case 'logout': userStore.logout(); router.push('/login'); break
    case 'download': ElMessage.info('桌面版下载页面开发中'); break
    case 'help': ElMessage.info('帮助文档开发中'); break
  }
}

async function changePwd() {
  try {
    const { value } = await ElMessageBox.prompt('请输入新密码', '修改密码', { inputType: 'password' })
    if (value) ElMessage.success('密码修改成功')
  } catch { /* cancelled */ }
}

async function clearData() {
  try {
    await ElMessageBox.confirm('确定清除所有对话数据？不可恢复。', '确认', { type: 'warning' })
    await Promise.all(recentChats.value.map(c => chatApi.deleteSession(c.id).catch(() => { })))
    recentChats.value = []
    messages.value = []
    currentChatId.value = 0
    ElMessage.success('已清除')
    showSettings.value = false
  } catch { /* cancelled */ }
}

// ── Session Management ────────────────────────────────────────

async function loadSessions() {
  try {
    const { data } = await chatApi.listSessions()
    recentChats.value = data.items.map((s: any) => ({ id: s.id, title: s.title || '新对话', model: s.model }))
  } catch { /* ignore */ }
}

async function newChat() {
  messages.value = []
  messageIds.clear()
  currentChatId.value = 0
  sessionStorage.removeItem('activeChatId')
  canGenerateReport.value = false
  lastAnalysis.value = null
  inputText.value = ''
  attachedFiles.value = []
  router.push('/chat')
}

async function selectChat(id: number) {
  // 已有完整本地消息时跳过；刷新后 messages 为空，必须重新拉取。
  if (id === currentChatId.value && messages.value.length > 0) {
    router.push('/chat')
    return
  }

  try {
    loading.value = true
    const { data } = await chatApi.getMessages(id)
    const msgs = Array.isArray(data) ? data : []
    
    console.log(`[selectChat] id=${id} loaded ${msgs.length} messages`, msgs)
    
    messageIds.clear()
    currentChatId.value = id
    messages.value = msgs.map((m: any) => ({
      id: m.id.toString(),
      role: m.role,
      content: m.content || '',
      createdAt: m.created_at ? new Date(m.created_at).getTime() : Date.now(),
      files: extractFiles(m),
      sources: m.sources || [],
    }))
    messages.value.forEach((m: any) => messageIds.add(m.id))
    sessionStorage.setItem('activeChatId', String(id))
    
    // 检查是否有日志分析结果，如果有则可以生成报告
    const hasAnalysis = msgs.some((m: any) => 
      m.role === 'assistant' && m.content && m.content.includes('诊断结果')
    )
    canGenerateReport.value = hasAnalysis
    
    router.push('/chat')
    loading.value = false
    
    // 等待DOM更新后滚动到底部
    await nextTick()
    setTimeout(() => msgListRef.value?.scrollToBottom(), 150)
  } catch (err: any) {
    console.error('[selectChat] error:', err)
    ElMessage.error('加载对话失败: ' + (err.response?.data?.detail || err.message))
    loading.value = false
  }
}

function extractFiles(m: any): MsgAttachment[] | undefined {
  if (m.role !== 'user') return undefined
  const match = m.content.match(/\[上传文件:\s*(.+?)\]/)
  if (!match) return undefined
  return match[1].split(/,\s*/).map((entry: string) => {
    const sizeMatch = entry.match(/^(.+?)\s*\((.+?)\)$/)
    const name = sizeMatch ? sizeMatch[1].trim() : entry.trim()
    const sizeStr = sizeMatch ? sizeMatch[2] : '0 B'
    const size = parseFloat(sizeStr) * (sizeStr.includes('KB') ? 1024 : sizeStr.includes('MB') ? 1048576 : 1) || 0
    return { name, size, type: name.split('.').pop() || 'log' }
  })
}

function openChatMenu(e: MouseEvent, chat: ChatRecord) {
  chatMenu.visible = true
  chatMenu.x = e.clientX - 8
  chatMenu.y = e.clientY + 4
  chatMenu.chatId = chat.id
}

function closeChatMenu() { chatMenu.visible = false }

async function renameChat() {
  const chat = recentChats.value.find(c => c.id === chatMenu.chatId)
  if (!chat) return
  try {
    const { value } = await ElMessageBox.prompt('新标题', '重命名', { inputValue: chat.title })
    if (value?.trim()) {
      chat.title = value.trim()
      await chatApi.updateSession(chat.id, value.trim())
    }
  } catch { /* cancelled */ }
  closeChatMenu()
}

function pinChat() {
  const idx = recentChats.value.findIndex(c => c.id === chatMenu.chatId)
  if (idx > 0) {
    const [item] = recentChats.value.splice(idx, 1)
    recentChats.value.unshift(item)
  }
  closeChatMenu()
}

function analyzeChat() { ElMessage.info('分析功能开发中'); closeChatMenu() }

async function deleteChat() {
  try {
    await ElMessageBox.confirm('删除后，该对话将不可恢复', '确认删除', {
      confirmButtonText: '删除该对话', cancelButtonText: '取消', type: 'warning',
    })
    await chatApi.deleteSession(chatMenu.chatId)
    recentChats.value = recentChats.value.filter(c => c.id !== chatMenu.chatId)
    if (currentChatId.value === chatMenu.chatId) {
      messages.value = []
      currentChatId.value = 0
      sessionStorage.removeItem('activeChatId')
    }
  } catch { /* cancelled */ }
  closeChatMenu()
}

// ── File Handling ─────────────────────────────────────────────

function onFileInput(e: Event) {
  const t = e.target as HTMLInputElement
  if (t.files) {
    for (let i = 0; i < t.files.length; i++) {
      const f = t.files[i]
      attachedFiles.value.push({
        id: Date.now().toString() + i,
        file: f,
        name: f.name,
        progress: 0,
        status: 'pending',
      })
    }
  }
  t.value = ''
}

function removeFile(id: string) {
  attachedFiles.value = attachedFiles.value.filter(f => f.id !== id)
}

const previewVisible = ref(false)
const previewContent = ref('')
const previewName = ref('')

async function previewFile(f: MsgAttachment) {
  previewName.value = f.name
  previewContent.value = '加载中...'
  previewVisible.value = true

  const found = attachedFiles.value.find(af => af.name === f.name)
  if (found) {
    const reader = new FileReader()
    reader.onload = (e) => {
      previewContent.value = (e.target?.result as string) || '无法读取文件内容'
    }
    reader.readAsText(found.file.slice(0, 50000))
  } else {
    previewContent.value = '该附件已不在当前会话中，无法预览。'
  }
}

// ── Chat / Send Message ──────────────────────────────────────

async function sendMessage() {
  const text = inputText.value.trim()
  const files = [...attachedFiles.value]
  if (!text) return

  const isNewChat = !currentChatId.value
  inputText.value = ''
  attachedFiles.value = []

  if (isNewChat) {
    try {
      const { data: s } = await chatApi.createSession(text.slice(0, 30) || '新对话', selectedModel.value)
      currentChatId.value = s.id
      sessionStorage.setItem('activeChatId', String(s.id))
      recentChats.value.unshift({ id: s.id, title: s.title || text.slice(0, 30), model: s.model || undefined })
    } catch { /* fallback */ }
  }

  const attachments: MsgAttachment[] = files.map(f => ({
    name: f.name,
    size: f.file.size,
    type: f.file.type || f.name.split('.').pop() || '',
  }))

  const fileTag = files.length
    ? `[上传文件: ${files.map(f => `${f.name} (${formatSizeStr(f.file.size)})`).join(', ')}]`
    : ''
  const userMsg = fileTag ? `${text}\n${fileTag}` : text
  addMessage('user', userMsg, attachments)

  // 用户消息先持久化，确保刷新后 selectChat 能恢复完整历史
  if (currentChatId.value) {
    try {
      await chatApi.saveMessage(currentChatId.value, 'user', userMsg)
    } catch {
      ElMessage.warning('用户消息保存失败，刷新后可能无法恢复')
    }
  }
  loading.value = true

  try {
    if (files.length > 0) {
      await processFiles(files, userMsg)
    } else if (userMsg) {
      await streamChat(userMsg)
    }
  } catch (e: any) {
    addMessage('assistant', `❌ 分析失败：${e.response?.data?.detail || e.message}`)
  } finally {
    loading.value = false
  }
}

async function processFiles(files: FileAttachment[], text: string) {
  for (const fa of files) {
    fa.status = 'uploading'
    const fd = new FormData()
    fd.append('file', fa.file)
    fd.append('description', text)

    try {
      const resp = await client.post('/logs/upload', fd, {
        headers: { 'Content-Type': 'multipart/form-data' },
        onUploadProgress: (e) => {
          if (e.total) fa.progress = Math.round((e.loaded / e.total) * 100)
        },
      })
      fa.progress = 100
      fa.status = 'parsing'
      const logId = resp.data.id

      const analysisStartedAt = Date.now()
      const pId = analysisStartedAt.toString()
      messageIds.add(pId)
      messages.value.push({
        id: pId,
        role: 'assistant',
        content: '',
        createdAt: analysisStartedAt,
        thinking: {
          elapsed: 0,
          active: true,
          text: '正在读取日志文件并提取关键事件…',
        },
        sources: [] as ChatSource[],
      })
      const processingMsg = messages.value[messages.value.length - 1]

      const updateThinking = (text: string) => {
        processingMsg.thinking.text = text
        processingMsg.thinking.elapsed = Math.max(1, Math.round((Date.now() - analysisStartedAt) / 1000))
        msgListRef.value?.scrollToBottom()
      }

      try {
        updateThinking('正在解析日志文件，提取结构化事件…')

        const analysisRes = await chatApi.runAnalysis(logId, selectedModel.value)
        if (analysisRes.data?.id) {
          updateThinking('日志解析完成，正在匹配错误模式并检索相关知识…')

          const detail = (await chatApi.getAnalysisResult(analysisRes.data.id)).data
          lastAnalysis.value = detail
          const confidence = ((detail.confidence || 0) * 100).toFixed(0)
          const sources = detail.sources || detail.knowledge_sources || detail.references || []

          const response = [
            `## ${fa.name} 的诊断结果`,
            '',
            '### 诊断摘要',
            detail.summary || '分析完成',
            '',
            '### 根因分析',
            detail.root_cause || '根因待确认',
            '',
            `诊断置信度：**${confidence}%**`,
            '',
            '### 建议措施',
            ...(detail.next_steps || []).map((s: string, i: number) => `${i + 1}. ${s}`),
          ].join('\n')

          processingMsg.content = response
          processingMsg.sources = sources
          processingMsg.thinking.elapsed = Math.max(1, Math.round((Date.now() - analysisStartedAt) / 1000))
          processingMsg.thinking.active = false
          canGenerateReport.value = true
          fa.status = 'done'
          await chatApi.saveMessage(currentChatId.value, 'assistant', response, sources).catch(() => { })
        }
      } catch (e: any) {
        processingMsg.content = `❌ 分析 \`${fa.name}\` 失败：${e.response?.data?.detail || e.message}`
        processingMsg.thinking.elapsed = Math.max(1, Math.round((Date.now() - analysisStartedAt) / 1000))
        processingMsg.thinking.active = false
        fa.status = 'error'
        fa.error = e.response?.data?.detail || e.message
      }
      msgListRef.value?.scrollToBottom()
    } catch (e: any) {
      fa.status = 'error'
      fa.error = e.response?.data?.detail || e.message
      addMessage('assistant', `❌ 上传 \`${fa.name}\` 失败：${e.response?.data?.detail || e.message}`)
    }
  }
}

async function streamChat(text: string) {
  loading.value = false
  const thinkStart = Date.now()
  const aId = thinkStart.toString()
  messageIds.add(aId)
  const assistantMsg: any = {
    id: aId, role: 'assistant', content: '', createdAt: thinkStart,
    thinking: { elapsed: 0, text: '', active: true }, sources: [] as ChatSource[],
  }
  messages.value.push(assistantMsg)
  const replyMsg = messages.value[messages.value.length - 1]

  let firstToken = true

  await chatApi.sendMessageStream(
    currentChatId.value,
    text,
    selectedModel.value,
    (token: string) => {
      if (firstToken) {
        firstToken = false
        const elapsed = Math.max(1, Math.round((Date.now() - thinkStart) / 1000))
        replyMsg.thinking.elapsed = elapsed
        replyMsg.thinking.active = false
      }
      replyMsg.content += token
      msgListRef.value?.scrollToBottom()
    },
    (_model: string) => {
      const chat = recentChats.value.find(c => c.id === currentChatId.value)
      if (chat && chat.title === '新对话') chat.title = text.slice(0, 30)
      replyMsg.thinking.elapsed = Math.max(1, Math.round((Date.now() - thinkStart) / 1000))
      replyMsg.thinking.active = false
      msgListRef.value?.scrollToBottom()
    },
    (err: string) => {
      replyMsg.content = '❌ 流式回复失败：' + err
    },
    lastAnalysis.value,
    (reasoning: string) => {
      replyMsg.thinking.text += reasoning
      replyMsg.thinking.elapsed = Math.max(1, Math.round((Date.now() - thinkStart) / 1000))
      replyMsg.thinking.active = true
    },
    (sources: ChatSource[]) => { replyMsg.sources = sources },
  )
}

function addMessage(role: string, content: string, files?: MsgAttachment[]) {
  const duplicate = messages.value.find(
    m => m.role === role && m.content && m.content.slice(0, 100) === content.slice(0, 100)
  )
  if (duplicate) return

  const id = Date.now().toString()
  if (messageIds.has(id)) return
  messageIds.add(id)

  messages.value.push({
    id,
    role: role as any,
    content,
    createdAt: Date.now(),
    files,
  } as any)
  setTimeout(() => msgListRef.value?.scrollToBottom(), 50)
}

function formatSizeStr(bytes: number): string {
  if (bytes < 1024) return bytes + ' B'
  if (bytes < 1048576) return (bytes / 1024).toFixed(1) + ' KB'
  return (bytes / 1048576).toFixed(1) + ' MB'
}

async function generateDiagnosticReport() {
  ElMessage.info('报告生成功能开发中')
}

onMounted(() => {
  selectedModel.value = localStorage.getItem('selectedModel') || 'mock'
  const savedChatId = sessionStorage.getItem('activeChatId')
  if (savedChatId) {
    const id = parseInt(savedChatId, 10)
    if (!isNaN(id) && id > 0) {
      selectChat(id).catch(() => { currentChatId.value = 0 })
    }
  }
  loadSessions()  // 始终加载侧边栏列表，不与自动恢复互斥
})
</script>

<style scoped>
.chat-layout {
  display: flex;
  height: 100vh;
  background: var(--chat-layout-bg);
  color: var(--chat-layout-text);
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
}

.float-open-btn {
  position: fixed;
  left: 12px;
  top: 12px;
  z-index: 50;
  width: 36px;
  height: 36px;
  border-radius: 50%;
  border: 1px solid var(--chat-float-btn-border);
  background: var(--chat-float-btn-bg);
  color: var(--chat-float-btn-text);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
  transition: all 0.15s;
}

.float-open-btn:hover {
  background: var(--chat-float-btn-hover-bg);
  color: var(--chat-float-btn-hover-text);
}

.menu-overlay {
  position: fixed;
  inset: 0;
  z-index: 99;
}

.chat-menu-popup {
  position: fixed;
  z-index: 100;
  background: var(--chat-popup-bg);
  border: 1px solid var(--chat-popup-border);
  border-radius: 10px;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.12);
  padding: 4px;
  min-width: 160px;
  animation: menuIn 0.12s ease;
}

@keyframes menuIn {
  from {
    opacity: 0;
    transform: translateY(-4px);
  }

  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.chat-menu-popup button {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  padding: 8px 12px;
  border: none;
  background: transparent;
  font-size: 13px;
  color: var(--chat-popup-text);
  cursor: pointer;
  border-radius: 6px;
  transition: background 0.1s;
}

.chat-menu-popup button:hover {
  background: var(--chat-popup-hover);
}

.chat-menu-popup button.danger:hover {
  background: var(--chat-popup-danger-hover-bg);
  color: var(--chat-popup-danger-hover-text);
}

.chat-menu-popup hr {
  margin: 4px 0;
  border: none;
  border-top: 1px solid var(--chat-popup-border);
}

.chat-main {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
  position: relative;
  overflow: hidden;
  background: var(--chat-main-bg);
}

.sub-page {
  flex: 1;
  overflow-y: auto;
  display: flex;
  justify-content: center;
}

.chat-content {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-height: 0;
}

/* 无对话时，提示语 + 输入框居中 */
.chat-content.chat-empty {
  justify-content: center;
  align-items: center;
}

.input-wrapper {
  display: flex;
  justify-content: center;
  padding: 12px 24px 20px;
  width: 100%;
  box-sizing: border-box;
}

.file-preview-content {
  max-height: 60vh;
  overflow: auto;
  padding: 16px;
  background: #1e293b;
  color: #e2e8f0;
  border-radius: 8px;
  font-size: 13px;
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-all;
}
</style>
