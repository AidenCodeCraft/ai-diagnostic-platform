import { beforeEach, describe, expect, it } from 'vitest'

import {
  clearSessionState,
  getActiveChatId,
  removeActiveChatId,
  setActiveChatId,
} from '@/utils/sessionState'

describe('sessionState 登录态与恢复状态', () => {
  beforeEach(() => {
    sessionStorage.clear()
  })

  it('activeChatId 按用户名隔离存储', () => {
    sessionStorage.setItem('user', JSON.stringify({ username: 'alice' }))
    setActiveChatId(7)

    expect(sessionStorage.getItem('activeChatId:alice')).toBe('7')
    expect(getActiveChatId()).toBe(7)
    removeActiveChatId()
    expect(getActiveChatId()).toBeNull()
  })

  it('无效值读取为 null', () => {
    sessionStorage.setItem('activeChatId', 'abc')
    expect(getActiveChatId(null)).toBeNull()
  })

  it('clearSessionState 清理 token/user 与所有 activeChatId，保留无关键', () => {
    sessionStorage.setItem('token', 't')
    sessionStorage.setItem('user', JSON.stringify({ username: 'bob' }))
    sessionStorage.setItem('activeChatId', '1')
    sessionStorage.setItem('activeChatId:bob', '2')
    sessionStorage.setItem('unrelated', 'keep')

    clearSessionState()

    expect(sessionStorage.getItem('token')).toBeNull()
    expect(sessionStorage.getItem('user')).toBeNull()
    expect(sessionStorage.getItem('activeChatId')).toBeNull()
    expect(sessionStorage.getItem('activeChatId:bob')).toBeNull()
    expect(sessionStorage.getItem('unrelated')).toBe('keep')
  })
})
