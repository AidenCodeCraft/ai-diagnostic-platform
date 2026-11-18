import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

import { describe, expect, it } from 'vitest'

/**
 * 深色主题静态守卫：
 * 关键组件（后台外壳、参考来源弹层、操作审计页）的颜色必须来自主题令牌，
 * 禁止在样式块中写裸色值，否则深色模式必然出现浅色残留。
 */

const RAW_HEX = /#[0-9a-fA-F]{3,8}\b/g

function read(relPath: string): string {
  return readFileSync(resolve(process.cwd(), relPath), 'utf8')
}

function styleText(source: string): string {
  const blocks = [...source.matchAll(/<style[^>]*>([\s\S]*?)<\/style>/g)]
  return blocks.map(m => m[1]).join('\n')
}

describe('深色主题静态守卫', () => {
  it('AdminLayout 样式不得出现裸色值', () => {
    const style = styleText(read('src/layouts/AdminLayout.vue'))
    expect(style.match(RAW_HEX) || []).toEqual([])
  })

  it('参考来源弹层 doc-panel 与 ref-tooltip 不得出现裸色值', () => {
    const style = styleText(read('src/components/chat/ChatMessageList.vue'))
    const panel = style.match(/\.doc-panel\s*\{[^}]*\}/)?.[0] || ''
    const tooltip = style.match(/\.ref-tooltip\s*\{[^}]*\}/)?.[0] || ''

    expect(panel).not.toBe('')
    expect(tooltip).not.toBe('')
    expect(panel.match(RAW_HEX) || []).toEqual([])
    expect(tooltip.match(RAW_HEX) || []).toEqual([])
  })

  it('操作审计页样式不得出现裸色值', () => {
    const style = styleText(read('src/views/admin/OperationLogs.vue'))
    expect(style.match(RAW_HEX) || []).toEqual([])
  })
})
