<template>
  <div class="chat-layout">
    <!-- 左侧边栏 -->
    <ChatSidebar v-model:collapsed="sidebarCollapsed" :chats="filteredChats" :loading="sessionsLoading"
      :activeChatId="isChatRoute ? currentChatId : 0"
      :userName="userName" :userInitial="userInitial" :isAdmin="isAdmin" @toggleSearch="toggleSearch"
      @newChat="newChat" @navigate="navigateTo" @selectChat="selectChat" @chatMenu="openChatMenu"
      @toggleUserMenu="showUserMenu = !showUserMenu" @searchChats="onSearchChats" />

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
        <button @click="exportChat">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
            <polyline points="7 10 12 15 17 10"/>
            <line x1="12" y1="15" x2="12" y2="3"/>
          </svg> 导出
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

    <!-- 帮助与反馈弹窗 -->
    <HelpDialog :visible="showHelp" @close="showHelp = false" />

    <!-- 下载客户端弹窗 -->
    <DownloadDialog :visible="showDownload" @close="showDownload = false" />

    <!-- 生成诊断报告弹窗 -->
    <ReportDialog
      :visible="showReportDialog"
      :messages="selectableMessages"
      :chatTitle="currentChatTitle"
      :model="selectedModel"
      @close="showReportDialog = false"
      @generate="onReportGenerate"
    />

    <!-- ============================================================ -->
    <!-- 对话主区域                                                    -->
    <!-- ============================================================ -->
    <main class="chat-main">
      <template v-if="$route.path === '/chat' || $route.path === '/'">
        <div class="chat-content" :class="{ 'chat-empty': displayMessages.length === 0 }">
          <!-- 分支面板 -->
          <BranchPanel
            v-if="branchCount > 1"
            :branches="branchList"
            :current-branch-id="currentBranchId"
            @switch="onBranchSwitch"
            @delete="onBranchDelete"
          />
          <ChatMessageList ref="msgListRef" :key="'cl-' + currentChatId + '-' + displayMessages.length"
            :messages="displayMessages" :loading="loadingPhase !== 'idle'" :isEmpty="displayMessages.length === 0"
            :chatId="currentChatId"
            @previewFile="previewFile" @openKnowledge="openKnowledge" @regenerate="handleRegenerate" @editMessage="handleEditMessage" />
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
import { adminApi } from '@/api/admin'
import { useUserStore } from '@/stores/user'
import { exportChat as exportChatUtil } from '@/utils/export'
import type { ExportMessage } from '@/utils/export'

import ChatSidebar from '@/components/chat/ChatSidebar.vue'
import ChatMessageList from '@/components/chat/ChatMessageList.vue'
import ChatInputArea from '@/components/chat/ChatInputArea.vue'
import UserMenu from '@/components/common/UserMenu.vue'
import SettingsDialog from '@/components/common/SettingsDialog.vue'
import HelpDialog from '@/components/common/HelpDialog.vue'
import DownloadDialog from '@/components/common/DownloadDialog.vue'
import ReportDialog from '@/components/common/ReportDialog.vue'
import BranchPanel from '@/components/common/BranchPanel.vue'
import type { ChatRecord, FileAttachment, MsgAttachment } from '@/components/chat/types'
import { useChatBranch } from '@/composables/useChatBranch'

// ── State ──────────────────────────────────────────────────────

const router = useRouter()
const route = useRoute()
const userStore = useUserStore()

const isChatRoute = computed(() => route.path === '/chat' || route.path === '/')

// 诊断：路由变化时打印消息状态（仅开发模式）
watch(
  () => route.path,
  (path) => {
    if (import.meta.env.DEV) {
      console.log(
        `[route→${path}] messages=${messages.value.length} display=${displayMessages.value.length}`,
        messages.value.map((m: any) => `${m.role}:${(m.content || '').slice(0, 20)}`),
      )
    }
  },
)

const sidebarCollapsed = ref(false)
const selectedModel = ref(localStorage.getItem('selectedModel') || 'deepseek-v4-flash')
const inputText = ref('')
const loadingPhase = ref<'idle' | 'sending' | 'uploading' | 'streaming' | 'analyzing'>('idle')
const isSending = ref(false)
const messages = ref<any[]>([])
const currentChatId = ref(0)
const canGenerateReport = ref(false)
const lastAnalysis = ref<any>(null)

// 按 createdAt 升序排列，使用 ID 去重（而非内容去重）
const displayMessages = computed(() => {
  const seen = new Set<string>()
  return [...messages.value]
    .filter(m => {
      // 使用消息 ID 去重，而不是内容哈希
      // 这样即使内容相同，只要是不同的消息实例也能正常显示
      if (seen.has(m.id)) return false
      seen.add(m.id)
      return true
    })
    .sort((a, b) => (a.createdAt || 0) - (b.createdAt || 0))
})
const messageIds = new Set<string>()

const attachedFiles = ref<FileAttachment[]>([])
const showUserMenu = ref(false)
const showSettings = ref(false)
const showHelp = ref(false)
const showDownload = ref(false)
const showReportDialog = ref(false)

// ── 分支管理 ────────────────────────────────────────────────
const { state: branchState, currentBranch, branchCount, createBranch, switchBranch, getBranches, reset: resetBranches, deleteBranch: removeBranch } = useChatBranch()

const branchList = computed(() => getBranches())
const currentBranchId = computed(() => branchState.currentBranchId)

function onBranchSwitch(branchId: string) {
  const saved = switchBranch(branchId)
  if (saved) {
    messages.value = saved
    messageIds.clear()
    messages.value.forEach((m: any) => messageIds.add(m.id))
  }
}

function onBranchDelete(branchId: string) {
  removeBranch(branchId)
}

/** 供报告生成选择的消息列表（仅 user + assistant，去除系统消息） */
const selectableMessages = computed(() =>
  messages.value.filter(m => m.role === 'user' || m.role === 'assistant')
)
const currentChatTitle = computed(() => {
  const chat = recentChats.value.find(c => c.id === currentChatId.value)
  return chat?.title || '诊断报告'
})

const recentChats = ref<ChatRecord[]>([])
const searchChatQuery = ref('')
const filteredChats = computed(() => {
  if (!searchChatQuery.value.trim()) return recentChats.value
  const q = searchChatQuery.value.toLowerCase()
  return recentChats.value.filter(c => (c.title || '').toLowerCase().includes(q))
})
const chatMenu = reactive({ visible: false, x: 0, y: 0, chatId: 0 })

const msgListRef = ref<InstanceType<typeof ChatMessageList>>()

const isUploading = computed(() => attachedFiles.value.some(f => f.status === 'uploading'))
const analysisMode = computed<'chat' | 'diagnose'>(() => attachedFiles.value.length > 0 ? 'diagnose' : 'chat')
const userName = computed(() => userStore.userName)
const userInitial = computed(() => userName.value.charAt(0).toUpperCase())
const isAdmin = computed(() => userStore.isAdmin)

// ── UI Actions ────────────────────────────────────────────────

function onSearchChats(query: string) { searchChatQuery.value = query }
function toggleSearch() { /* 搜索框切换由 ChatSidebar 内部处理 */ }
function navigateTo(path: string) { router.push(path) }
function openKnowledge(source: { id?: number }) {
  router.push(source.id ? `/knowledge?document=${source.id}` : '/knowledge')
}
function onModelChange(model: string) { selectedModel.value = model; localStorage.setItem('selectedModel', model) }

async function handleUserAction(action: 'download' | 'settings' | 'help' | 'logout') {
  switch (action) {
    case 'settings': showSettings.value = true; break
    case 'logout': await userStore.logout(); router.push('/login'); break
    case 'download': showDownload.value = true; break
    case 'help': showHelp.value = true; break
  }
}

async function changePwd() {
  try {
    const { value } = await ElMessageBox.prompt(
      '请输入新密码（至少12位，含大小写字母+数字+特殊字符）',
      '修改密码',
      {
        inputType: 'password',
        inputValidator: (v: string) => {
          if (!v) return '密码不能为空'
          if (v.length < 12) return '密码至少12位'
          return true
        },
      },
    )
    if (!value) return
    // 调用后端更新密码
    const currentUser = userStore.user
    const userId = currentUser?.id
    if (!userId) {
      ElMessage.error('无法获取用户信息，请重新登录')
      return
    }
    try {
      await adminApi.updateUser(userId, { password: value })
      ElMessage.success('密码修改成功')
    } catch (err: any) {
      ElMessage.error('修改失败: ' + (err.response?.data?.detail || err.message))
    }
  } catch { /* cancelled */ }
}

async function clearData() {
  try {
    await ElMessageBox.confirm('确定清除所有对话数据？不可恢复。', '确认', { type: 'warning' })
    await Promise.all(recentChats.value.map(c => chatApi.deleteSession(c.id).catch(e => console.warn('[clearData] delete session failed:', c.id, e))))
    recentChats.value = []
    messages.value = []
    currentChatId.value = 0
    ElMessage.success('已清除')
    showSettings.value = false
  } catch { /* cancelled */ }
}

// ── Session Management ────────────────────────────────────────

const sessionsLoading = ref(false)

async function loadSessions() {
  sessionsLoading.value = true
  try {
    const { data } = await chatApi.listSessions()
    recentChats.value = (data.items || []).map((s: any) => ({ id: s.id, title: s.title || '新对话', model: s.model }))
  } catch {
    recentChats.value = []
  } finally {
    sessionsLoading.value = false
  }
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
  resetBranches()
  router.push('/chat')
}

async function selectChat(id: number) {
  // 已有完整本地消息时跳过；刷新后 messages 为空，必须重新拉取。
  if (id === currentChatId.value && messages.value.length > 0) {
    router.push('/chat')
    return
  }

  try {
    loadingPhase.value = 'sending'
    const { data } = await chatApi.getMessages(id)
    const msgs = Array.isArray(data) ? data : []
    
    if (import.meta.env.DEV) console.log(`[selectChat] id=${id} loaded ${msgs.length} messages`, msgs)
    
    messageIds.clear()
    currentChatId.value = id
    messages.value = msgs.map((m: any) => {
      const msg: any = {
        id: m.id.toString(),
        role: m.role,
        content: m.content || '',
        createdAt: m.created_at ? new Date(m.created_at).getTime() : Date.now(),
        files: extractFiles(m),
        sources: m.sources || [],
      }
      
      // 恢复持久化的思维链数据（短内容默认展开，长内容折叠）
      if (m.role === 'assistant' && m.thinking) {
        msg.thinking = {
          text: m.thinking.text || '',
          elapsed: m.thinking.elapsed || 0,
          active: false
        }
        // 短思维链（<500字符）默认展开，长思维链折叠
        msg._thinkOpen = !!(m.thinking.text) && (m.thinking.text || '').length < 500
      }
      
      return msg
    })
    messages.value.forEach((m: any) => messageIds.add(m.id))
    sessionStorage.setItem('activeChatId', String(id))
    
    // 检查是否有日志分析结果，如果有则可以生成报告
    const hasAnalysis = msgs.some((m: any) => 
      m.role === 'assistant' && m.content && m.content.includes('诊断结果')
    )
    canGenerateReport.value = hasAnalysis
    
    router.push('/chat')
    loadingPhase.value = 'idle'
    
    // 等待DOM更新后滚动到底部
    await nextTick()
    setTimeout(() => msgListRef.value?.scrollToBottom(), 150)
  } catch (err: any) {
    console.error('[selectChat] error:', err)
    ElMessage.error('加载对话失败: ' + (err.response?.data?.detail || err.message))
    loadingPhase.value = 'idle'
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

async function exportChat() {
  const chatId = chatMenu.chatId
  const chat = recentChats.value.find(c => c.id === chatId)
  if (!chat) return

  try {
    // 如果是当前对话，使用内存中的消息；否则从服务端加载
    let msgs = chatId === currentChatId.value 
      ? messages.value 
      : (await chatApi.getMessages(chatId)).data

    if (!Array.isArray(msgs)) msgs = []
    if (msgs.length === 0) {
      ElMessage.warning('该对话暂无消息')
      closeChatMenu()
      return
    }

    // 转换为导出格式
    const exportMessages: ExportMessage[] = msgs.map((m: any) => ({
      role: m.role,
      content: m.content || '',
      createdAt: m.createdAt || (m.created_at ? new Date(m.created_at).getTime() : Date.now()),
      sources: m.sources,
      thinking: m.thinking,
    }))

    await exportChatUtil(exportMessages, {
      title: chat.title || '对话记录',
      model: chat.model || selectedModel.value,
      includeMetadata: true,
      includeSources: true,
      includeThinking: false, // 默认不导出思维过程
    })

    ElMessage.success('对话已导出')
  } catch (err: any) {
    ElMessage.error('导出失败: ' + (err.message || '未知错误'))
  }
  closeChatMenu()
}

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

const MAX_FILE_SIZE = 200 * 1024 * 1024  // 200MB

function onFileInput(e: Event) {
  const t = e.target as HTMLInputElement
  if (t.files) {
    for (let i = 0; i < t.files.length; i++) {
      const f = t.files[i]
      if (f.size > MAX_FILE_SIZE) {
        ElMessage.warning(`文件 "${f.name}" 超过 200MB 限制，已跳过`)
        continue
      }
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

  // 并发保护：防止快速连击重复触发
  if (isSending.value) return
  isSending.value = true

  const isNewChat = !currentChatId.value
  inputText.value = ''
  attachedFiles.value = []

  if (isNewChat) {
    try {
      const { data: s } = await chatApi.createSession(text.slice(0, 30) || '新对话', selectedModel.value)
      currentChatId.value = s.id
      sessionStorage.setItem('activeChatId', String(s.id))
      recentChats.value.unshift({ id: s.id, title: s.title || text.slice(0, 30), model: s.model || undefined })
    } catch (e: any) {
      console.error('[sendMessage] create session failed:', e?.response?.data?.detail || e?.message || e)
      ElMessage.warning('创建会话失败，请重试')
      return
    }
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

  try {
    if (files.length > 0) {
      loadingPhase.value = 'uploading'
      await processFiles(files, userMsg)
    } else if (userMsg) {
      loadingPhase.value = 'streaming'
      await streamChat(userMsg)
    }
  } catch (e: any) {
    addMessage('assistant', `❌ 失败：${formatApiError(e)}`)
  } finally {
    loadingPhase.value = 'idle'
    isSending.value = false
  }
}

async function processFiles(files: FileAttachment[], text: string) {
  loadingPhase.value = 'uploading'

  // 并发上传所有文件
  const uploadResults = await Promise.allSettled(
    files.map(async (fa) => {
      fa.status = 'uploading'
      const fd = new FormData()
      fd.append('file', fa.file)
      fd.append('description', text)

      try {
        // axios 自动处理 multipart/form-data 的 Content-Type（含 boundary）
        const resp = await client.post('/logs/upload', fd, {
          onUploadProgress: (e) => {
            if (e.total) fa.progress = Math.round((e.loaded / e.total) * 100)
          },
        })
        fa.progress = 100
        fa.status = 'parsing'
        const logId = Number(resp.data?.id)
        if (import.meta.env.DEV) console.log(`[processFiles] upload OK: ${fa.name} → logId=${logId}`)
        if (!logId || logId <= 0) {
          throw new Error(`服务器返回了无效的日志ID: ${resp.data?.id}`)
        }
        return { fa, logId, ok: true }
      } catch (e: any) {
        fa.status = 'error'
        fa.error = formatApiError(e)
        if (import.meta.env.DEV) console.error(`[processFiles] upload FAIL: ${fa.name}`, fa.error)
        return { fa, logId: 0, ok: false, error: e }
      }
    }),
  )

  // 检查是否有成功上传的
  const succeeded = uploadResults.filter(
    (r): r is PromiseFulfilledResult<{ fa: FileAttachment; logId: number; ok: true }> =>
      r.status === 'fulfilled' && r.value.ok,
  )
  const failed = uploadResults.filter(
    (r): r is PromiseFulfilledResult<{ fa: FileAttachment; logId: number; ok: false; error: any }> =>
      r.status === 'fulfilled' && !r.value.ok,
  )

  // 为失败的显示错误消息
  for (const r of failed) {
    addMessage('assistant', `❌ 上传 \`${r.value.fa.name}\` 失败：${formatApiError(r.value.error)}`)
  }

  if (succeeded.length === 0) {
    loadingPhase.value = 'idle'
    return
  }

  loadingPhase.value = 'analyzing'

  // 并发执行所有分析
  await Promise.allSettled(
    succeeded.map(async (item: any) => {
      const { fa, logId } = item
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

      // 安全校验：确保 logId 有效
      if (!logId || logId <= 0) {
        processingMsg.content = `❌ 分析 \`${fa.name}\` 失败：日志ID无效 (${logId})`
        processingMsg.thinking.elapsed = 1
        processingMsg.thinking.active = false
        fa.status = 'error'
        fa.error = `无效的日志ID: ${logId}`
        return
      }

      try {
        updateThinking('正在解析日志并提取关键错误片段…')

        if (import.meta.env.DEV) console.log(`[processFiles] runAnalysis: logId=${logId} model=${selectedModel.value} query=${text?.slice(0, 50)}`)
        const analysisRes = await chatApi.runAnalysis(logId, selectedModel.value, text)
        if (analysisRes.data?.id) {
          updateThinking('规则引擎匹配 + 知识库检索中…')

          const detail = (await chatApi.getAnalysisResult(analysisRes.data.id)).data
          lastAnalysis.value = detail
          const sources = detail.sources || detail.knowledge_sources || detail.references || []

          // 优先使用后端预生成的 Markdown，回退到前端组装
          const response = detail.diagnosis_markdown || [
            `## ${fa.name} 的诊断结果`,
            '',
            '### 诊断摘要',
            detail.summary || '分析完成',
            '',
            '### 根因分析',
            detail.root_cause || '根因待确认',
            '',
            `诊断置信度：**${((detail.confidence || 0) * 100).toFixed(0)}%**`,
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

          // 保存消息时包含思维链数据
          const thinkingData = {
            text: processingMsg.thinking.text,
            elapsed: processingMsg.thinking.elapsed,
          }
          await chatApi.saveMessage(currentChatId.value, 'assistant', response, sources, thinkingData).catch(() => {})
        }
      } catch (e: any) {
        processingMsg.content = `❌ 分析 \`${fa.name}\` 失败：${formatApiError(e)}`
        processingMsg.thinking.elapsed = Math.max(1, Math.round((Date.now() - analysisStartedAt) / 1000))
        processingMsg.thinking.active = false
        fa.status = 'error'
        fa.error = e.response?.data?.detail || e.message
      }
      msgListRef.value?.scrollToBottom()
    }),
  )
}

async function streamChat(text: string) {
  const thinkStart = Date.now()
  const aId = thinkStart.toString()
  messageIds.add(aId)
  const assistantMsg: any = {
    id: aId, role: 'assistant', content: '', createdAt: thinkStart,
    thinking: { elapsed: 0, text: '', active: false }, sources: [] as ChatSource[],
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
    async (_model: string) => {
      const chat = recentChats.value.find(c => c.id === currentChatId.value)
      if (chat && chat.title === '新对话') chat.title = text.slice(0, 30)
      replyMsg.thinking.elapsed = Math.max(1, Math.round((Date.now() - thinkStart) / 1000))
      replyMsg.thinking.active = false
      msgListRef.value?.scrollToBottom()
      
      // 流式对话完成后保存消息，包含思维链数据（如果有）
      if (currentChatId.value && replyMsg.content) {
        const thinkingData = (replyMsg.thinking.text || replyMsg.thinking.elapsed > 0) ? {
          text: replyMsg.thinking.text || '',
          elapsed: replyMsg.thinking.elapsed
        } : undefined
        await chatApi.saveMessage(currentChatId.value, 'assistant', replyMsg.content, replyMsg.sources, thinkingData).catch(e => console.warn('[streamChat] save message failed:', e))
      }
    },
    (err: string) => {
      replyMsg.content = '❌ 流式回复失败：' + err
      replyMsg.thinking.active = false
    },
    lastAnalysis.value,
    (reasoning: string) => {
      replyMsg.thinking.text += reasoning
      replyMsg.thinking.elapsed = Math.max(1, Math.round((Date.now() - thinkStart) / 1000))
      replyMsg.thinking.active = true
      // 思维链短时默认展开，超过 500 字符自动折叠（太啰嗦）
      if (replyMsg._thinkOpen === undefined) {
        replyMsg._thinkOpen = replyMsg.thinking.text.length < 500
      }
    },
    (sources: ChatSource[]) => { replyMsg.sources = sources },
  )
}

function addMessage(role: string, content: string, files?: MsgAttachment[]) {
  // 生成唯一ID，避免时间戳冲突
  let id = Date.now().toString()
  let attempts = 0
  while (messageIds.has(id) && attempts < 100) {
    id = (Date.now() + attempts).toString()
    attempts++
  }
  
  if (messageIds.has(id)) {
    console.error('[addMessage] Failed to generate unique ID after 100 attempts')
    return
  }
  
  messageIds.add(id)

  const newMsg = {
    id,
    role: role as any,
    content,
    createdAt: Date.now(),
    files,
  } as any
  
  messages.value.push(newMsg)
  if (import.meta.env.DEV) console.log(`[addMessage] Added ${role} message, total: ${messages.value.length}`, newMsg)
  
  setTimeout(() => msgListRef.value?.scrollToBottom(), 50)
}

// ── Regenerate / Edit ────────────────────────────────────────

async function handleRegenerate(assistantMsg: any) {
  if (isSending.value || !currentChatId.value) return
  // 找到该 assistant 消息之前最近的 user 消息
  const idx = messages.value.findIndex(m => m.id === assistantMsg.id)
  const userMsg = [...messages.value].slice(0, idx).reverse().find(m => m.role === 'user')
  if (!userMsg) return

  // 创建分支：保存截断前的消息状态
  createBranch(messages.value, idx, `regen-${new Date().toLocaleTimeString()}`)

  // 截断：移除该 assistant 消息及其之后的所有消息（对话分支）
  messages.value = messages.value.slice(0, idx)
  messageIds.clear()
  messages.value.forEach((m: any) => messageIds.add(m.id))

  isSending.value = true
  loadingPhase.value = 'streaming'
  try {
    await streamChat(userMsg.content)
  } finally {
    loadingPhase.value = 'idle'
    isSending.value = false
  }
}

function handleEditMessage(userMsg: any) {
  if (isSending.value) return
  // 将消息内容填入输入框，截断该消息及之后的所有消息
  const idx = messages.value.findIndex(m => m.id === userMsg.id)
  if (idx === -1) return
  // 去掉文件标签，只保留文字
  const text = userMsg.content.replace(/\n?\[上传文件:.*?\]/g, '').trim()

  // 创建分支
  createBranch(messages.value, idx, `edit-${new Date().toLocaleTimeString()}`)

  inputText.value = text
  messages.value = messages.value.slice(0, idx)
  messageIds.clear()
  messages.value.forEach((m: any) => messageIds.add(m.id))
}

function formatSizeStr(bytes: number): string {
  if (bytes < 1024) return bytes + ' B'
  if (bytes < 1048576) return (bytes / 1024).toFixed(1) + ' KB'
  return (bytes / 1048576).toFixed(1) + ' MB'
}

/** 格式化 API 错误信息（处理 FastAPI 422 返回的 detail 数组） */
function formatApiError(e: any): string {
  const detail = e.response?.data?.detail
  if (Array.isArray(detail)) {
    return detail.map((d: any) => d.msg || JSON.stringify(d)).join('; ')
  }
  if (typeof detail === 'string') return detail
  return e.message || '未知错误'
}

async function generateDiagnosticReport() {
  if (messages.value.length === 0) {
    ElMessage.warning('当前对话暂无内容，请先进行对话或上传日志分析')
    return
  }
  showReportDialog.value = true
}

function onReportGenerate(selectedIds: Set<string>, format: 'markdown' | 'pdf' = 'markdown') {
  const selected = messages.value.filter(m => selectedIds.has(m.id))
  if (selected.length === 0) {
    ElMessage.warning('请至少选择一条消息')
    return
  }

  if (format === 'pdf') {
    // PDF 导出
    import('@/utils/pdfExport').then(({ exportToPdf }) => {
      const pdfMessages = selected.map((m: any) => ({
        role: m.role,
        content: m.content || '',
        createdAt: m.createdAt || Date.now(),
      }))
      exportToPdf(pdfMessages, {
        title: currentChatTitle.value,
        model: selectedModel.value,
        includeMetadata: true,
      }).then(() => {
        ElMessage.success(`PDF 报告已生成，包含 ${selected.length} 条消息`)
        showReportDialog.value = false
      }).catch((err: any) => {
        ElMessage.error('PDF 导出失败: ' + (err.message || '未知错误'))
      })
    }).catch((err: any) => {
      ElMessage.error('PDF 模块加载失败: ' + (err.message || '未知错误'))
    })
    return
  }

  // Markdown 导出
  const exportMessages: ExportMessage[] = selected.map((m: any) => ({
    role: m.role,
    content: m.content || '',
    createdAt: m.createdAt || Date.now(),
    sources: m.sources,
    thinking: m.thinking,
  }))

  exportChatUtil(exportMessages, {
    title: currentChatTitle.value,
    model: selectedModel.value,
    includeMetadata: true,
    includeSources: true,
    includeThinking: false,
  })

  ElMessage.success(`诊断报告已生成，包含 ${selected.length} 条消息`)
  showReportDialog.value = false
}

onMounted(() => {
  selectedModel.value = localStorage.getItem('selectedModel') || 'deepseek-v4-flash'
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
