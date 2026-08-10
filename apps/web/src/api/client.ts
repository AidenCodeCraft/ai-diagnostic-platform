import axios from 'axios'
import { getLogger } from '@/logger'

const client = axios.create({
  baseURL: '/api/v1',
  timeout: 30000,
})

/** 每个请求的开始时间 (config -> timestamp ms) */
const requestTimestamps = new WeakMap<object, number>()

// ── 请求拦截 ──────────────────────────────────────────────
client.interceptors.request.use((config) => {
  const token = sessionStorage.getItem('token')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  requestTimestamps.set(config, Date.now())
  return config
})

// ── 响应拦截 ──────────────────────────────────────────────
client.interceptors.response.use(
  (response) => {
    const startTime = requestTimestamps.get(response.config)
    const duration = startTime ? Date.now() - startTime : undefined
    const method = response.config.method?.toUpperCase() || 'GET'
    // 仅记录路径，不记录查询参数（避免泄露 token 等敏感信息）
    const path = response.config.url?.split('?')[0] || ''
    getLogger().debug(
      `${method} ${path} ${response.status}`,
      'api',
      { url: path, duration, extra: { status: response.status } },
    )
    return response
  },
  (error) => {
    const config = error.config
    const startTime = config ? requestTimestamps.get(config) : undefined
    const duration = startTime ? Date.now() - startTime : undefined
    const path = config?.url?.split('?')[0] || ''

    if (error.response?.status === 401) {
      getLogger().warn('Token expired — redirecting to login', 'api', {
        url: path, duration, extra: { status: 401 },
      })
      sessionStorage.removeItem('token')
      sessionStorage.removeItem('user')
      // 使用 location.replace 避免历史污染（不可回退到受保护页面）
      if (window.location.pathname !== '/login') {
        window.location.replace('/login')
      }
    } else if (error.response?.status === 403) {
      getLogger().warn('Forbidden access', 'api', {
        url: path, duration, extra: { status: 403 },
      })
    } else if (error.response?.status === 429) {
      getLogger().warn('Rate limited', 'api', {
        url: path, duration, extra: { status: 429 },
      })
    } else {
      const status = error.response?.status || 0
      const message = error.response?.data?.detail || error.message || 'Request failed'
      getLogger().error(`API ${status}: ${message}`, 'api', {
        url: path, duration, extra: { status, method: config?.method },
      })
    }
    return Promise.reject(error)
  },
)

export default client
