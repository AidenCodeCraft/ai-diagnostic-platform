/**
 * 登录态与「上次打开会话」恢复状态的统一读写。
 *
 * 背景：activeChatId 若在退出登录 / 401 / 换账号后残留，登录进入 /chat
 * 会用它去拉取一个不属于当前用户或已被删除的会话，后端返回
 * 404「会话不存在」，前端便弹出「加载对话失败」。
 *
 * 约束：
 * 1. 清理登录态时（登出 / 401 / token 失效）必须同时清理会话恢复状态
 * 2. activeChatId 按用户名隔离，避免 A 用户的会话 id 被 B 用户继承
 */

const ACTIVE_CHAT_PREFIX = 'activeChatId'

function currentUsername(): string | null {
  try {
    const raw = sessionStorage.getItem('user')
    if (!raw) return null
    const parsed = JSON.parse(raw)
    return parsed?.username || null
  } catch {
    return null
  }
}

/** 当前用户对应的 activeChatId 存储键 */
export function activeChatKey(username?: string | null): string {
  const name = username !== undefined ? username : currentUsername()
  return name ? `${ACTIVE_CHAT_PREFIX}:${name}` : ACTIVE_CHAT_PREFIX
}

/** 读取当前用户上次打开的会话 id；无效值返回 null */
export function getActiveChatId(username?: string | null): number | null {
  const raw = sessionStorage.getItem(activeChatKey(username))
  const id = raw ? Number.parseInt(raw, 10) : Number.NaN
  return Number.isNaN(id) || id <= 0 ? null : id
}

export function setActiveChatId(id: number, username?: string | null): void {
  sessionStorage.setItem(activeChatKey(username), String(id))
}

export function removeActiveChatId(username?: string | null): void {
  sessionStorage.removeItem(activeChatKey(username))
}

/**
 * 清理全部登录态与对话恢复状态。
 * 登出、token 失效（401）、路由鉴权失败等场景统一调用，避免状态残留。
 */
export function clearSessionState(): void {
  sessionStorage.removeItem('token')
  sessionStorage.removeItem('user')
  // 兼容历史遗留的无后缀 key
  sessionStorage.removeItem(ACTIVE_CHAT_PREFIX)
  for (let i = sessionStorage.length - 1; i >= 0; i--) {
    const key = sessionStorage.key(i)
    if (key?.startsWith(`${ACTIVE_CHAT_PREFIX}:`)) sessionStorage.removeItem(key)
  }
}
