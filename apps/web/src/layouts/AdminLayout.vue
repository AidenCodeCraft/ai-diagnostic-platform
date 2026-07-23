<template>
  <div class="admin-layout">
    <!-- 顶部导航 -->
    <header class="admin-topbar">
      <div class="topbar-left">
        <button class="topbar-menu-btn" @click="sidebarOpen = !sidebarOpen" title="菜单">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="3" y1="6" x2="21" y2="6"/><line x1="3" y1="12" x2="21" y2="12"/><line x1="3" y1="18" x2="21" y2="18"/></svg>
        </button>
        <span class="topbar-brand">管理后台</span>
      </div>
      <div class="topbar-right">
        <span class="topbar-user">{{ userStore.userName }}</span>
        <el-button size="small" @click="$router.push('/chat')">返回对话</el-button>
        <el-button size="small" @click="handleLogout">退出登录</el-button>
      </div>
    </header>

    <div class="admin-body">
      <!-- 侧边菜单 -->
      <aside class="admin-sidebar" :class="{ open: sidebarOpen }">
        <nav class="admin-menu">
          <router-link to="/admin/overview" class="menu-item" active-class="active">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/></svg>
            <span>系统概览</span>
          </router-link>
          <router-link to="/admin/users" class="menu-item" active-class="active">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>
            <span>用户管理</span>
          </router-link>
          <router-link to="/admin/audit" class="menu-item" active-class="active">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/></svg>
            <span>审核监控</span>
          </router-link>
          <router-link to="/admin/settings" class="menu-item" active-class="active">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>
            <span>系统配置</span>
          </router-link>
        </nav>
      </aside>

      <!-- 遮罩（移动端） -->
      <div v-if="sidebarOpen" class="sidebar-overlay" @click="sidebarOpen = false"></div>

      <!-- 内容区 -->
      <main class="admin-content">
        <router-view />
      </main>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useUserStore } from '@/stores/user'

const router = useRouter()
const userStore = useUserStore()
const sidebarOpen = ref(true)

function handleLogout() {
  userStore.logout()
  router.push('/login')
}
</script>

<style scoped>
.admin-layout { display: flex; flex-direction: column; height: 100vh; background: #f3f4f6; }
.admin-topbar {
  display: flex; align-items: center; justify-content: space-between;
  height: 48px; padding: 0 16px; background: #fff; border-bottom: 1px solid #e5e7eb;
  flex-shrink: 0; z-index: 100;
}
.topbar-left { display: flex; align-items: center; gap: 12px; }
.topbar-menu-btn { width: 32px; height: 32px; border: none; background: none; cursor: pointer; color: #374151; border-radius: 6px; display: flex; align-items: center; justify-content: center; }
.topbar-menu-btn:hover { background: #f3f4f6; }
.topbar-brand { font-size: 15px; font-weight: 600; color: #1f2937; }
.topbar-right { display: flex; align-items: center; gap: 8px; }
.topbar-user { font-size: 13px; color: #6b7280; }

.admin-body { display: flex; flex: 1; overflow: hidden; position: relative; }
.admin-sidebar {
  width: 200px; flex-shrink: 0; background: #fff; border-right: 1px solid #e5e7eb;
  overflow-y: auto; transition: width 0.2s;
}
.admin-sidebar:not(.open) { width: 0; overflow: hidden; }
.admin-menu { padding: 12px 8px; display: flex; flex-direction: column; gap: 2px; }
.menu-item {
  display: flex; align-items: center; gap: 10px; padding: 10px 12px;
  border-radius: 8px; font-size: 14px; color: #4b5563; text-decoration: none;
  transition: background 0.12s; white-space: nowrap;
}
.menu-item:hover { background: #f3f4f6; }
.menu-item.active { background: #edf3fe; color: #2563eb; font-weight: 500; }
.sidebar-overlay { display: none; }

.admin-content { flex: 1; overflow-y: auto; padding: 24px; }

@media (max-width: 768px) {
  .admin-sidebar { position: fixed; top: 48px; left: 0; bottom: 0; z-index: 90; }
  .admin-sidebar:not(.open) { width: 200px; transform: translateX(-100%); }
  .sidebar-overlay { display: block; position: fixed; inset: 0; top: 48px; background: rgba(0,0,0,0.3); z-index: 89; }
}
</style>
