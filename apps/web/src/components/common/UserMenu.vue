<template>
  <teleport to="body">
    <div v-if="visible" class="menu-overlay" @click="$emit('close')"></div>
    <div v-if="visible" class="user-menu-popup">
      <button @click="handleAction('download')">📥 下载桌面版</button>
      <button @click="handleAction('settings')">⚙️ 设置</button>
      <button @click="handleAction('help')">💬 帮助与反馈</button>
      <hr />
      <button class="danger" @click="handleAction('logout')">🚪 退出登录</button>
    </div>
  </teleport>
</template>

<script setup lang="ts">
defineProps<{ visible: boolean }>()

const emit = defineEmits<{
  (e: 'close'): void
  (e: 'action', action: 'download' | 'settings' | 'help' | 'logout'): void
}>()

function handleAction(action: 'download' | 'settings' | 'help' | 'logout') {
  emit('action', action)
  emit('close')
}
</script>

<style scoped>
.menu-overlay {
  position: fixed;
  inset: 0;
  z-index: 99;
}

.user-menu-popup {
  position: fixed;
  z-index: 100;
  background: var(--chat-popup-bg);
  border: 1px solid var(--chat-popup-border);
  border-radius: 10px;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.12);
  padding: 4px;
  min-width: 160px;
  animation: menuIn 0.12s ease;
  bottom: 60px;
  left: 14px;
}

@keyframes menuIn {
  from { opacity: 0; transform: translateY(-4px); }
  to { opacity: 1; transform: translateY(0); }
}

.user-menu-popup button {
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

.user-menu-popup button:hover {
  background: var(--chat-popup-hover);
}

.user-menu-popup button.danger:hover {
  background: var(--chat-popup-danger-hover-bg);
  color: var(--chat-popup-danger-hover-text);
}

.user-menu-popup hr {
  margin: 4px 0;
  border: none;
  border-top: 1px solid var(--chat-popup-border);
}
</style>
