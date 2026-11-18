import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import axios from 'axios'
import { getLogger } from '@/logger'
import { syncUserTheme, applyTheme } from '@/composables/useTheme'

// 使用 sessionStorage → 浏览器关闭后自动清除
const store = sessionStorage

/** 与 api/admin.ts 保持一致的 UserInfo 类型 */
export interface UserInfo {
  id: number
  username: string
  email?: string | null
  role: string
  is_active: boolean
  organization?: string | null
  created_at?: string | null
}

function loadUserFromStorage(): UserInfo | null {
  const u = store.getItem('user')
  if (!u) return null
  try { return JSON.parse(u) } catch { return null }
}

export const useUserStore = defineStore('user', () => {
  const token = ref(store.getItem('token') || '')
  const user = ref<UserInfo | null>(loadUserFromStorage())
  // 已有登录态（刷新/恢复会话）时优先按该用户的主题配置渲染
  if (user.value?.username) syncUserTheme(user.value.username).catch(() => {})

  const isLoggedIn = computed(() => !!token.value)
  const isAdmin = computed(() => {
    const r = user.value?.role
    return r === 'admin' || r === 'developer'
  })
  const userName = computed(() => user.value?.username || '用户')

  function setAuth(t: string, u: UserInfo) {
    token.value = t
    user.value = u
    store.setItem('token', t)
    store.setItem('user', JSON.stringify(u))
    // 优先按当前登录用户自身的主题配置渲染（服务端配置 > 本地缓存）
    syncUserTheme(u.username).catch(() => {})
  }

  async function login(username: string, password: string) {
    try {
      const { data } = await axios.post('/api/v1/auth/login', { username, password })
      setAuth(data.access_token, data.user)
      return data
    } catch (e: any) {
      const detail = e?.response?.data?.detail || e?.message || '登录失败'
      throw new Error(detail)
    }
  }

  async function logout() {
    try {
      // 尝试通知后端使 token 失效
      await axios.post('/api/v1/auth/logout', {}, {
        headers: token.value ? { Authorization: `Bearer ${token.value}` } : {},
      }).catch(() => { /* 后端可能没有 /logout 端点，静默忽略 */ })
    } catch { /* ignore */ }
    getLogger().info('User logged out', 'user', { action: 'logout', extra: { username: user.value?.username } })
    token.value = ''
    user.value = null
    store.removeItem('token')
    store.removeItem('user')
    // 退出登录后登录页强制浅色（下次登录再按用户偏好恢复）
    applyTheme('light')
  }

  return { token, user, isLoggedIn, isAdmin, userName, setAuth, login, logout }
})
