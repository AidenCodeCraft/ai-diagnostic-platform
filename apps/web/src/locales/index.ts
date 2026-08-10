import { createI18n } from 'vue-i18n'
import zhCN from './zh-CN'
import en from './en'

export type SupportedLocale = 'zh-CN' | 'en'
export const DEFAULT_LOCALE: SupportedLocale = 'zh-CN'

/** 从 localStorage 获取用户偏好语言 */
function getPersistedLocale(): SupportedLocale {
  try {
    const stored = localStorage.getItem('app-locale')
    if (stored === 'zh-CN' || stored === 'en') return stored
  } catch { /* ignore */ }
  return DEFAULT_LOCALE
}

const i18n = createI18n({
  legacy: false,
  locale: getPersistedLocale(),
  fallbackLocale: 'zh-CN',
  messages: { 'zh-CN': zhCN, en },
  // 允许组件中直接用 $t
  globalInjection: true,
})

/** 切换语言并持久化 */
export function setLocale(locale: SupportedLocale) {
  i18n.global.locale.value = locale
  try {
    localStorage.setItem('app-locale', locale)
  } catch { /* ignore */ }
}

export default i18n
