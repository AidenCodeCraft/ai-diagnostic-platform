import { createRouter, createWebHistory } from 'vue-router'

let tokenVerified = false

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/login',
      name: 'Login',
      component: () => import('@/views/LoginView.vue'),
      meta: { title: '登录', guest: true },
    },
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

async function verifyToken(): Promise<boolean> {
  const token = sessionStorage.getItem('token')
  if (!token) return false
  try {
    const resp = await fetch('/api/v1/auth/verify', {
      headers: { Authorization: `Bearer ${token}` },
    })
    return resp.ok
  } catch {
    return false
  }
}

function clearAuth() {
  sessionStorage.removeItem('token')
  sessionStorage.removeItem('user')
  tokenVerified = false
}

router.beforeEach(async (to, _from, next) => {
  const token = sessionStorage.getItem('token')
  const userStr = sessionStorage.getItem('user')
  let user: { role?: string } | null = null
  try { user = userStr ? JSON.parse(userStr) : null } catch { /* ignore */ }

  // 0) Verify token on first navigation (prevents auth bypass on browser restart)
  if (!tokenVerified && token && !to.meta.guest) {
    const valid = await verifyToken()
    if (!valid) {
      clearAuth()
      return next('/login')
    }
    tokenVerified = true
  }

  // 1) Logged-in users visiting login page → redirect to chat
  if (to.meta.guest && token) {
    return next('/chat')
  }

  // 2) Protected route without token → login
  if (to.meta.requiresAuth && !token) {
    return next('/login')
  }

  // 3) Admin route without admin/developer role → redirect to chat
  const adminRoles = ['admin', 'developer']
  if (to.meta.requiresAdmin && !adminRoles.includes(user?.role || '')) {
    return next('/chat')
  }

  next()
})

export default router
