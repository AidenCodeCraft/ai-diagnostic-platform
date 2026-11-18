import { preferencesApi, type ThemePreference } from '@/api/preferences'

export type { ThemePreference }

/**
 * 主题偏好解析与应用。
 *
 * 优先级：当前登录用户自身的配置（theme:<用户名>）→ 全局旧键（theme）→ 浅色。
 * 登录后由 syncUserTheme 拉取服务端配置（每个用户独立，跨设备生效），服务端值优先。
 */

function resolveTheme(preference: ThemePreference): 'light' | 'dark' {
  if (preference === 'system') {
    return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
  }
  return preference
}

function isValidTheme(value: string | null): value is ThemePreference {
  return value === 'dark' || value === 'light' || value === 'system'
}

/** 当前登录用户名（sessionStorage 中的登录态） */
function currentUsername(): string | null {
  try {
    const u = JSON.parse(sessionStorage.getItem('user') || 'null')
    return u?.username || null
  } catch {
    return null
  }
}

export function applyTheme(preference: ThemePreference) {
  const resolved = resolveTheme(preference)
  document.documentElement.dataset.theme = resolved
  // Element Plus 内置暗色变量跟随同一开关（组件级暗色主题）
  document.documentElement.classList.toggle('dark', resolved === 'dark')
}

export function getSavedTheme(username?: string | null): ThemePreference {
  const user = username !== undefined ? username : currentUsername()
  if (user) {
    const saved = localStorage.getItem(`theme:${user}`)
    if (isValidTheme(saved)) return saved
  }
  const savedTheme = localStorage.getItem('theme')
  // 只有当用户明确设置过主题时才使用保存的值,否则默认为浅色
  if (isValidTheme(savedTheme)) return savedTheme
  return 'light'
}

/** 保存主题偏好（按用户独立缓存 + 全局旧键回退） */
export function saveTheme(preference: ThemePreference, username?: string | null) {
  const user = username !== undefined ? username : currentUsername()
  if (user) localStorage.setItem(`theme:${user}`, preference)
  localStorage.setItem('theme', preference)
}

/**
 * 应用并保存主题偏好：立即生效（所有界面实时同步），并异步同步到服务端
 * （每个用户独立配置；服务端失败不影响本地生效）。
 */
export function setTheme(preference: ThemePreference) {
  applyTheme(preference)
  saveTheme(preference)
  preferencesApi.saveTheme(preference).catch(() => { /* 未登录或服务端不可用时仅本地生效 */ })
}

/**
 * 登录后（或应用启动时已有登录态）拉取当前用户的服务端主题配置并应用。
 * 服务端值优先于本地缓存；拉取失败时回退本地缓存。
 */
export async function syncUserTheme(username?: string | null): Promise<ThemePreference> {
  const user = username !== undefined ? username : currentUsername()
  try {
    const { data } = await preferencesApi.getTheme()
    if (data && isValidTheme(data.theme)) {
      saveTheme(data.theme, user)
      applyTheme(data.theme)
      return data.theme
    }
  } catch { /* 未登录或服务端不可用：使用本地缓存 */ }
  const local = getSavedTheme(user)
  applyTheme(local)
  return local
}

/** 登录页强制浅色：不跟随用户偏好或系统暗色 */
function isLoginPage(): boolean {
  return window.location.pathname === '/login'
}

export function initTheme() {
  applyTheme(isLoginPage() ? 'light' : getSavedTheme())

  const media = window.matchMedia('(prefers-color-scheme: dark)')
  const onSystemChange = () => {
    if (!isLoginPage() && getSavedTheme() === 'system') {
      applyTheme('system')
    }
  }
  media.addEventListener('change', onSystemChange)
}
