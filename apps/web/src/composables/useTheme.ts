export type ThemePreference = 'light' | 'dark' | 'system'

function resolveTheme(preference: ThemePreference): 'light' | 'dark' {
  if (preference === 'system') {
    return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
  }
  return preference
}

export function applyTheme(preference: ThemePreference) {
  document.documentElement.dataset.theme = resolveTheme(preference)
}

export function getSavedTheme(): ThemePreference {
  const savedTheme = localStorage.getItem('theme')
  // 只有当用户明确设置过主题时才使用保存的值,否则默认为浅色
  if (savedTheme === 'dark' || savedTheme === 'light' || savedTheme === 'system') {
    return savedTheme
  }
  return 'light'
}

export function initTheme() {
  applyTheme(getSavedTheme())

  const media = window.matchMedia('(prefers-color-scheme: dark)')
  const onSystemChange = () => {
    if (getSavedTheme() === 'system') {
      applyTheme('system')
    }
  }
  media.addEventListener('change', onSystemChange)
}
