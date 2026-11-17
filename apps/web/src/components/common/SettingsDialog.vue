<template>
  <teleport to="body">
    <div v-if="visible" class="menu-overlay settings-overlay" @click="$emit('close')"></div>
    <transition name="settings-modal">
      <div v-if="visible" class="settings-dialog">
        <div class="settings-header">
          <h3>{{ $t('settings.title') }}</h3>
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
                <h4>{{ $t('settings.theme') }}</h4>
                <div class="theme-switch">
                  <button
                    v-for="opt in themeOptions"
                    :key="opt.value"
                    :class="{ active: theme === opt.value }"
                    @click="updateTheme(opt.value as ThemePreference)"
                  >
                    {{ opt.icon }} {{ $t(`settings.${opt.value}`) }}
                  </button>
                </div>
              </div>
              <div class="setting-group">
                <h4>{{ $t('settings.language') }}</h4>
                <el-select v-model="language" size="small" style="width:150px" @change="updateLanguage">
                  <el-option :label="$t('settings.zhCN')" value="zh-CN" />
                  <el-option :label="$t('settings.en')" value="en" />
                </el-select>
              </div>
            </div>

            <!-- 账号 -->
            <div v-show="activeTab === 'account'">
              <div class="setting-group">
                <h4>{{ $t('settings.personalInfo') }}</h4>
                <div class="setting-row">
                  <span>{{ $t('settings.username') }}</span>
                  <span class="setting-value">{{ userName }}</span>
                </div>
              </div>
              <div class="setting-group">
                <h4>{{ $t('settings.security') }}</h4>
                <div class="setting-row">
                  <span>{{ $t('settings.changePwd') }}</span>
                  <el-button size="small" @click="$emit('changePassword')">{{ $t('common.edit') }}</el-button>
                </div>
              </div>
            </div>

            <!-- 数据 -->
            <div v-show="activeTab === 'data'">
              <div class="setting-group">
                <h4>{{ $t('settings.clearData') }}</h4>
                <p class="setting-desc">{{ $t('settings.clearDataDesc') }}</p>
                <el-button size="small" type="danger" @click="$emit('clearData')">{{ $t('settings.clearDataBtn') }}</el-button>
              </div>
            </div>

            <!-- 关于 -->
            <div v-show="activeTab === 'about'">
              <div class="setting-group">
                <h4>{{ $t('settings.version') }}</h4>
                <p class="setting-desc">{{ $t('settings.versionNumber') }}</p>
              </div>
              <div class="setting-group">
                <h4>{{ $t('settings.about') }}</h4>
                <p class="setting-desc">{{ $t('settings.terms') }}</p>
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
import { useI18n } from 'vue-i18n'
import { ElSelect, ElOption, ElButton } from 'element-plus'
import { getSavedTheme, setTheme, type ThemePreference } from '@/composables/useTheme'
import { setLocale, type SupportedLocale } from '@/locales'

const { locale } = useI18n()

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
const language = ref<SupportedLocale>((locale.value as SupportedLocale) || 'zh-CN')
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
  // 立即生效（所有界面实时同步），并按当前登录用户保存独立的配置（本地 + 服务端）
  setTheme(value)
}

function updateLanguage(lang: SupportedLocale) {
  language.value = lang
  setLocale(lang)
}

// Sync language with current locale on open
watch(() => props.visible, (v) => {
  if (v) {
    activeTab.value = 'general'
    language.value = (locale.value as SupportedLocale) || 'zh-CN'
  }
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

<style>
/* 深色主题（teleport 到 body，使用全局选择器，html[data-theme] 前缀保证优先级覆盖 scoped 基础样式） */
html[data-theme='dark'] .settings-overlay {
  background: rgba(0, 0, 0, 0.5) !important;
}

html[data-theme='dark'] .settings-dialog {
  background: #292a2e;
  box-shadow: 0 16px 48px rgba(0, 0, 0, 0.4);
}

html[data-theme='dark'] .settings-header {
  border-bottom-color: #3a3b40;
}

html[data-theme='dark'] .settings-header h3 {
  color: #e7e9ee;
}

html[data-theme='dark'] .settings-close {
  color: #858b97;
}

html[data-theme='dark'] .settings-close:hover {
  color: #e7e9ee;
  background: #393a40;
}

html[data-theme='dark'] .settings-nav {
  background: #222326;
}

html[data-theme='dark'] .settings-nav-item {
  color: #aeb4c0;
}

html[data-theme='dark'] .settings-nav-item:hover {
  background: #393a40;
}

html[data-theme='dark'] .settings-nav-item.active {
  background: #303a5b;
  color: #aebfff;
}

html[data-theme='dark'] .setting-group h4 {
  color: #e7e9ee;
}

html[data-theme='dark'] .setting-row span {
  color: #d3d7df;
}

html[data-theme='dark'] .setting-value {
  color: #9298a5 !important;
}

html[data-theme='dark'] .setting-desc {
  color: #aeb4c0;
}

html[data-theme='dark'] .theme-switch button {
  background: #222326;
  border-color: #46474d;
  color: #aeb4c0;
}

html[data-theme='dark'] .theme-switch button.active {
  background: #303a5b;
  border-color: #698dff;
  color: #aebfff;
}

html[data-theme='dark'] .theme-switch button:hover:not(.active) {
  background: #393a40;
}
</style>
