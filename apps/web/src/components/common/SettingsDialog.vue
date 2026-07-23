<template>
  <teleport to="body">
    <div v-if="visible" class="menu-overlay settings-overlay" @click="$emit('close')"></div>
    <transition name="settings-modal">
      <div v-if="visible" class="settings-dialog">
        <div class="settings-header">
          <h3>设置</h3>
          <button class="settings-close" @click="$emit('close')">&times;</button>
        </div>
        <div class="settings-layout">
          <!-- 左侧导航 -->
          <nav class="settings-nav">
            <div
              v-for="tab in tabs"
              :key="tab.key"
              class="settings-nav-item"
              :class="{ active: activeTab === tab.key }"
              @click="activeTab = tab.key"
            >
              <span v-html="tab.icon"></span>
              <span>{{ tab.label }}</span>
            </div>
          </nav>
          <!-- 右侧内容 -->
          <div class="settings-content">
            <!-- 通用 -->
            <div v-show="activeTab === 'general'">
              <div class="setting-group">
                <h4>主题</h4>
                <div class="theme-switch">
                  <button
                    v-for="opt in themeOptions"
                    :key="opt.value"
                    :class="{ active: theme === opt.value }"
                    @click="updateTheme(opt.value)"
                  >
                    {{ opt.icon }} {{ opt.label }}
                  </button>
                </div>
              </div>
              <div class="setting-group">
                <h4>语言</h4>
                <el-select v-model="language" size="small" style="width:150px" @change="saveSettings">
                  <el-option label="简体中文" value="zh-CN" />
                  <el-option label="English" value="en" />
                </el-select>
              </div>
            </div>

            <!-- 账号 -->
            <div v-show="activeTab === 'account'">
              <div class="setting-group">
                <h4>个人信息</h4>
                <div class="setting-row">
                  <span>用户名</span>
                  <span class="setting-value">{{ userName }}</span>
                </div>
              </div>
              <div class="setting-group">
                <h4>安全</h4>
                <div class="setting-row">
                  <span>修改密码</span>
                  <el-button size="small" @click="$emit('changePassword')">修改</el-button>
                </div>
              </div>
            </div>

            <!-- 数据 -->
            <div v-show="activeTab === 'data'">
              <div class="setting-group">
                <h4>清除数据</h4>
                <p class="setting-desc">清除后将不可恢复，请谨慎操作。</p>
                <el-button size="small" type="danger" @click="$emit('clearData')">清除所有对话数据</el-button>
              </div>
            </div>

            <!-- 关于 -->
            <div v-show="activeTab === 'about'">
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
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { ElSelect, ElOption, ElButton } from 'element-plus'
import { applyTheme, getSavedTheme, type ThemePreference } from '@/composables/useTheme'

const props = defineProps<{
  visible: boolean
  userName: string
}>()

const emit = defineEmits<{
  (e: 'close'): void
  (e: 'changePassword'): void
  (e: 'clearData'): void
}>()

const theme = ref<ThemePreference>(getSavedTheme())
const language = ref('zh-CN')
const activeTab = ref('general')

const tabs = [
  { key: 'general', label: '通用', icon: '⚙️' },
  { key: 'account', label: '账号管理', icon: '👤' },
  { key: 'data', label: '数据管理', icon: '🗄️' },
  { key: 'about', label: '服务协议', icon: '📄' },
]

const themeOptions = [
  { value: 'light', label: '浅色', icon: '☀️' },
  { value: 'dark', label: '深色', icon: '🌙' },
  { value: 'system', label: '跟随系统', icon: '💻' },
]

function updateTheme(value: ThemePreference) {
  theme.value = value
  applyTheme(value)
  saveSettings()
}

function saveSettings() {
  localStorage.setItem('theme', theme.value)
}

// Reset tab when dialog opens
watch(() => props.visible, (v) => {
  if (v) activeTab.value = 'general'
})
</script>

<style scoped>
.settings-overlay {
  background: rgba(0, 0, 0, 0.3) !important;
}

.settings-dialog {
  position: fixed;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  z-index: 100;
  background: #fff;
  border-radius: 14px;
  box-shadow: 0 16px 48px rgba(0, 0, 0, 0.18);
  width: 680px;
  height: 520px;
  max-height: 80vh;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.settings-modal-enter-active {
  transition: all 0.2s cubic-bezier(0.22, 0.61, 0.36, 1);
}

.settings-modal-leave-active {
  transition: all 0.15s cubic-bezier(0.55, 0, 1, 0.45);
}

.settings-modal-enter-from,
.settings-modal-leave-to {
  opacity: 0;
  transform: translate(-50%, -50%) scale(0.92);
}

.settings-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 18px 24px;
  border-bottom: 1px solid #f3f4f6;
  flex-shrink: 0;
}

.settings-header h3 {
  font-size: 17px;
  font-weight: 600;
  color: #1f2937;
  margin: 0;
}

.settings-close {
  background: none;
  border: none;
  font-size: 22px;
  color: #9ca3af;
  cursor: pointer;
  padding: 0 4px;
  line-height: 1;
  border-radius: 6px;
  transition: all 0.12s;
}

.settings-close:hover {
  color: #374151;
  background: #f3f4f6;
}

.settings-layout {
  display: flex;
  flex: 1;
  overflow: hidden;
  min-height: 0;
}

.settings-nav {
  width: 170px;
  background: #f9fafb;
  padding: 12px 8px;
  display: flex;
  flex-direction: column;
  gap: 2px;
  flex-shrink: 0;
}

.settings-nav-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 12px;
  border-radius: 8px;
  cursor: pointer;
  font-size: 13px;
  color: #4b5563;
  transition: all 0.12s;
}

.settings-nav-item:hover {
  background: #e5e7eb;
}

.settings-nav-item.active {
  background: #edf3fe;
  color: #2563eb;
  font-weight: 500;
}

.settings-content {
  flex: 1;
  padding: 20px 24px;
  overflow-y: auto;
  overflow-x: hidden;
  min-height: 0;
}

.settings-content > div {
  min-height: 100%;
  display: flex;
  flex-direction: column;
  justify-content: flex-start;
}

.setting-group {
  margin-bottom: 20px;
}

.setting-group h4 {
  font-size: 14px;
  font-weight: 600;
  color: #1f2937;
  margin-bottom: 10px;
}

.setting-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 0;
}

.setting-row span {
  font-size: 14px;
  color: #374151;
}

.setting-value {
  color: #6b7280 !important;
}

.setting-desc {
  font-size: 13px;
  color: #6b7280;
  line-height: 1.6;
  margin-bottom: 10px;
}

.theme-switch {
  display: flex;
  gap: 4px;
}

.theme-switch button {
  padding: 6px 14px;
  border-radius: 8px;
  border: 1px solid #e5e7eb;
  background: #fff;
  font-size: 13px;
  color: #6b7280;
  cursor: pointer;
  transition: all 0.12s;
}

.theme-switch button.active {
  background: #edf3fe;
  border-color: #2563eb;
  color: #2563eb;
}

.theme-switch button:hover:not(.active) {
  background: #f3f4f6;
}

.menu-overlay {
  position: fixed;
  inset: 0;
  z-index: 99;
}
</style>
