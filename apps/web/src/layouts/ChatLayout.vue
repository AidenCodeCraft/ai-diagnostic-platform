<template>
  <div class="chat-layout">
    <!-- ============================================================ -->
    <!-- 左侧边栏                                                     -->
    <!-- ============================================================ -->
    <aside class="sidebar" :class="{ collapsed: sidebarCollapsed }">
      <div class="sidebar-inner">
        <div class="sidebar-top">
          <button class="sidebar-icon-btn" title="搜索" @click="toggleSearch">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.35-4.35"/></svg>
          </button>
          <button class="sidebar-icon-btn" :title="sidebarCollapsed ? '展开侧栏' : '收起侧栏'" @click="toggleSidebar">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="18" height="18" rx="2"/><path :d="sidebarCollapsed ? 'M9 3v18' : 'M15 3v18'"/></svg>
          </button>
        </div>
        <div class="sidebar-new-chat" v-show="!sidebarCollapsed">
          <button class="new-chat-btn" @click="newChat">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
            <span>新对话</span>
          </button>
        </div>
        <div class="sidebar-nav" v-show="!sidebarCollapsed">
          <div class="nav-item" @click="navigateTo('/knowledge')"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 19.5v-15A2.5 2.5 0 0 1 6.5 2H20v20H6.5a2.5 2.5 0 0 1 0-5H20"/></svg><span>知识库</span></div>
          <div class="nav-item" @click="navigateTo('/plugins')"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/><path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/></svg><span>插件管理</span></div>
          <div class="nav-item" @click="navigateTo('/reports')"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/></svg><span>诊断报告</span></div>
        </div>
        <div class="sidebar-history" v-show="!sidebarCollapsed">
          <div class="section-title">最近对话</div>
          <div v-for="chat in recentChats" :key="chat.id" class="history-item" :class="{ active: chat.id === currentChatId }" @click="selectChat(chat.id)">
            <span class="history-title">{{ chat.title }}</span>
            <button class="history-more-btn" @click.stop="openChatMenu($event, chat)"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="5" r="1"/><circle cx="12" cy="12" r="1"/><circle cx="12" cy="19" r="1"/></svg></button>
          </div>
          <div v-if="recentChats.length === 0" class="empty-hint">暂无对话记录</div>
        </div>
        <div class="sidebar-user" v-show="!sidebarCollapsed" @click="showUserMenu = !showUserMenu">
          <div class="user-avatar">{{ userInitial }}</div>
          <span class="user-name">{{ userName }}</span>
        </div>
      </div>
    </aside>

    <button v-if="sidebarCollapsed" class="float-open-btn" @click="toggleSidebar" title="展开侧栏">
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="18" height="18" rx="2"/><path d="M9 3v18"/></svg>
    </button>

    <!-- 用户菜单 -->
    <teleport to="body">
      <div v-if="showUserMenu" class="menu-overlay" @click="showUserMenu = false"></div>
      <div v-if="showUserMenu" class="user-menu-popup">
        <button @click="downloadApp">📥 下载桌面版</button>
        <button @click="openSettings">⚙️ 设置</button>
        <button @click="openHelp">💬 帮助与反馈</button>
        <hr>
        <button class="danger" @click="logout">🚪 退出登录</button>
      </div>
    </teleport>

    <!-- 对话菜单 -->
    <teleport to="body">
      <div v-if="chatMenu.visible" class="menu-overlay" @click="closeChatMenu"></div>
      <div v-if="chatMenu.visible" class="chat-menu-popup" :style="{ top: chatMenu.y + 'px', left: chatMenu.x + 'px' }">
        <button @click="renameChat"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M17 3a2.83 2.83 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5Z"/></svg> 重命名</button>
        <button @click="pinChat"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="12" y1="5" x2="12" y2="19"/><polyline points="19 12 12 19 5 12"/></svg> 置顶</button>
        <button @click="analyzeChat"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/></svg> 分析</button>
        <hr>
        <button class="danger" @click="deleteChat"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg> 删除</button>
      </div>
    </teleport>

    <!-- 设置弹窗 — 左右分栏 + 平滑动画 -->
    <teleport to="body">
      <div v-if="showSettings" class="menu-overlay settings-overlay" @click="showSettings = false"></div>
      <transition name="settings-modal">
        <div v-if="showSettings" class="settings-dialog">
          <div class="settings-header">
            <h3>设置</h3>
            <button class="settings-close" @click="showSettings = false">&times;</button>
          </div>
          <div class="settings-layout">
            <!-- 左侧导航 -->
            <nav class="settings-nav">
              <div
                v-for="tab in settingTabs"
                :key="tab.key"
                class="settings-nav-item"
                :class="{ active: activeSettingTab === tab.key }"
                @click="activeSettingTab = tab.key"
              >
                <span v-html="tab.icon"></span>
                <span>{{ tab.label }}</span>
              </div>
            </nav>
            <!-- 右侧内容 -->
            <div class="settings-content">
              <!-- 通用 -->
              <div v-show="activeSettingTab === 'general'">
                <div class="setting-group">
                  <h4>主题</h4>
                  <div class="theme-switch">
                    <button :class="{ active: settings.theme === 'light' }" @click="settings.theme = 'light'; saveSettings()">☀️ 浅色</button>
                    <button :class="{ active: settings.theme === 'dark' }" @click="settings.theme = 'dark'; saveSettings()">🌙 深色</button>
                    <button :class="{ active: settings.theme === 'system' }" @click="settings.theme = 'system'; saveSettings()">💻 跟随系统</button>
                  </div>
                </div>
                <div class="setting-group">
                  <h4>语言</h4>
                  <el-select v-model="settings.language" size="small" style="width:150px" @change="saveSettings">
                    <el-option label="简体中文" value="zh-CN" />
                    <el-option label="English" value="en" />
                  </el-select>
                </div>
              </div>

              <!-- 账号 -->
              <div v-show="activeSettingTab === 'account'">
                <div class="setting-group">
                  <h4>个人信息</h4>
                  <div class="setting-row"><span>用户名</span><span class="setting-value">{{ userName }}</span></div>
                </div>
                <div class="setting-group">
                  <h4>安全</h4>
                  <div class="setting-row"><span>修改密码</span><el-button size="small" @click="changePwd">修改</el-button></div>
                </div>
              </div>

              <!-- 数据 -->
              <div v-show="activeSettingTab === 'data'">
                <div class="setting-group">
                  <h4>清除数据</h4>
                  <p class="setting-desc">清除后将不可恢复，请谨慎操作。</p>
                  <el-button size="small" type="danger" @click="clearData">清除所有对话数据</el-button>
                </div>
              </div>

              <!-- 关于 -->
              <div v-show="activeSettingTab === 'about'">
                <div class="setting-group">
                  <h4>AI Diagnostic Platform</h4>
                  <p class="setting-desc">版本 v0.1.0</p>
                </div>
                <div class="setting-group">
                  <h4>服务条款</h4>
                  <p class="setting-desc">本平台为 AI 驱动的设备日志诊断工具。上传的日志文件仅用于分析诊断，AI 分析结果仅供参考。</p>
                </div>
              </div>
            </div>
          </div>
        </div>
      </transition>
    </teleport>

    <!-- ============================================================ -->
    <!-- 对话主区域 — ChatGPT 风格居中                                 -->
    <!-- ============================================================ -->
    <main class="chat-main" :class="{ 'has-messages': messages.length > 0 }">
      <!-- 空状态：提示语 + 输入框整体居中 -->
      <div v-if="messages.length === 0" class="welcome-full">
        <div class="welcome-inner">
          <div class="welcome-icon">
            <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="#9ca3af" stroke-width="1.5"><circle cx="12" cy="12" r="10"/><path d="M8 14s1.5 2 4 2 4-2 4-2"/><line x1="9" y1="9" x2="9.01" y2="9"/><line x1="15" y1="9" x2="15.01" y2="9"/></svg>
          </div>
          <h2>有什么可以帮助你的？</h2>
        </div>
        <!-- 输入框也在居中区域内 -->
        <div class="welcome-input">
          <div class="input-container">
            <div v-if="attachedFile" class="attached-file">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21.44 11.05l-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48"/></svg>
              <span>{{ attachedFile.name }}</span>
              <button class="remove-file" @click="attachedFile = null">&times;</button>
            </div>
            <div class="input-box">
              <textarea ref="inputEl" v-model="inputText" placeholder="输入问题或拖拽日志文件..." class="msg-textarea" :rows="1" @keydown.enter.exact.prevent="sendMessage" @input="autoResize"></textarea>
              <div class="input-actions">
                <div class="actions-left">
                  <el-select v-model="selectedModel" size="small" class="model-select"><el-option label="Mock (开发模式)" value="mock" /><el-option label="DeepSeek" value="deepseek" /></el-select>
                  <button class="action-btn report-btn" :disabled="!canGenerateReport" title="生成诊断报告" @click="generateDiagnosticReport"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg><span v-if="messages.length > 0">生成报告</span></button>
                </div>
                <div class="actions-right">
                  <label class="action-btn attach-btn" title="上传文件"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="m21.44 11.05-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48"/></svg><input type="file" accept=".log,.txt,.zip" @change="onFileInput" hidden /></label>
                  <button class="action-btn send-btn" :disabled="!inputText.trim() && !attachedFile" :class="{ active: inputText.trim() || attachedFile }" @click="sendMessage"><svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor" stroke="none"><path d="M2.01 21 23 12 2.01 3 2 10l15 2-15 2z"/></svg></button>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- 有消息时 -->
      <template v-else>
        <div class="chat-messages" ref="msgContainer">
          <div v-for="msg in messages" :key="msg.id" class="message-row" :class="msg.role">
            <div class="message-avatar" v-if="msg.role === 'assistant'"><svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#2563eb" stroke-width="1.5"><circle cx="12" cy="12" r="10"/><path d="M8 14s1.5 2 4 2 4-2 4-2"/></svg></div>
            <div class="message-body"><div class="message-bubble"><div class="msg-content" v-html="renderContent(msg.content)"></div></div></div>
          </div>
          <div v-if="loading" class="message-row assistant">
            <div class="message-avatar"><svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#2563eb" stroke-width="1.5"><circle cx="12" cy="12" r="10"/><path d="M8 14s1.5 2 4 2 4-2 4-2"/></svg></div>
            <div class="message-body"><div class="message-bubble typing"><span class="dot"></span><span class="dot"></span><span class="dot"></span></div></div>
          </div>
        </div>
        <div class="input-wrapper">
          <div class="input-container">
            <div v-if="attachedFile" class="attached-file"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21.44 11.05l-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48"/></svg><span>{{ attachedFile.name }}</span><button class="remove-file" @click="attachedFile = null">&times;</button></div>
            <div class="input-box">
              <textarea ref="inputEl" v-model="inputText" placeholder="输入问题或拖拽日志文件..." class="msg-textarea" :rows="1" @keydown.enter.exact.prevent="sendMessage" @input="autoResize"></textarea>
              <div class="input-actions">
                <div class="actions-left">
                  <el-select v-model="selectedModel" size="small" class="model-select"><el-option label="Mock (开发模式)" value="mock" /><el-option label="DeepSeek" value="deepseek" /></el-select>
                  <button class="action-btn report-btn" :disabled="!canGenerateReport" title="生成诊断报告" @click="generateDiagnosticReport"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg><span v-if="messages.length > 0">生成报告</span></button>
                </div>
                <div class="actions-right">
                  <label class="action-btn attach-btn" title="上传文件"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="m21.44 11.05-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48"/></svg><input type="file" accept=".log,.txt,.zip" @change="onFileInput" hidden /></label>
                  <button class="action-btn send-btn" :disabled="!inputText.trim() && !attachedFile" :class="{ active: inputText.trim() || attachedFile }" @click="sendMessage"><svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor" stroke="none"><path d="M2.01 21 23 12 2.01 3 2 10l15 2-15 2z"/></svg></button>
                </div>
              </div>
            </div>
          </div>
        </div>
      </template>
    </main>
  </div>
</template>

<script setup lang="ts">
import { ref, nextTick, onMounted, reactive, computed } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { chatApi, type ChatMessage } from '@/api/chat'

const router = useRouter()
const sidebarCollapsed = ref(false)
const selectedModel = ref('mock')
const inputText = ref('')
const loading = ref(false)
const attachedFile = ref<File | null>(null)
const inputEl = ref<HTMLTextAreaElement>()
const msgContainer = ref<HTMLElement>()
const messages = ref<ChatMessage[]>([])
const currentChatId = ref('')
const canGenerateReport = ref(false)
const showUserMenu = ref(false)
const showSettings = ref(false)

const settings = reactive({ theme: (localStorage.getItem('theme') || 'light'), language: 'zh-CN' })
const activeSettingTab = ref('general')
const settingTabs = [
  { key: 'general', label: '通用', icon: '⚙️' },
  { key: 'account', label: '账号管理', icon: '👤' },
  { key: 'data', label: '数据管理', icon: '🗄️' },
  { key: 'about', label: '服务协议', icon: '📄' },
]

interface ChatRecord { id: string; title: string; pinned?: boolean; messages?: ChatMessage[] }
const recentChats = ref<ChatRecord[]>([])
const chatMenu = reactive({ visible: false, x: 0, y: 0, chatId: '' })

const userName = ref('用户')
const userInitial = computed(() => userName.value.charAt(0).toUpperCase())

// ============================================================
function toggleSidebar() { sidebarCollapsed.value = !sidebarCollapsed.value }
function toggleSearch() {}
function navigateTo(path: string) { router.push(path) }
function saveSettings() { localStorage.setItem('theme', settings.theme) }

function newChat() { messages.value = []; currentChatId.value = ''; canGenerateReport.value = false; inputText.value = ''; attachedFile.value = null }
function selectChat(id: string) { const chat = recentChats.value.find(c => c.id === id); if (chat?.messages) { currentChatId.value = id; messages.value = [...chat.messages]; canGenerateReport.value = true; nextTick(() => { if (msgContainer.value) msgContainer.value.scrollTop = msgContainer.value.scrollHeight }) } }
function saveCurrentChat() { if (!currentChatId.value || messages.value.length === 0) return; const chat = recentChats.value.find(c => c.id === currentChatId.value); if (chat) { chat.messages = [...messages.value]; saveChats() } }
function openChatMenu(e: MouseEvent, chat: ChatRecord) { chatMenu.visible = true; chatMenu.x = e.clientX - 8; chatMenu.y = e.clientY + 4; chatMenu.chatId = chat.id }
function closeChatMenu() { chatMenu.visible = false }
async function renameChat() { const chat = recentChats.value.find(c => c.id === chatMenu.chatId); if (!chat) return; try { const { value } = await ElMessageBox.prompt('新标题', '重命名', { inputValue: chat.title }); if (value?.trim()) { chat.title = value.trim(); saveChats() } } catch {}; closeChatMenu() }
function pinChat() { const idx = recentChats.value.findIndex(c => c.id === chatMenu.chatId); if (idx > 0) { const [item] = recentChats.value.splice(idx, 1); recentChats.value.unshift(item); saveChats() }; closeChatMenu() }
function analyzeChat() { ElMessage.info('分析功能开发中'); closeChatMenu() }
function deleteChat() { recentChats.value = recentChats.value.filter(c => c.id !== chatMenu.chatId); saveChats(); closeChatMenu() }
function autoTitle(text: string, file?: File | null): string { if (file) return file.name.length > 24 ? file.name.slice(0, 24) + '…' : file.name; const cleaned = text.replace(/[🎯📊🔍❌📚]/g, '').trim(); return cleaned.length > 28 ? cleaned.slice(0, 28) + '…' : cleaned }
function addChatToHistory(title: string) { const id = Date.now().toString(); recentChats.value.unshift({ id, title, messages: [...messages.value] }); currentChatId.value = id; saveChats() }
function saveChats() { localStorage.setItem('recent-chats', JSON.stringify(recentChats.value.map(({ id, title, pinned, messages: m }) => ({ id, title, pinned, messages: m })))) }

// 用户
function downloadApp() { ElMessage.info('桌面版下载页面开发中'); showUserMenu.value = false }
function openSettings() { showUserMenu.value = false; showSettings.value = true }
function openHelp() { ElMessage.info('帮助文档开发中'); showUserMenu.value = false }
function logout() { ElMessage.success('已退出登录'); showUserMenu.value = false }
async function changePwd() { try { const { value } = await ElMessageBox.prompt('请输入新密码', '修改密码', { inputType: 'password' }); if (value) ElMessage.success('密码修改成功') } catch {} }
async function clearData() { try { await ElMessageBox.confirm('确定清除所有对话数据？不可恢复。', '确认', { type: 'warning' }); localStorage.removeItem('recent-chats'); recentChats.value = []; ElMessage.success('已清除'); showSettings.value = false } catch {} }

// 消息
function onFileInput(e: Event) { const t = e.target as HTMLInputElement; if (t.files?.[0]) attachedFile.value = t.files[0] }
function autoResize() { if (!inputEl.value) return; inputEl.value.style.height = 'auto'; inputEl.value.style.height = Math.min(inputEl.value.scrollHeight, 200) + 'px' }
function addMessage(role: 'user' | 'assistant', content: string) { messages.value.push({ id: Date.now().toString(), role, content, timestamp: new Date().toLocaleTimeString() }); nextTick(() => { if (msgContainer.value) msgContainer.value.scrollTop = msgContainer.value.scrollHeight }) }
function renderContent(text: string) { return text.replace(/\n/g, '<br>').replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>') }

async function sendMessage() {
  const text = inputText.value.trim(); const file = attachedFile.value
  if (!text && !file) return
  addMessage('user', text || `[上传文件: ${file?.name}]`)
  const isNew = messages.value.length <= 2
  inputText.value = ''; attachedFile.value = null; if (inputEl.value) inputEl.value.style.height = 'auto'
  loading.value = true
  try {
    let logId: number | null = null
    if (file) { const fd = new FormData(); fd.append('file', file); fd.append('description', text); logId = (await chatApi.uploadLog(fd)).data.id }
    if (logId) {
      addMessage('assistant', '🔍 正在解析日志并运行分析...')
      const analysisRes = await chatApi.runAnalysis(logId)
      if (analysisRes.data.id) {
        const detail = (await chatApi.getAnalysisResult(analysisRes.data.id)).data
        let response = `## 📊 分析结果\n\n**摘要：** ${detail.summary}\n\n**根因分析：** ${detail.root_cause}\n\n**置信度：** ${((detail.confidence || 0) * 100).toFixed(0)}%\n\n**建议措施：**\n`
        if (detail.next_steps) detail.next_steps.forEach((s: string, i: number) => { response += `${i + 1}. ${s}\n` })
        canGenerateReport.value = true; addMessage('assistant', response)
        if (isNew) addChatToHistory(autoTitle(text, file))
      }
    } else if (text) {
      const items = (await chatApi.searchKnowledge(text)).data.items || []
      if (items.length > 0) { let response = `## 📚 知识库搜索结果\n\n找到 ${items.length} 条相关知识：\n\n`; items.slice(0, 3).forEach((item: any, i: number) => { response += `**${i + 1}. ${item.title}** (${item.doc_type})\n${item.snippet}\n\n` }); addMessage('assistant', response) }
      else addMessage('assistant', '未找到相关知识。请上传日志文件进行详细分析，或尝试其他关键词。')
      if (isNew) addChatToHistory(autoTitle(text))
    }
    saveCurrentChat()
  } catch (e: any) { addMessage('assistant', `❌ 分析失败：${e.response?.data?.detail || e.message}`) }
  finally { loading.value = false }
}
async function generateDiagnosticReport() { ElMessage.info('报告生成功能开发中') }

onMounted(() => { recentChats.value = JSON.parse(localStorage.getItem('recent-chats') || '[]') })
</script>

<style scoped>
/* ============================================================
   全局
   ============================================================ */
.chat-layout { display: flex; height: 100vh; background: #fff; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; }

/* ============================================================
   侧边栏
   ============================================================ */
.sidebar { width: 260px; background: #f9fafb; border-right: 1px solid #e5e7eb; flex-shrink: 0; overflow: hidden; transition: width 0.2s ease; }
.sidebar.collapsed { width: 0; border-right: none; }
.sidebar-inner { width: 260px; display: flex; flex-direction: column; height: 100%; }
.sidebar-top { display: flex; align-items: center; gap: 8px; padding: 12px 14px; }
.sidebar-icon-btn { width: 36px; height: 36px; border-radius: 50%; border: none; background: transparent; color: #6b7280; cursor: pointer; display: flex; align-items: center; justify-content: center; transition: background 0.15s; flex-shrink: 0; }
.sidebar-icon-btn:hover { background: #e5e7eb; color: #1f2937; }
.sidebar-new-chat { padding: 4px 10px; }
.new-chat-btn { display: flex; align-items: center; gap: 8px; width: 100%; padding: 10px 12px; border-radius: 8px; border: 1px solid #d1d5db; background: #fff; color: #374151; cursor: pointer; font-size: 14px; transition: background 0.15s; }
.new-chat-btn:hover { background: #f3f4f6; }
.sidebar-nav { padding: 4px 10px; }
.nav-item { display: flex; align-items: center; gap: 10px; padding: 10px 12px; border-radius: 8px; cursor: pointer; font-size: 14px; color: #374151; margin-bottom: 2px; transition: background 0.12s; }
.nav-item:hover { background: #e5e7eb; }
.sidebar-history { flex: 1; overflow-y: auto; padding: 8px 10px; }
.section-title { font-size: 12px; color: #9ca3af; padding: 8px 12px 4px; letter-spacing: 0.5px; }
.history-item { display: flex; align-items: center; padding: 8px 12px; border-radius: 6px; cursor: pointer; font-size: 13px; color: #4b5563; transition: background 0.12s; }
.history-item:hover { background: #e5e7eb; }
.history-item.active { background: #dbeafe; color: #2563eb; }
.history-title { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.history-more-btn { width: 26px; height: 26px; border-radius: 6px; border: none; background: transparent; color: #9ca3af; cursor: pointer; display: flex; align-items: center; justify-content: center; flex-shrink: 0; opacity: 0; transition: opacity 0.15s, background 0.12s; }
.history-item:hover .history-more-btn { opacity: 1; }
.history-more-btn:hover { background: #d1d5db; color: #374151; }
.empty-hint { font-size: 12px; color: #9ca3af; padding: 12px; text-align: center; }
.sidebar-user { display: flex; align-items: center; gap: 10px; padding: 12px 14px; border-top: 1px solid #e5e7eb; cursor: pointer; transition: background 0.12s; margin-top: auto; }
.sidebar-user:hover { background: #e5e7eb; }
.user-avatar { width: 30px; height: 30px; border-radius: 50%; background: #2563eb; color: #fff; display: flex; align-items: center; justify-content: center; font-size: 14px; font-weight: 600; flex-shrink: 0; }
.user-name { font-size: 13px; color: #374151; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

.float-open-btn { position: fixed; left: 12px; top: 12px; z-index: 50; width: 36px; height: 36px; border-radius: 50%; border: 1px solid #e5e7eb; background: #fff; color: #6b7280; cursor: pointer; display: flex; align-items: center; justify-content: center; box-shadow: 0 2px 8px rgba(0,0,0,0.08); transition: all 0.15s; }
.float-open-btn:hover { background: #f3f4f6; color: #1f2937; }

/* 弹出菜单 */
.menu-overlay { position: fixed; inset: 0; z-index: 99; }
.chat-menu-popup, .user-menu-popup { position: fixed; z-index: 100; background: #fff; border: 1px solid #e5e7eb; border-radius: 10px; box-shadow: 0 8px 24px rgba(0,0,0,0.12); padding: 4px; min-width: 160px; animation: menuIn 0.12s ease; }
@keyframes menuIn { from { opacity: 0; transform: translateY(-4px); } to { opacity: 1; transform: translateY(0); } }
.chat-menu-popup button, .user-menu-popup button { display: flex; align-items: center; gap: 8px; width: 100%; padding: 8px 12px; border: none; background: transparent; font-size: 13px; color: #374151; cursor: pointer; border-radius: 6px; transition: background 0.1s; }
.chat-menu-popup button:hover, .user-menu-popup button:hover { background: #f3f4f6; }
.chat-menu-popup button.danger:hover, .user-menu-popup button.danger:hover { background: #fef2f2; color: #ef4444; }
.chat-menu-popup hr, .user-menu-popup hr { margin: 4px 0; border: none; border-top: 1px solid #e5e7eb; }
.user-menu-popup { bottom: 60px; left: 14px; }

/* 设置弹窗 — 平滑缩放动画 + 左右分栏 */
.settings-overlay { background: rgba(0,0,0,0.3) !important; }
.settings-dialog {
  position: fixed; top: 50%; left: 50%; transform: translate(-50%, -50%);
  z-index: 100; background: #fff; border-radius: 14px;
  box-shadow: 0 16px 48px rgba(0,0,0,0.18);
  width: 680px; height: 520px; max-height: 80vh; overflow: hidden;
  display: flex; flex-direction: column;
}
/* Vue transition — 平滑缩放 */
.settings-modal-enter-active { transition: all 0.2s cubic-bezier(0.22, 0.61, 0.36, 1); }
.settings-modal-leave-active { transition: all 0.15s cubic-bezier(0.55, 0, 1, 0.45); }
.settings-modal-enter-from { opacity: 0; transform: translate(-50%, -50%) scale(0.92); }
.settings-modal-leave-to { opacity: 0; transform: translate(-50%, -50%) scale(0.92); }

.settings-header { display: flex; align-items: center; justify-content: space-between; padding: 18px 24px; border-bottom: 1px solid #f3f4f6; flex-shrink: 0; }
.settings-header h3 { font-size: 17px; font-weight: 600; color: #1f2937; margin: 0; }
.settings-close { background: none; border: none; font-size: 22px; color: #9ca3af; cursor: pointer; padding: 0 4px; line-height: 1; border-radius: 6px; transition: all 0.12s; }
.settings-close:hover { color: #374151; background: #f3f4f6; }

/* 左右分栏 */
/* 左右分栏 — 固定高度 */
.settings-layout { display: flex; flex: 1; overflow: hidden; min-height: 0; }
.settings-nav {
  width: 170px; background: #f9fafb; padding: 12px 8px;
  display: flex; flex-direction: column; gap: 2px;
  flex-shrink: 0;
}
.settings-nav-item {
  display: flex; align-items: center; gap: 10px; padding: 10px 12px;
  border-radius: 8px; cursor: pointer; font-size: 13px; color: #4b5563;
  transition: all 0.12s;
}
.settings-nav-item:hover { background: #e5e7eb; }
.settings-nav-item.active { background: #eff6ff; color: #2563eb; font-weight: 500; }

/* 右侧内容 — 固定高度 + 内部滚动，切换 tab 不改变弹窗尺寸 */
.settings-content {
  flex: 1; padding: 20px 24px;
  overflow-y: auto; overflow-x: hidden;
  min-height: 0;
}
/* 每个 tab 内容区统一最小高度，少内容时有留白而非收缩 */
.settings-content > div {
  min-height: 100%;
  display: flex; flex-direction: column; justify-content: flex-start;
}

.setting-group { margin-bottom: 20px; }
.setting-group h4 { font-size: 14px; font-weight: 600; color: #1f2937; margin-bottom: 10px; }
.setting-row { display: flex; align-items: center; justify-content: space-between; padding: 8px 0; }
.setting-row span { font-size: 14px; color: #374151; }
.setting-value { color: #6b7280 !important; }
.setting-desc { font-size: 13px; color: #6b7280; line-height: 1.6; margin-bottom: 10px; }
.theme-switch { display: flex; gap: 4px; }
.theme-switch button { padding: 6px 14px; border-radius: 8px; border: 1px solid #e5e7eb; background: #fff; font-size: 13px; color: #6b7280; cursor: pointer; transition: all 0.12s; }
.theme-switch button.active { background: #eff6ff; border-color: #2563eb; color: #2563eb; }
.theme-switch button:hover:not(.active) { background: #f3f4f6; }

/* ============================================================
   对话区 — ChatGPT 风格：空状态整体居中
   ============================================================ */
.chat-main { flex: 1; display: flex; flex-direction: column; min-width: 0; position: relative; }

/* 空状态：flex居中整块内容 */
.welcome-full { flex: 1; display: flex; flex-direction: column; align-items: center; justify-content: center; padding: 0 24px; gap: 24px; }
.welcome-inner { text-align: center; }
.welcome-icon { margin-bottom: 12px; opacity: 0.5; }
.welcome-inner h2 { font-size: 22px; font-weight: 500; color: #374151; margin: 0; }
.welcome-input { width: 100%; max-width: 720px; }

/* 有消息 */
.chat-messages { flex: 1; overflow-y: auto; padding: 24px; display: flex; flex-direction: column; align-items: center; }
.message-row { display: flex; gap: 10px; margin-bottom: 24px; width: 100%; max-width: 768px; }
.message-row.user { justify-content: flex-end; }
.message-row.assistant { justify-content: flex-start; }
.message-avatar { flex-shrink: 0; width: 30px; height: 30px; display: flex; align-items: center; justify-content: center; }
.message-body { max-width: 85%; }
.message-bubble { padding: 12px 16px; border-radius: 12px; line-height: 1.65; font-size: 14px; color: #1f2937; }
.message-row.user .message-bubble { background: #eff6ff; border: 1px solid #bfdbfe; border-bottom-right-radius: 4px; }
.message-row.assistant .message-bubble { background: #fff; border: 1px solid #e5e7eb; border-bottom-left-radius: 4px; }
.typing { display: flex; gap: 5px; align-items: center; padding: 14px 18px; }
.dot { width: 7px; height: 7px; border-radius: 50%; background: #9ca3af; animation: bounce 1.4s infinite ease-in-out both; }
.dot:nth-child(1) { animation-delay: -0.32s; }
.dot:nth-child(2) { animation-delay: -0.16s; }
@keyframes bounce { 0%,80%,100% { transform: scale(0); } 40% { transform: scale(1); } }

/* 输入框 */
.input-wrapper { display: flex; justify-content: center; padding: 12px 24px 20px; }
.input-container { width: 100%; max-width: 720px; }
.attached-file { display: flex; align-items: center; gap: 6px; padding: 6px 10px; background: #f3f4f6; border: 1px solid #e5e7eb; border-radius: 8px 8px 0 0; font-size: 13px; color: #4b5563; }
.remove-file { margin-left: auto; background: none; border: none; font-size: 18px; cursor: pointer; color: #9ca3af; }
.remove-file:hover { color: #ef4444; }
.input-box { border: 1px solid #d1d5db; border-radius: 12px; background: #fff; box-shadow: 0 2px 8px rgba(0,0,0,0.04); transition: border-color 0.15s, box-shadow 0.15s; overflow: hidden; }
.input-box:focus-within { border-color: #2563eb; box-shadow: 0 0 0 3px rgba(37,99,235,0.1); }
.attached-file + .input-box { border-radius: 0 0 12px 12px; border-top: none; }
.msg-textarea { width: 100%; border: none; outline: none; resize: none; padding: 14px 16px 8px; font-size: 15px; line-height: 1.6; font-family: inherit; color: #1f2937; background: transparent; min-height: 48px; }
.msg-textarea::placeholder { color: #9ca3af; }
.input-actions { display: flex; align-items: center; justify-content: space-between; padding: 4px 12px 10px; }
.actions-left, .actions-right { display: flex; align-items: center; gap: 6px; }
.model-select { width: 150px; }
:deep(.model-select .el-input__wrapper) { border-radius: 20px; box-shadow: none !important; border: 1px solid #e5e7eb; padding: 0 12px; height: 30px; font-size: 13px; }
:deep(.model-select .el-input__wrapper:hover) { border-color: #d1d5db; }
.action-btn { display: inline-flex; align-items: center; gap: 5px; height: 30px; padding: 0 10px; border-radius: 20px; border: 1px solid #e5e7eb; background: #fff; color: #6b7280; cursor: pointer; font-size: 13px; transition: all 0.15s; }
.action-btn:hover { background: #f3f4f6; color: #374151; }
.action-btn:disabled { opacity: 0.4; cursor: not-allowed; }
.attach-btn { width: 30px; padding: 0; justify-content: center; cursor: pointer; }
.send-btn { width: 30px; padding: 0; justify-content: center; }
.send-btn.active { background: #2563eb; border-color: #2563eb; color: #fff; }
.send-btn.active:hover { background: #1d4ed8; }
</style>
