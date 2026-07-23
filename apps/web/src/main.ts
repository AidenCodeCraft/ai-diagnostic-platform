import { createApp } from 'vue'
import { createPinia } from 'pinia'
import ElementPlus from 'element-plus'
import zhCn from 'element-plus/dist/locale/zh-cn.mjs'
import 'element-plus/dist/index.css'
import * as ElementPlusIconsVue from '@element-plus/icons-vue'

import App from './App.vue'
import router from './router'
import './styles/global.css'
import './styles/chat-theme.css'

// Logger — initialize early so all startup errors are captured
import { createLogger } from './logger'
import { LoggerPlugin } from './plugins/logger-plugin'
import { initTheme } from './composables/useTheme'

const logger = createLogger()
initTheme()

// Reporter — start async batch upload to backend
import { Reporter } from './logger/reporter'
const reporter = new Reporter(logger.config)
logger.setReporter(reporter)
reporter.start()

// VMdEditor plugins — register once globally to avoid "already in use" errors
import VMdEditor from '@kangc/v-md-editor'
import '@kangc/v-md-editor/lib/style/base-editor.css'
import vuepressTheme from '@kangc/v-md-editor/lib/theme/vuepress.js'
import '@kangc/v-md-editor/lib/theme/style/vuepress.css'
import createCopyCodePlugin from '@kangc/v-md-editor/lib/plugins/copy-code/index'
import '@kangc/v-md-editor/lib/plugins/copy-code/copy-code.css'
import Prism from 'prismjs'
import 'prismjs/components/prism-python'
import 'prismjs/components/prism-javascript'
import 'prismjs/components/prism-bash'
import 'prismjs/components/prism-json'
import 'prismjs/components/prism-yaml'
import 'prismjs/components/prism-markdown'
import 'prismjs/components/prism-css'
import 'prismjs/components/prism-sql'

VMdEditor.use(vuepressTheme, { Prism })
VMdEditor.use(createCopyCodePlugin())

const app = createApp(App)

app.use(createPinia())
app.use(router)
app.use(ElementPlus, { locale: zhCn })
app.use(LoggerPlugin)

for (const [key, component] of Object.entries(ElementPlusIconsVue)) {
  app.component(key, component)
}

app.mount('#app')

logger.info('App mounted successfully', 'business', { url: window.location.href })
