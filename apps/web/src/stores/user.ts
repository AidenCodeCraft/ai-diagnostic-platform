import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import axios from 'axios'

interface UserInfo {
  id: number
  username: string
  email: string | null
  role: string
  is_active: boolean
}

export const useUserStore = defineStore('user', () => {
  const token = ref(localStorage.getItem('token') || '')
  const user = ref<UserInfo | null>(null)

  const isLoggedIn = computed(() => !!token.value)
  const isAdmin = computed(() => user.value?.role === 'admin')
  const userName = computed(() => user.value?.username || '用户')

  function setAuth(t: string, u: UserInfo) {
    token.value = t
    user.value = u
    localStorage.setItem('token', t)
    localStorage.setItem('user', JSON.stringify(u))
  }

  function restoreFromStorage() {
    const t = localStorage.getItem('token')
    const u = localStorage.getItem('user')
    if (t && u) {
      try {
        token.value = t
        user.value = JSON.parse(u)
      } catch {
        logout()
      }
    }
  }

  async function login(username: string, password: string) {
    const { data } = await axios.post('/api/v1/auth/login', { username, password })
    setAuth(data.access_token, data.user)
    return data
  }

  function logout() {
    token.value = ''
    user.value = null
    localStorage.removeItem('token')
    localStorage.removeItem('user')
  }

  return { token, user, isLoggedIn, isAdmin, userName, setAuth, restoreFromStorage, login, logout }
})
