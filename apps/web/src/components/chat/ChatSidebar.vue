<template>
  <aside class="sidebar" :class="{ collapsed }">
    <div class="sidebar-inner">
      <div class="sidebar-top">
        <button class="sidebar-icon-btn" title="搜索" @click="$emit('toggleSearch')">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"
            stroke-linecap="round" stroke-linejoin="round">
            <circle cx="11" cy="11" r="8" />
            <path d="m21 21-4.35-4.35" />
          </svg>
        </button>
        <button class="sidebar-icon-btn" :title="collapsed ? '展开侧栏' : '收起侧栏'" @click="$emit('update:collapsed', !collapsed)">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"
            stroke-linecap="round" stroke-linejoin="round">
            <rect x="3" y="3" width="18" height="18" rx="2" />
            <path :d="collapsed ? 'M9 3v18' : 'M15 3v18'" />
          </svg>
        </button>
      </div>

      <div class="sidebar-new-chat" v-show="!collapsed">
        <button class="new-chat-btn" @click="$emit('newChat')">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <line x1="12" y1="5" x2="12" y2="19" />
            <line x1="5" y1="12" x2="19" y2="12" />
          </svg>
          <span>新对话</span>
        </button>
      </div>

      <div class="sidebar-nav" v-show="!collapsed">
        <div class="nav-item" @click="$emit('navigate', '/knowledge')">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M4 19.5v-15A2.5 2.5 0 0 1 6.5 2H20v20H6.5a2.5 2.5 0 0 1 0-5H20" />
          </svg><span>知识库</span>
        </div>
        <div class="nav-item" @click="$emit('navigate', '/plugins')">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71" />
            <path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71" />
          </svg><span>插件管理</span>
        </div>
        <div class="nav-item" @click="$emit('navigate', '/reports')">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
            <polyline points="14 2 14 8 20 8" />
            <line x1="16" y1="13" x2="8" y2="13" />
            <line x1="16" y1="17" x2="8" y2="17" />
          </svg><span>诊断报告</span>
        </div>
        <div v-if="isAdmin" class="nav-item admin-entry" @click="$emit('navigate', '/admin')">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <circle cx="12" cy="12" r="3"/>
            <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"/>
          </svg><span>管理后台</span>
        </div>
      </div>

      <div class="sidebar-history" v-show="!collapsed">
        <div class="section-title">最近对话</div>
        <div
          v-for="chat in chats"
          :key="chat.id"
          class="history-item"
          :class="{ active: chat.id === activeChatId }"
          @click="$emit('selectChat', chat.id)"
        >
          <span class="history-title">{{ chat.title }}</span>
          <button class="history-more-btn" @click.stop="$emit('chatMenu', $event, chat)">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <circle cx="12" cy="5" r="1" />
              <circle cx="12" cy="12" r="1" />
              <circle cx="12" cy="19" r="1" />
            </svg>
          </button>
        </div>
        <div v-if="chats.length === 0" class="empty-hint">暂无对话记录</div>
      </div>

      <div class="sidebar-user" v-show="!collapsed" @click="$emit('toggleUserMenu')">
        <div class="user-avatar">{{ userInitial }}</div>
        <span class="user-name">{{ userName }}</span>
      </div>
    </div>
  </aside>
</template>

<script setup lang="ts">
import type { ChatRecord } from './types'

defineProps<{
  collapsed: boolean
  chats: ChatRecord[]
  activeChatId: number
  userName: string
  userInitial: string
  isAdmin: boolean
}>()

defineEmits<{
  (e: 'update:collapsed', value: boolean): void
  (e: 'toggleSearch'): void
  (e: 'newChat'): void
  (e: 'navigate', path: string): void
  (e: 'selectChat', id: number): void
  (e: 'chatMenu', event: MouseEvent, chat: ChatRecord): void
  (e: 'toggleUserMenu'): void
}>()
</script>

<style scoped>
.sidebar {
  width: 260px;
  background: var(--chat-sidebar-bg);
  border-right: 1px solid var(--chat-sidebar-border);
  flex-shrink: 0;
  overflow: hidden;
  transition: width 0.2s ease;
}

.sidebar.collapsed {
  width: 0;
  border-right: none;
}

.sidebar-inner {
  width: 260px;
  display: flex;
  flex-direction: column;
  height: 100%;
}

.sidebar-top {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px 14px;
}

.sidebar-icon-btn {
  width: 36px;
  height: 36px;
  border-radius: 50%;
  border: none;
  background: transparent;
  color: var(--chat-sidebar-icon);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: background 0.15s;
  flex-shrink: 0;
}

.sidebar-icon-btn:hover {
  background: var(--chat-sidebar-icon-hover-bg);
  color: var(--chat-sidebar-icon-hover);
}

.sidebar-new-chat {
  padding: 4px 10px;
}

.new-chat-btn {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  padding: 10px 12px;
  border-radius: 8px;
  border: 1px solid var(--chat-sidebar-btn-border);
  background: var(--chat-sidebar-btn-bg);
  color: var(--chat-sidebar-btn-text);
  cursor: pointer;
  font-size: 14px;
  transition: background 0.15s;
}

.new-chat-btn:hover {
  background: var(--chat-sidebar-btn-hover);
}

.sidebar-nav {
  padding: 4px 10px;
}

.nav-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 12px;
  border-radius: 8px;
  cursor: pointer;
  font-size: 14px;
  color: var(--chat-sidebar-nav-text);
  margin-bottom: 2px;
  transition: background 0.12s;
}

.nav-item:hover {
  background: var(--chat-sidebar-nav-hover);
}

.sidebar-history {
  flex: 1;
  overflow-y: auto;
  padding: 8px 10px;
}

.section-title {
  font-size: 12px;
  color: var(--chat-sidebar-section);
  padding: 8px 12px 4px;
  letter-spacing: 0.5px;
}

.history-item {
  display: flex;
  align-items: center;
  padding: 8px 12px;
  border-radius: 6px;
  cursor: pointer;
  font-size: 13px;
  color: var(--chat-sidebar-history-text);
  transition: background 0.12s;
}

.history-item:hover {
  background: var(--chat-sidebar-history-hover);
}

.history-item.active {
  background: var(--chat-sidebar-history-active-bg);
  color: var(--chat-sidebar-history-active-text);
}

.history-title {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.history-more-btn {
  width: 26px;
  height: 26px;
  border-radius: 6px;
  border: none;
  background: transparent;
  color: var(--chat-sidebar-section);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  opacity: 0;
  transition: opacity 0.15s, background 0.12s;
}

.history-item:hover .history-more-btn {
  opacity: 1;
}

.history-more-btn:hover {
  background: var(--chat-sidebar-history-hover);
  color: var(--chat-sidebar-icon-hover);
}

.empty-hint {
  font-size: 12px;
  color: var(--chat-sidebar-section);
  padding: 12px;
  text-align: center;
}

.sidebar-user {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 14px;
  border-top: 1px solid var(--chat-sidebar-user-border);
  cursor: pointer;
  transition: background 0.12s;
  margin-top: auto;
}

.sidebar-user:hover {
  background: var(--chat-sidebar-nav-hover);
}

.user-avatar {
  width: 30px;
  height: 30px;
  border-radius: 50%;
  background: #6688fa;
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 14px;
  font-weight: 600;
  flex-shrink: 0;
}

.user-name {
  font-size: 13px;
  color: var(--chat-sidebar-user-text);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
