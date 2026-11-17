<template>
  <div class="chat-layout">
    <!-- 左侧边栏 -->
    <ChatSidebar v-model:collapsed="sidebarCollapsed" :chats="filteredChats" :loading="sessionsLoading"
      :activeChatId="isChatRoute ? currentChatId : 0" :sendingIds="[...sendingChatIds]"
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
          <!-- key 不能包含消息条数：否则每加一条消息组件都会重建，
               容器 scrollTop 归零导致页面先跳到顶部再瞬间拉回底部 -->
          <ChatMessageList ref="msgListRef" :key="'cl-' + currentChatId"
            :messages="displayMessages" :loading="loadingPhase !== 'idle'" :isEmpty="displayMessages.length === 0"
            :chatId="currentChatId"
            @previewFile="previewFile" @openKnowledge="openKnowledge" @regenerate="handleRegenerate" @editSend="handleEditSend"
            @switchVersion="handleSwitchVersion"
            @selectClarification="onSelectClarification" />
          <div class="input-wrapper">
            <ChatInputArea v-model="inputText" :files="attachedFiles" :selectedModel="selectedModel"
              :isUploading="isUploading" :canReport="canGenerateReport" :hasMessages="messages.length > 0"
              :isStreaming="loadingPhase === 'streaming'"
              @send="sendMessage" @stop="stopChatStream(currentChatId)" @fileInput="onFileInput"
              @removeFile="removeFile" @modelChange="onModelChange"
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
import { appendVersion, snapshotVersion, applyVersion } from '@/utils/messageVersions'
import { adminApi } from '@/api/admin'
import { useUserStore } from '@/stores/user'
import { exportChat as exportChatUtil } from '@/utils/export'
import { pollAnalysis } from '@/utils/analysisPoll'
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
type LoadingPhase = 'idle' | 'sending' | 'uploading' | 'streaming' | 'analyzing'

// ── 按对话隔离的状态：支持多对话并行提问（配置见管理后台系统参数）──
const currentChatId = ref(0)
const messagesByChat = reactive(new Map<number, any[]>())
const loadingPhases = reactive(new Map<number, LoadingPhase>())
const sendingChatIds = reactive(new Set<number>())
/** 各对话最近一次日志分析结果（流式提问时注入诊断上下文） */
const lastAnalysisByChat = reactive(new Map<number, any>())
/** 附件分析需要补充信息时，按对话记录日志 ID 与问题，用户补充后自动重跑 */
const pendingClarificationByChat = reactive(new Map<number, { logId: number; questions: any[] }>())

function ensureChatMessages(chatId: number): any[] {
  if (!messagesByChat.has(chatId)) messagesByChat.set(chatId, [])
  return messagesByChat.get(chatId)!
}
function setChatMessages(chatId: number, arr: any[]) { messagesByChat.set(chatId, arr) }
function setLoadingPhase(chatId: number, phase: LoadingPhase) { loadingPhases.set(chatId, phase) }
/** 各对话进行中的流式请求控制器（用于停止生成） */
const activeStreams = reactive(new Map<number, AbortController>())
function stopChatStream(chatId: number) {
  activeStreams.get(chatId)?.abort()
}
function setSending(chatId: number, on: boolean) {
  if (on) sendingChatIds.add(chatId)
  else sendingChatIds.delete(chatId)
}

const loadingPhase = computed<LoadingPhase>(() => loadingPhases.get(currentChatId.value) ?? 'idle')
const isSending = computed(() => sendingChatIds.has(currentChatId.value))
const messages = computed<any[]>(() => messagesByChat.get(currentChatId.value) ?? [])
const canGenerateReport = ref(false)

// 多对话并行提问配置（管理后台 → 系统配置 → 系统参数）
const chatConcurrency = reactive({ parallelEnabled: true, maxParallel: 3 })
function effectiveParallelLimit(): number {
  return chatConcurrency.parallelEnabled ? Math.max(1, chatConcurrency.maxParallel) : 1
}
async function loadChatConcurrencyConfig() {
  try {
    const { data } = await adminApi.getSystemConfig()
    if (data) {
      chatConcurrency.parallelEnabled = data.parallel_chat_enabled ?? true
      chatConcurrency.maxParallel = Math.max(1, data.max_parallel_chats ?? 3)
    }
  } catch { /* 加载失败保持默认值 */ }
}

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
    setChatMessages(currentChatId.value, saved)
    saved.forEach((m: any) => messageIds.add(m.id))
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
    messagesByChat.clear()
    loadingPhases.clear()
    sendingChatIds.clear()
    lastAnalysisByChat.clear()
    pendingClarificationByChat.clear()
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
    recentChats.value = (data.items || []).map((s: any) => ({ id: s.id, title: s.title || '新对话', model: s.model, updatedAt: s.updated_at || s.created_at }))
  } catch {
    recentChats.value = []
  } finally {
    sessionsLoading.value = false
  }
}

async function newChat() {
  currentChatId.value = 0
  sessionStorage.removeItem('activeChatId')
  canGenerateReport.value = false
  inputText.value = ''
  attachedFiles.value = []
  resetBranches()
  router.push('/chat')
}

async function selectChat(id: number, options: { navigate?: boolean } = {}) {
  // navigate=false：仅恢复消息（刷新页面时），不改变当前路由——
  // 否则在知识库/诊断报告页刷新会被强制跳回 /chat。
  const { navigate = true } = options
  // 已有完整本地消息时跳过；刷新后 messages 为空，必须重新拉取。
  if (id === currentChatId.value && messages.value.length > 0) {
    if (navigate) router.push('/chat')
    return
  }
  // 该对话已有本地消息（含正在后台流式输出的）：直接切换，保留进行中的输出
  if (messagesByChat.has(id)) {
    currentChatId.value = id
    sessionStorage.setItem('activeChatId', String(id))
    if (navigate) router.push('/chat')
    await nextTick()
    setTimeout(() => msgListRef.value?.scrollToBottom(), 150)
    return
  }

  try {
    setLoadingPhase(id, 'sending')
    const { data } = await chatApi.getMessages(id)
    const msgs = Array.isArray(data) ? data : []
    
    if (import.meta.env.DEV) console.log(`[selectChat] id=${id} loaded ${msgs.length} messages`, msgs)
    
    currentChatId.value = id
    setChatMessages(id, msgs.map((m: any) => {
      // 编辑重发的版本历史：展示 active_version 对应的版本内容
      const hasVersions = !!(m.versions && m.versions.length)
      const activeIdx = hasVersions ? (m.active_version ?? m.versions.length - 1) : 0
      const activeVersion = hasVersions ? m.versions[activeIdx] : null
      const msg: any = {
        id: m.id.toString(),
        role: m.role,
        content: activeVersion?.content ?? (m.content || ''),
        createdAt: m.created_at ? new Date(m.created_at).getTime() : Date.now(),
        files: extractFiles(m),
        sources: activeVersion?.sources ?? m.sources ?? [],
        _persisted: true,
        _dbId: m.id,
        versions: hasVersions ? m.versions : undefined,
        activeVersion: hasVersions ? activeIdx : undefined,
      }
      
      // 恢复持久化的思维链数据（短内容默认展开，长内容折叠）
      const thinkingData = activeVersion?.thinking ?? m.thinking
      if (m.role === 'assistant' && thinkingData) {
        msg.thinking = {
          text: thinkingData.text || '',
          elapsed: thinkingData.elapsed || 0,
          active: false
        }
        // 短思维链（<500字符）默认展开，长思维链折叠
        msg._thinkOpen = !!(msg.thinking.text) && (msg.thinking.text || '').length < 500
      }
      
      return msg
    }))
    msgs.forEach((m: any) => messageIds.add(m.id.toString()))
    sessionStorage.setItem('activeChatId', String(id))
    
    // 检查是否有日志分析结果，如果有则可以生成报告
    const hasAnalysis = msgs.some((m: any) => 
      m.role === 'assistant' && m.content && m.content.includes('诊断结果')
    )
    canGenerateReport.value = hasAnalysis
    
    if (navigate) router.push('/chat')
    setLoadingPhase(id, 'idle')
    
    // 等待DOM更新后滚动到底部
    await nextTick()
    setTimeout(() => msgListRef.value?.scrollToBottom(), 150)
  } catch (err: any) {
    console.error('[selectChat] error:', err)
    ElMessage.error('加载对话失败: ' + (err.response?.data?.detail || err.message))
    setLoadingPhase(id, 'idle')
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
    messagesByChat.delete(chatMenu.chatId)
    loadingPhases.delete(chatMenu.chatId)
    sendingChatIds.delete(chatMenu.chatId)
    lastAnalysisByChat.delete(chatMenu.chatId)
    pendingClarificationByChat.delete(chatMenu.chatId)
    if (currentChatId.value === chatMenu.chatId) {
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

  let chatId = currentChatId.value
  // 并发保护：同一对话内防止快速连击重复触发
  if (sendingChatIds.has(chatId)) return
  // 多对话并行限制（管理后台 → 系统配置 → 系统参数）
  const limit = effectiveParallelLimit()
  if (sendingChatIds.size >= limit) {
    ElMessage.warning(
      chatConcurrency.parallelEnabled
        ? `最多支持 ${limit} 个对话同时提问，请等待进行中的对话完成`
        : '已有对话正在提问（系统未开启多对话并行提问）',
    )
    return
  }
  setSending(chatId, true)

  const isNewChat = !chatId
  inputText.value = ''
  attachedFiles.value = []

  try {
    if (isNewChat) {
      try {
        const { data: s } = await chatApi.createSession(text.slice(0, 30) || '新对话', selectedModel.value)
        setSending(chatId, false)
        chatId = s.id
        setSending(chatId, true)
        ensureChatMessages(s.id)
        currentChatId.value = s.id
        sessionStorage.setItem('activeChatId', String(s.id))
        recentChats.value.unshift({ id: s.id, title: s.title || text.slice(0, 30), model: s.model || undefined, updatedAt: s.updated_at || s.created_at })
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
    const userMsgObj = addMessage('user', userMsg, attachments, chatId)

    // 用户消息先持久化，确保刷新后 selectChat 能恢复完整历史
    if (chatId) {
      try {
        const { data: saved } = await chatApi.saveMessage(chatId, 'user', userMsg)
        if (saved?.id != null && userMsgObj) userMsgObj._dbId = saved.id
      } catch {
        ElMessage.warning('用户消息保存失败，刷新后可能无法恢复')
      }
    }

    if (files.length > 0) {
      setLoadingPhase(chatId, 'uploading')
      await processFiles(files, userMsg, chatId)
    } else if (pendingClarificationByChat.get(chatId)) {
      setLoadingPhase(chatId, 'analyzing')
      await reanalyzeWithClarification(userMsg, chatId)
    } else if (userMsg) {
      setLoadingPhase(chatId, 'streaming')
      await streamChat(userMsg, chatId)
    }
  } catch (e: any) {
    addMessage('assistant', `❌ 失败：${formatApiError(e)}`, undefined, chatId)
  } finally {
    setLoadingPhase(chatId, 'idle')
    setSending(chatId, false)
  }
}

/** 附件澄清后：用户补充信息，自动用上次日志重新分析 */
async function reanalyzeWithClarification(text: string, chatId: number) {
  const pending = pendingClarificationByChat.get(chatId)
  if (!pending) return
  const started = Date.now()
  const id = started.toString()
  messageIds.add(id)
  const msgs = ensureChatMessages(chatId)
  msgs.push({
    id,
    role: 'assistant',
    content: '',
    createdAt: started,
    thinking: { elapsed: 0, active: true, text: '正在结合补充信息重新分析…' },
    sources: [] as ChatSource[],
  })
  const msg = msgs[msgs.length - 1]
  try {
    const res = await chatApi.runAnalysis(pending.logId, selectedModel.value, text)
    const detail = (await chatApi.getAnalysisResult(res.data.id)).data
    lastAnalysisByChat.set(chatId, detail)
    const response = detail.diagnosis_markdown || detail.summary || '分析完成'
    msg.content = response
    msg.sources = detail.sources || detail.knowledge_sources || detail.references || []
    msg.thinking.active = false
    msg.thinking.elapsed = Math.max(1, Math.round((Date.now() - started) / 1000))
    if (detail.needs_clarification && (detail.questions || []).length) {
      msg.clarification = detail.questions
      pendingClarificationByChat.set(chatId, { logId: pending.logId, questions: detail.questions })
    } else {
      pendingClarificationByChat.delete(chatId)
    }
    await chatApi.saveMessage(chatId, 'assistant', response, msg.sources, {
      text: msg.thinking.text,
      elapsed: msg.thinking.elapsed,
    }).then(({ data: saved }) => { if (saved?.id != null) msg._dbId = saved.id }).catch(() => {})
  } catch (e: any) {
    msg.content = `❌ 分析失败：${formatApiError(e)}`
    msg.thinking.active = false
  } finally {
    if (currentChatId.value === chatId) msgListRef.value?.scrollToBottom()
  }
}

/** 轮询异步分析任务状态，直到 completed / failed / 超时。
 *  阶段进度由后端 "[进度] …" summary 实时上报，驱动思维链展示 Agent 真实进度。 */
function waitForAnalysis(
  analysisId: number,
  onProgress?: (text: string) => void,
  timeoutMs = 540_000,
): Promise<any> {
  return pollAnalysis(chatApi, analysisId, { onProgress, timeoutMs })
}

async function processFiles(files: FileAttachment[], text: string, chatId: number) {
  setLoadingPhase(chatId, 'uploading')

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
    addMessage('assistant', `❌ 上传 \`${r.value.fa.name}\` 失败：${formatApiError(r.value.error)}`, undefined, chatId)
  }

  if (succeeded.length === 0) {
    setLoadingPhase(chatId, 'idle')
    return
  }

  setLoadingPhase(chatId, 'analyzing')

  // 并发执行所有分析
  await Promise.allSettled(
    succeeded.map(async (item: any) => {
      const { fa, logId } = item
      const analysisStartedAt = Date.now()
      const pId = analysisStartedAt.toString()
      messageIds.add(pId)
      const chatMsgs = ensureChatMessages(chatId)
      chatMsgs.push({
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
      const processingMsg = chatMsgs[chatMsgs.length - 1]

      const seenPhases = new Set<string>()
      const updateThinking = (text: string) => {
        // 思维链呈现 Agent 真实进度：按阶段追加，形成执行轨迹
        if (!seenPhases.has(text)) {
          seenPhases.add(text)
          const prev = processingMsg.thinking.text
          processingMsg.thinking.text = prev ? `${prev}\n${text}` : text
        }
        processingMsg.thinking.elapsed = Math.max(1, Math.round((Date.now() - analysisStartedAt) / 1000))
        if (currentChatId.value === chatId) msgListRef.value?.scrollToBottom()
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

        if (import.meta.env.DEV) console.log(`[processFiles] runAnalysisAsync: logId=${logId} model=${selectedModel.value} query=${text?.slice(0, 50)}`)
        // 提问文本去掉文件标签，避免干扰后端按用户问题检索/分析
        const queryText = text.replace(/\n?\[上传文件:.*?\]/g, '').trim()
        const queued = await chatApi.runAnalysisAsync(logId, selectedModel.value, queryText)
        const analysisId = queued.data?.id
        if (!analysisId) throw new Error('分析任务创建失败')
        updateThinking('规则引擎匹配 + 知识库检索中…')

        const detail = await waitForAnalysis(analysisId, updateThinking)
        if (detail) {
          lastAnalysisByChat.set(chatId, detail)
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
          if (detail.needs_clarification && (detail.questions || []).length) {
            processingMsg.clarification = detail.questions
            pendingClarificationByChat.set(chatId, { logId, questions: detail.questions })
          } else {
            pendingClarificationByChat.delete(chatId)
          }
          processingMsg.thinking.elapsed = Math.max(1, Math.round((Date.now() - analysisStartedAt) / 1000))
          processingMsg.thinking.active = false
          canGenerateReport.value = true
          fa.status = 'done'

          // 保存消息时包含思维链数据
          const thinkingData = {
            text: processingMsg.thinking.text,
            elapsed: processingMsg.thinking.elapsed,
          }
          await chatApi.saveMessage(chatId, 'assistant', response, sources, thinkingData)
            .then(({ data: saved }) => { if (saved?.id != null) processingMsg._dbId = saved.id })
            .catch(() => {})
        }
      } catch (e: any) {
        processingMsg.content = `❌ 分析 \`${fa.name}\` 失败：${formatApiError(e)}`
        processingMsg.thinking.elapsed = Math.max(1, Math.round((Date.now() - analysisStartedAt) / 1000))
        processingMsg.thinking.active = false
        fa.status = 'error'
        fa.error = e.response?.data?.detail || e.message
      }
      if (currentChatId.value === chatId) msgListRef.value?.scrollToBottom()
    }),
  )
}

async function streamChat(text: string, chatId: number, reuseMsg?: any) {
  const thinkStart = Date.now()
  const aId = thinkStart.toString()
  messageIds.add(aId)
  const msgs = ensureChatMessages(chatId)
  let replyMsg: any
  if (reuseMsg) {
    // 编辑重发：复用旧回答消息对象继续接收新回答（旧版本已归档进 versions）
    replyMsg = reuseMsg
  } else {
    msgs.push({
      id: aId, role: 'assistant', content: '', createdAt: thinkStart,
      thinking: { elapsed: 0, text: '', active: false }, sources: [] as ChatSource[],
    })
    // 必须经响应式代理取消息对象：直接持有原始对象，后续 token 追加不会触发渲染
    replyMsg = msgs[msgs.length - 1]
  }
  const scrollToBottomIfActive = () => {
    if (currentChatId.value === chatId) msgListRef.value?.scrollToBottom()
  }

  let firstToken = true
  let receivedToken = false
  let stopped = false
  let failed = false
  const controller = new AbortController()
  activeStreams.set(chatId, controller)

  await chatApi.sendMessageStream(
    chatId,
    text,
    selectedModel.value,
    (token: string) => {
      receivedToken = true
      if (firstToken) {
        firstToken = false
        const elapsed = Math.max(1, Math.round((Date.now() - thinkStart) / 1000))
        replyMsg.thinking.elapsed = elapsed
        replyMsg.thinking.active = false
      }
      replyMsg.content += token
      scrollToBottomIfActive()
    },
    async (_model: string) => {
      const chat = recentChats.value.find(c => c.id === chatId)
      if (chat && chat.title === '新对话') chat.title = text.slice(0, 30)
      replyMsg.thinking.elapsed = Math.max(1, Math.round((Date.now() - thinkStart) / 1000))
      replyMsg.thinking.active = false
      scrollToBottomIfActive()
      
      // 流式对话完成后保存消息（归属发起提问的对话），包含思维链数据（如果有）
      if (chatId && replyMsg.content) {
        await persistReplyMessage(chatId, replyMsg, !!reuseMsg)
      }
    },
    (err: string) => {
      failed = true
      // 保留已生成的内容，仅追加中断提示（不覆盖已有 token）
      replyMsg.content = replyMsg.content
        ? `${replyMsg.content}\n\n⚠️ 流式回复中断：${err}`
        : '❌ 流式回复失败：' + err
      replyMsg.thinking.active = false
    },
    lastAnalysisByChat.get(chatId),
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
    (questions: any[]) => { replyMsg.clarification = questions },
    () => { stopped = true },
    controller.signal,
  )

  activeStreams.delete(chatId)

  // 停止/出错中断时：保存已生成的部分内容，避免刷新后丢失
  if ((stopped || failed) && receivedToken) {
    await persistReplyMessage(chatId, replyMsg, !!reuseMsg)
  }
}

/**
 * 持久化回答消息。
 * 编辑重发（versioned）：新回答快照为新版本后整体更新原消息行（保留旧版本）；
 * 普通回答：插入新消息行并记住行 ID（供后续编辑/反馈更新用）。
 */
async function persistReplyMessage(chatId: number, replyMsg: any, versioned: boolean) {
  const thinkingData = (replyMsg.thinking?.text || replyMsg.thinking?.elapsed > 0) ? {
    text: replyMsg.thinking.text || '',
    elapsed: replyMsg.thinking.elapsed,
  } : undefined
  if (versioned && replyMsg._dbId != null) {
    const idx = snapshotVersion(replyMsg, replyMsg.activeVersion)
    try {
      await chatApi.updateMessage(chatId, replyMsg._dbId, {
        content: replyMsg.content,
        sources: replyMsg.sources,
        thinking: thinkingData,
        versions: replyMsg.versions,
        active_version: idx,
      })
    } catch (e) {
      console.warn('[persistReplyMessage] versioned update failed:', e)
    }
    return
  }
  try {
    const { data: saved } = await chatApi.saveMessage(
      chatId, 'assistant', replyMsg.content, replyMsg.sources, thinkingData,
      replyMsg.versions, replyMsg.activeVersion,
    )
    if (saved?.id != null) replyMsg._dbId = saved.id
  } catch (e) {
    console.warn('[persistReplyMessage] save message failed:', e)
  }
}

/** 供澄清选项芯片点击：把选项填入输入框，由用户确认后发送 */
function onSelectClarification(value: string) {
  const current = inputText.value.trim()
  inputText.value = current ? `${current} ${value}` : value
}

function addMessage(role: string, content: string, files?: MsgAttachment[], chatId: number = currentChatId.value) {
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
  
  ensureChatMessages(chatId).push(newMsg)
  if (import.meta.env.DEV) console.log(`[addMessage] Added ${role} message to chat ${chatId}`, newMsg)

  setTimeout(() => {
    if (currentChatId.value === chatId) msgListRef.value?.scrollToBottom()
  }, 50)
  // 返回响应式代理对象（后续持久化后把行 ID 记到 _dbId）
  return ensureChatMessages(chatId)[ensureChatMessages(chatId).length - 1]
}

// ── Regenerate / Edit ────────────────────────────────────────

async function handleRegenerate(assistantMsg: any) {
  const chatId = currentChatId.value
  if (sendingChatIds.has(chatId) || !chatId) return
  const limit = effectiveParallelLimit()
  if (sendingChatIds.size >= limit) {
    ElMessage.warning(`最多支持 ${limit} 个对话同时提问，请等待进行中的对话完成`)
    return
  }
  // 找到该 assistant 消息之前最近的 user 消息
  const idx = messages.value.findIndex(m => m.id === assistantMsg.id)
  const userMsg = [...messages.value].slice(0, idx).reverse().find(m => m.role === 'user')
  if (!userMsg) return

  // 创建分支：保存截断前的消息状态
  createBranch(messages.value, idx, `regen-${new Date().toLocaleTimeString()}`)

  // 截断：移除该 assistant 消息及其之后的所有消息（对话分支）
  const truncated = messages.value.slice(0, idx)
  setChatMessages(chatId, truncated)
  truncated.forEach((m: any) => messageIds.add(m.id))

  setSending(chatId, true)
  setLoadingPhase(chatId, 'streaming')
  try {
    await streamChat(userMsg.content, chatId)
  } finally {
    setLoadingPhase(chatId, 'idle')
    setSending(chatId, false)
  }
}

/**
 * 内联编辑重发（编辑提问 → 保留历史版本 → 重新生成回答）。
 * 不删除原始提问：旧提问/旧回答归档为上一版本，消息下方出现 ‹ 1/2 › 切换。
 */
async function handleEditSend(userMsg: any, newText: string) {
  const chatId = currentChatId.value
  if (!chatId || sendingChatIds.has(chatId)) return
  const limit = effectiveParallelLimit()
  if (sendingChatIds.size >= limit) {
    ElMessage.warning(
      chatConcurrency.parallelEnabled
        ? `最多支持 ${limit} 个对话同时提问，请等待进行中的对话完成`
        : '已有对话正在提问（系统未开启多对话并行提问）',
    )
    return
  }
  const msgs = messagesByChat.get(chatId)
  if (!msgs) return
  const idx = msgs.findIndex((m: any) => m.id === userMsg.id)
  if (idx === -1) return

  setSending(chatId, true)
  try {
    // 1. 提问消息版本化：保留修改前内容，追加修改后版本
    const newIdx = appendVersion(userMsg, newText)
    if (userMsg._dbId != null) {
      chatApi.updateMessage(chatId, userMsg._dbId, {
        content: newText,
        versions: userMsg.versions,
        active_version: newIdx,
      }).catch(e => console.warn('[handleEditSend] persist question versions failed:', e))
    }

    // 2. 配对回答（该提问后的第一条 assistant 消息）：旧回答归档为旧版本，重新生成新版本
    const ans: any = idx + 1 < msgs.length && msgs[idx + 1].role === 'assistant' && !msgs[idx + 1].thinking?.active
      ? msgs[idx + 1]
      : null

    setLoadingPhase(chatId, 'streaming')
    if (ans) {
      // 归档旧回答（快照到其当前版本下标，与提问版本下标对齐）
      const oldIdx = snapshotVersion(ans, ans.activeVersion ?? Math.max(0, newIdx - 1))
      ans.activeVersion = newIdx
      if (ans.versions && ans.versions.length <= newIdx) {
        ans.versions = [...ans.versions]
        ans.versions[newIdx] = { content: '' }
      }
      ans.content = ''
      ans.sources = []
      ans.thinking = { elapsed: 0, text: '', active: true }
      ans._versionedFrom = oldIdx
      await streamChat(newText, chatId, ans)
    } else {
      await streamChat(newText, chatId)
    }
  } finally {
    setLoadingPhase(chatId, 'idle')
    setSending(chatId, false)
  }
}

/** 切换消息版本：提问与其配对回答一起切换（DeepSeek 式版本浏览） */
function handleSwitchVersion(msg: any, idx: number) {
  const chatId = currentChatId.value
  if (!chatId || sendingChatIds.has(chatId)) return
  const msgs = messagesByChat.get(chatId)
  if (!msgs) return
  if (!applyVersion(msg, idx)) return

  // 配对回答（该提问后的第一条 assistant 消息）同步切换
  const i = msgs.findIndex((m: any) => m.id === msg.id)
  const ans: any = i !== -1 && i + 1 < msgs.length && msgs[i + 1].role === 'assistant' ? msgs[i + 1] : null
  if (ans && ans.versions?.[idx]) applyVersion(ans, idx)

  // 持久化当前浏览的版本（fire-and-forget）
  if (msg._dbId != null) {
    chatApi.updateMessage(chatId, msg._dbId, { content: msg.content, active_version: idx })
      .catch(e => console.warn('[handleSwitchVersion] persist failed:', e))
  }
  if (ans && ans._dbId != null && ans.versions?.[idx]) {
    chatApi.updateMessage(chatId, ans._dbId, {
      content: ans.content, sources: ans.sources, thinking: ans.thinking, active_version: idx,
    }).catch(e => console.warn('[handleSwitchVersion] persist answer failed:', e))
  }
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
      // 只恢复消息，不跳转路由：刷新时停留在当前页面（知识库/诊断报告等）
      selectChat(id, { navigate: false }).catch(() => { currentChatId.value = 0 })
    }
  }
  loadSessions()  // 始终加载侧边栏列表，不与自动恢复互斥
  loadChatConcurrencyConfig()  // 多对话并行提问配置（管理后台系统参数）
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
  background: var(--chat-msg-pre-bg);
  color: var(--chat-msg-pre-text);
  border: 1px solid var(--chat-msg-pre-border);
  border-radius: 8px;
  font-size: 13px;
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-all;
}
</style>
