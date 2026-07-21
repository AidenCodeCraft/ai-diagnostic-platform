import { createRouter, createWebHistory } from 'vue-router'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    // 登录页 — 独立布局，不需要 ChatLayout
    {
      path: '/login',
      name: 'Login',
      component: () => import('@/views/LoginView.vue'),
      meta: { title: '登录', guest: true },
    },
    // 主应用布局
    {
      path: '/',
      component: () => import('@/layouts/ChatLayout.vue'),
      redirect: '/chat',
      meta: { requiresAuth: true },
      children: [
        { path: '/chat', name: 'Chat', component: () => import('@/views/ChatView.vue'), meta: { title: 'AI 诊断' } },
        { path: '/knowledge', name: 'Knowledge', component: () => import('@/views/KnowledgeBase.vue'), meta: { title: '知识库' } },
        { path: '/plugins', name: 'Plugins', component: () => import('@/views/PluginManager.vue'), meta: { title: '插件管理' } },
        { path: '/reports', name: 'Reports', component: () => import('@/views/ReportList.vue'), meta: { title: '诊断报告' } },
      ],
    },
    // 管理后台 — 独立布局，需要 admin 角色
    {
      path: '/admin',
      component: () => import('@/layouts/AdminLayout.vue'),
      redirect: '/admin/overview',
      meta: { title: '管理后台', requiresAuth: true, requiresAdmin: true },
      children: [
        { path: 'overview', name: 'AdminOverview', component: () => import('@/views/admin/Overview.vue'), meta: { title: '系统概览' } },
        { path: 'users', name: 'AdminUsers', component: () => import('@/views/admin/Users.vue'), meta: { title: '用户管理' } },
        { path: 'audit', name: 'AdminAudit', component: () => import('@/views/admin/Audit.vue'), meta: { title: '审核监控' } },
        { path: 'settings', name: 'AdminSettings', component: () => import('@/views/admin/Settings.vue'), meta: { title: '系统配置' } },
      ],
    },
  ],
})

// ============================================================
// 全局路由守卫
// ============================================================
router.beforeEach((to, _from, next) => {
  const token = localStorage.getItem('token')
  const userStr = localStorage.getItem('user')
  let user: { role?: string } | null = null
  try { user = userStr ? JSON.parse(userStr) : null } catch { /* ignore */ }

  // 1) 已登录用户访问登录页 → 重定向到对话页
  if (to.meta.guest && token) {
    return next('/chat')
  }

  // 2) 需要认证但未登录 → 跳转登录页
  if (to.meta.requiresAuth && !token) {
    return next('/login')
  }

  // 3) 需要管理员权限但非 admin → 重定向到对话页
  if (to.meta.requiresAdmin && user?.role !== 'admin') {
    return next('/chat')
  }

  next()
})

export default router
