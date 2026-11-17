import client from './client'

/** 主题偏好：浅色 / 深色 / 跟随系统 */
export type ThemePreference = 'light' | 'dark' | 'system'

/**
 * 用户主题偏好（每个用户独立配置，服务端持久化）。
 * 未登录或接口不可用时由 useTheme 回退到本地存储。
 */
export const preferencesApi = {
  getTheme() {
    return client.get<{ theme: ThemePreference | null }>('/auth/preferences')
  },
  saveTheme(theme: ThemePreference) {
    return client.put<{ theme: ThemePreference }>('/auth/preferences', { theme })
  },
}
