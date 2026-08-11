/// <reference types="vite/client" />

declare module '*.vue' {
  import type { DefineComponent } from 'vue'
  const component: DefineComponent<{}, {}, any>
  export default component
}

declare module '@kangc/v-md-editor' {
  import type { DefineComponent } from 'vue'
  const VMdEditor: DefineComponent<any, any, any> & {
    Preview: DefineComponent<{ text: string }, any, any>
  }
  export default VMdEditor
}

declare module 'element-plus/dist/locale/zh-cn.mjs' {
  import type { Language } from 'element-plus/es/locale'
  const zhCn: Language
  export default zhCn
}

declare module '@kangc/v-md-editor/lib/theme/vuepress.js' {
  const theme: any
  export default theme
}

declare module '@kangc/v-md-editor/lib/plugins/copy-code/index' {
  const plugin: any
  export default plugin
}
