import axios from 'axios'
import { getLogger } from '@/logger'

const client = axios.create({
  baseURL: '/api/v1',
  timeout: 30000,
  // 不设置默认 Content-Type：axios 会自动根据 body 类型选择
  //   — JSON 对象 → application/json
  //   — FormData  → multipart/form-data（含 boundary）
})

// 请求拦截：自动注入 JWT Token + 记录请求开始时间
client.interceptors.request.use((config) => {
  const token = sessionStorage.getItem('token')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  // 记录请求开始时间（用于耗时计算）
  ;(config as Record<string, unknown>)._startTime = Date.now()
  return config
})

// 响应拦截：日志记录 + 401 自动跳转登录页
client.interceptors.response.use(
  (response) => {
    // 请求成功：记录 API 日志（DEBUG 级别，不上报）
    const startTime = (response.config as Record<string, unknown>)._startTime as number | undefined
    const duration = startTime ? Date.now() - startTime : undefined
    const method = response.config.method?.toUpperCase() || 'GET'
    getLogger().debug(
      `${method} ${response.config.url} ${response.status}`,
      'api',
      { url: response.config.url, duration, extra: { status: response.status } },
    )
    return response
  },
  (error) => {
    const duration = error.config
      ? (error.config as Record<string, unknown>)._startTime as number
        ? Date.now() - ((error.config as Record<string, unknown>)._startTime as number)
        : undefined
      : undefined

    if (error.response?.status === 401) {
      getLogger().warn('Token expired or invalid — redirecting to login', 'api', {
        url: error.config?.url,
        duration,
        extra: { status: 401 },
      })
      sessionStorage.removeItem('token')
      sessionStorage.removeItem('user')
      if (window.location.pathname !== '/login') {
        window.location.href = '/login'
      }
    } else {
      const status = error.response?.status || 0
      const message = error.response?.data?.detail || error.message || 'Request failed'
      getLogger().error(`API ${status}: ${message}`, 'api', {
        url: error.config?.url,
        duration,
        extra: { status, method: error.config?.method },
      })
    }
    return Promise.reject(error)
  },
)

export default client
