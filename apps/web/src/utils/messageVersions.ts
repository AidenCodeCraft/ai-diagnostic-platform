/**
 * 消息编辑重发的版本历史工具。
 *
 * 约定：
 *  - msg.versions：版本数组 [{ content, sources?, thinking? }, ...]（下标即版本号）；
 *  - msg.activeVersion：当前展示的版本下标；
 *  - content / sources / thinking 始终与 versions[activeVersion] 保持一致（写透式）。
 *  - 提问消息与其回答消息的版本下标一一对应（回答随提问版本一起切换）。
 */

export interface MessageLike {
  content: string
  sources?: any
  thinking?: any
  versions?: any[]
  activeVersion?: number
}

/** 追加一个新版本（内容为 newContent），把消息写透到该版本，返回其下标 */
export function appendVersion(msg: MessageLike, newContent: string): number {
  const list: any[] = msg.versions && msg.versions.length ? [...msg.versions] : [{ content: msg.content || '' }]
  list.push({ content: newContent })
  msg.versions = list
  msg.activeVersion = list.length - 1
  msg.content = newContent
  return list.length - 1
}

/** 把消息当前内容（含 sources/thinking）快照进 versions[idx]（默认追加），返回其下标 */
export function snapshotVersion(msg: MessageLike, idx?: number): number {
  const item: any = { content: msg.content || '' }
  if (msg.sources !== undefined) item.sources = msg.sources
  if (msg.thinking !== undefined) item.thinking = { ...(msg.thinking as any) }
  const list: any[] = msg.versions && msg.versions.length ? [...msg.versions] : []
  const at = idx ?? list.length
  list[at] = item
  msg.versions = list
  return at
}

/** 切换到第 idx 个版本并把内容写回消息；版本不存在时返回 false 且不改动 */
export function applyVersion(msg: MessageLike, idx: number): boolean {
  const item = msg.versions?.[idx]
  if (!item) return false
  msg.activeVersion = idx
  msg.content = item.content
  if (item.sources !== undefined) msg.sources = item.sources
  if (item.thinking !== undefined && item.thinking) msg.thinking = { ...(item.thinking as any) }
  return true
}
