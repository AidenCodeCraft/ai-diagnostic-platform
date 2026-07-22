import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import axios from 'axios'

interface UserInfo {
  id: number
  username: string
  email: string | null
  role: string
  is_active: boolean
  organization?: string | null
}

// Use sessionStorage → auth cleared when browser closes
const store = sessionStorage

function loadUserFromStorage(): UserInfo | null {
  const u = store.getItem('user')
  if (!u) return null
  try { return JSON.parse(u) } catch { return null }
}

export const useUserStore = defineStore('user', () => {
  const token = ref(store.getItem('token') || '')
  const user = ref<UserInfo | null>(loadUserFromStorage())

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
  }

  async function login(username: string, password: string) {
    const { data } = await axios.post('/api/v1/auth/login', { username, password })
    setAuth(data.access_token, data.user)
    return data
  }

  function logout() {
    token.value = ''
    user.value = null
    store.removeItem('token')
    store.removeItem('user')
  }

  return { token, user, isLoggedIn, isAdmin, userName, setAuth, login, logout }
})
