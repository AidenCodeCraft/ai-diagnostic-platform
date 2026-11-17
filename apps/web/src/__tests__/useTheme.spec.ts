import { beforeEach, describe, expect, it } from 'vitest'

import { applyTheme, getSavedTheme, saveTheme } from '@/composables/useTheme'

// jsdom 未实现 matchMedia，按需桩化（matches 可控）
let prefersDark = false
function stubMatchMedia() {
  window.matchMedia = ((query: string) => ({
    matches: prefersDark && query.includes('prefers-color-scheme: dark'),
    media: query,
    addEventListener: () => {},
    removeEventListener: () => {},
  })) as any
}

describe('useTheme 每个用户独立的主题配置', () => {
  beforeEach(() => {
    localStorage.clear()
    sessionStorage.clear()
    prefersDark = false
    stubMatchMedia()
    document.documentElement.removeAttribute('data-theme')
    document.documentElement.classList.remove('dark')
  })

  it('applyTheme 设置 data-theme 并同步 Element Plus dark 类', () => {
    applyTheme('dark')
    expect(document.documentElement.dataset.theme).toBe('dark')
    expect(document.documentElement.classList.contains('dark')).toBe(true)

    applyTheme('light')
    expect(document.documentElement.dataset.theme).toBe('light')
    expect(document.documentElement.classList.contains('dark')).toBe(false)
  })

  it('按用户名独立保存/读取主题，优先于全局旧键', () => {
    saveTheme('dark', 'alice')
    saveTheme('light', 'bob')
    expect(getSavedTheme('alice')).toBe('dark')
    expect(getSavedTheme('bob')).toBe('light')
    // 全局旧键被最后写入覆盖，但用户键优先
    expect(getSavedTheme('carol')).toBe('light')
  })

  it('读取当前登录用户（sessionStorage）的配置', () => {
    saveTheme('dark', 'alice')
    sessionStorage.setItem('user', JSON.stringify({ username: 'alice' }))
    expect(getSavedTheme()).toBe('dark')

    sessionStorage.setItem('user', JSON.stringify({ username: 'bob' }))
    saveTheme('system', 'bob')
    expect(getSavedTheme()).toBe('system')
  })

  it('无任何配置时默认浅色', () => {
    expect(getSavedTheme(null)).toBe('light')
  })

  it('跟随系统解析为实际主题', () => {
    applyTheme('system')
    expect(document.documentElement.dataset.theme).toBe('light')
    prefersDark = true
    applyTheme('system')
    expect(document.documentElement.dataset.theme).toBe('dark')
  })
})
