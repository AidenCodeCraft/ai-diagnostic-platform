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
      <!-- 侧边菜单：一级分组 + 二级页面，最多两级 -->
      <aside class="admin-sidebar" :class="{ open: sidebarOpen }">
        <nav class="admin-menu">
          <!-- 概览：跨域汇总，独立一级项 -->
          <router-link to="/admin/overview" class="menu-item" active-class="active">
            <svg class="menu-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" v-html="icons.overview" />
            <span class="menu-text">概览</span>
          </router-link>

          <div v-for="group in groups" :key="group.key" class="menu-group">
            <button
              class="menu-group-head"
              :class="{ collapsed: !isGroupOpen(group.key) }"
              @click="toggleGroup(group.key)"
            >
              <span class="menu-group-title">{{ group.title }}</span>
              <svg class="menu-group-chevron" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="6 9 12 15 18 9"/></svg>
            </button>
            <div v-show="isGroupOpen(group.key)" class="menu-group-items">
              <router-link
                v-for="item in group.items"
                :key="item.to"
                :to="item.to"
                class="menu-item sub"
                active-class="active"
              >
                <svg class="menu-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" v-html="icons[item.icon]" />
                <span class="menu-text">{{ item.title }}</span>
                <span v-if="badgeOf(item.badge)" class="menu-badge">{{ badgeText(item.badge) }}</span>
              </router-link>
            </div>
          </div>
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
import { onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useUserStore } from '@/stores/user'
import client from '@/api/client'

const router = useRouter()
const route = useRoute()
const userStore = useUserStore()
const sidebarOpen = ref(true)

/** 内联 SVG 路径片段（常量字符串，非用户输入） */
const icons: Record<string, string> = {
  overview: '<rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/>',
  users: '<path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/>',
  org: '<path d="M3 21h18"/><path d="M5 21V7l7-4 7 4v14"/><path d="M9 21v-6h6v6"/>',
  projects: '<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>',
  logs: '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="8" y1="13" x2="16" y2="13"/><line x1="8" y1="17" x2="16" y2="17"/>',
  audit: '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/>',
  quality: '<path d="M3 3v18h18"/><path d="M7 15l4-6 4 4 4-7"/>',
  pipeline: '<path d="M3 12h4l3 8 4-16 3 8h4"/>',
  operationLogs: '<path d="M9 11l3 3L22 4"/><path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"/>',
  settings: '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"/>',
  about: '<circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/>',
}

/** 待办角标来源：logs=失败分析任务，audit=待审知识候选，quality=待我审核样本 */
type BadgeKey = 'logs' | 'audit' | 'quality'

interface MenuItem {
  title: string
  to: string
  icon: string
  badge?: BadgeKey
}

interface MenuGroup {
  key: string
  title: string
  items: MenuItem[]
}

// 分组顺序即使用频率顺序：诊断主线 → 内容质检 → 主数据 → 低频高风险
const groups: MenuGroup[] = [
  {
    key: 'runtime',
    title: '诊断运行',
    items: [
      { title: '日志与任务', to: '/admin/logs', icon: 'logs', badge: 'logs' },
      { title: '运行监控', to: '/admin/pipeline', icon: 'pipeline' },
    ],
  },
  {
    key: 'quality',
    title: '内容与质量',
    items: [
      { title: '内容审核', to: '/admin/audit', icon: 'audit', badge: 'audit' },
      { title: '黄金集回归', to: '/admin/quality', icon: 'quality', badge: 'quality' },
    ],
  },
  {
    key: 'account',
    title: '账号与组织',
    items: [
      { title: '用户管理', to: '/admin/users', icon: 'users' },
      { title: '组织与成员', to: '/admin/organizations', icon: 'org' },
      { title: '项目管理', to: '/admin/projects', icon: 'projects' },
    ],
  },
  {
    key: 'ops',
    title: '平台运维',
    items: [
      { title: '操作审计', to: '/admin/audit-logs', icon: 'operationLogs' },
      { title: '系统配置', to: '/admin/settings', icon: 'settings' },
      { title: '关于系统', to: '/admin/about', icon: 'about' },
    ],
  },
]

// 默认全部展开：分组只做视觉聚合，不增加日常点击成本
const openGroups = ref<Record<string, boolean>>(
  Object.fromEntries(groups.map(group => [group.key, true])),
)

function isGroupOpen(key: string): boolean {
  return openGroups.value[key] !== false
}

function toggleGroup(key: string): void {
  openGroups.value = { ...openGroups.value, [key]: !isGroupOpen(key) }
}

// 直接访问 URL 或前进后退时，自动展开命中的分组
watch(
  () => route.path,
  path => {
    const group = groups.find(g => g.items.some(item => item.to === path))
    if (group && !isGroupOpen(group.key)) toggleGroup(group.key)
  },
  { immediate: true },
)

// ── 待办角标：只取总数，失败静默（角标是辅助信息，不该打扰使用） ──
const badges = ref<Record<BadgeKey, number>>({ logs: 0, audit: 0, quality: 0 })
let badgeTimer: number | undefined

async function fetchBadges(): Promise<void> {
  const [failed, drafts, pending] = await Promise.allSettled([
    client.get('/analyses', { params: { status: 'failed', page_size: 1 } }),
    client.get('/admin/knowledge/profiles/drafts'),
    client.get('/quality/golden-samples/pending', { params: { page_size: 1 } }),
  ])
  const countOf = (result: PromiseSettledResult<any>, pick: (data: any) => number): number => {
    if (result.status !== 'fulfilled') return 0
    try { return pick(result.value?.data) } catch { return 0 }
  }
  badges.value = {
    logs: countOf(failed, data => Number(data?.total) || 0),
    audit: countOf(drafts, data => (Array.isArray(data?.items) ? data.items.length : 0)),
    quality: countOf(pending, data => Number(data?.total) || 0),
  }
}

function badgeOf(key?: BadgeKey): number {
  return key ? badges.value[key] || 0 : 0
}

/** 超过 99 显示 99+，避免窄侧栏被数字撑开 */
function badgeText(key?: BadgeKey): string {
  const count = badgeOf(key)
  return count > 99 ? '99+' : String(count)
}

// 进入页面时刷新一次，之后每 60 秒刷新，切换路由也刷新（刚操作完返回即更新）
onMounted(() => {
  void fetchBadges()
  badgeTimer = window.setInterval(fetchBadges, 60_000)
})
onUnmounted(() => {
  if (badgeTimer) window.clearInterval(badgeTimer)
})
watch(() => route.path, () => { void fetchBadges() })

function handleLogout() {
  userStore.logout()
  router.push('/login')
}
</script>

<style scoped>
.admin-layout { display: flex; flex-direction: column; height: 100vh; background: var(--adm-page-bg); color: var(--chat-layout-text); }
.admin-topbar {
  display: flex; align-items: center; justify-content: space-between;
  height: 48px; padding: 0 16px; background: var(--chat-popup-bg); border-bottom: 1px solid var(--chat-popup-border);
  flex-shrink: 0; z-index: 100;
}
.topbar-left { display: flex; align-items: center; gap: 12px; }
.topbar-menu-btn { width: 32px; height: 32px; border: none; background: none; cursor: pointer; color: var(--chat-sidebar-icon); border-radius: 6px; display: flex; align-items: center; justify-content: center; }
.topbar-menu-btn:hover { background: var(--chat-sidebar-nav-hover); }
.topbar-brand { font-size: 15px; font-weight: 600; color: var(--chat-layout-text); }
.topbar-right { display: flex; align-items: center; gap: 8px; }
.topbar-user { font-size: 13px; color: var(--chat-sidebar-section); }

.admin-body { display: flex; flex: 1; overflow: hidden; position: relative; }
.admin-sidebar {
  width: 208px; flex-shrink: 0; background: var(--chat-popup-bg); border-right: 1px solid var(--chat-popup-border);
  overflow-y: auto; transition: width 0.2s;
}
.admin-sidebar:not(.open) { width: 0; overflow: hidden; }
.admin-menu { padding: 12px 8px; display: flex; flex-direction: column; gap: 2px; }

.menu-item {
  display: flex; align-items: center; gap: 10px; padding: 9px 12px;
  border-radius: 8px; font-size: 14px; color: var(--chat-sidebar-nav-text); text-decoration: none;
  transition: background 0.12s; white-space: nowrap;
}
.menu-item:hover { background: var(--chat-sidebar-nav-hover); color: var(--chat-sidebar-icon-hover); }
.menu-item.active { background: var(--chat-sidebar-history-active-bg); color: var(--chat-sidebar-history-active-text); font-weight: 500; }
.menu-icon { width: 18px; height: 18px; flex-shrink: 0; }
.menu-text { overflow: hidden; text-overflow: ellipsis; }
.sidebar-overlay { display: none; }

/* 一级分组 */
.menu-group { display: flex; flex-direction: column; gap: 2px; margin-top: 8px; }
.menu-group-head {
  display: flex; align-items: center; justify-content: space-between; gap: 8px;
  padding: 6px 12px; border: none; background: none; cursor: pointer; width: 100%;
  border-radius: 8px; font-size: 12px; font-weight: 600; letter-spacing: 0.02em;
  color: var(--chat-sidebar-section); text-align: left;
}
.menu-group-head:hover { background: var(--chat-sidebar-nav-hover); }
.menu-group-title { overflow: hidden; text-overflow: ellipsis; }
.menu-group-chevron { flex-shrink: 0; transition: transform 0.16s; }
.menu-group-head.collapsed .menu-group-chevron { transform: rotate(-90deg); }
.menu-group-items { display: flex; flex-direction: column; gap: 2px; }
.menu-item.sub { padding-left: 22px; font-size: 13px; }

/* 待办角标 */
.menu-badge {
  margin-left: auto; flex-shrink: 0; min-width: 18px; padding: 0 5px;
  border-radius: 9px; background: var(--chat-sidebar-history-active-bg); color: var(--chat-sidebar-history-active-text);
  font-size: 11px; font-weight: 600; line-height: 18px; text-align: center;
}

.admin-content { flex: 1; overflow-y: auto; padding: 24px; }

@media (max-width: 768px) {
  .admin-sidebar { position: fixed; top: 48px; left: 0; bottom: 0; z-index: 90; background: var(--chat-popup-bg); }
  .admin-sidebar:not(.open) { width: 208px; transform: translateX(-100%); }
  .sidebar-overlay { display: block; position: fixed; inset: 0; top: 48px; background: var(--adm-overlay-bg); z-index: 89; }
}
</style>
