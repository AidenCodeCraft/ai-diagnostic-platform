import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { chatApi } from '@/api/chat'

/** 用最小 reader 模拟 SSE 响应体，避免依赖真实 Response/ReadableStream。 */
function mockSseResponse(chunks: string[]) {
  const encoder = new TextEncoder()
  let index = 0
  const reader = {
    read: async () => {
      if (index >= chunks.length) return { done: true, value: undefined }
      return { done: false, value: encoder.encode(chunks[index++]) }
    },
    cancel: async () => undefined,
  }
  return { ok: true, status: 200, body: { getReader: () => reader } }
}

describe('chat SSE stream', () => {
  beforeEach(() => {
    sessionStorage.clear()
    sessionStorage.setItem('token', 'test-token')
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  it('parses tokens / sources / clarification / done callbacks', async () => {
    const payloads = [
      { token: '你' },
      { token: '好' },
      { sources: [{ id: 1, title: 'KB', source: '知识库', excerpt: 'x' }] },
      { clarification: [{ slot: 'device', label: '设备型号', options: ['D3C'] }] },
      { done: true, model: 'mock' },
    ].map((payload) => `data: ${JSON.stringify(payload)}\n\n`)

    const fetchMock = vi.fn().mockResolvedValue(mockSseResponse(payloads))
    vi.stubGlobal('fetch', fetchMock)

    const tokens: string[] = []
    let sources: any[] = []
    let clarification: any[] = []
    let doneModel = ''
    let error: string | undefined

    await chatApi.sendMessageStream(
      1,
      'hello',
      'mock',
      (token) => tokens.push(token),
      (model) => { doneModel = model },
      (err) => { error = err },
      undefined,
      undefined,
      (value) => { sources = value },
      (questions) => { clarification = questions },
    )

    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect(tokens.join('')).toBe('你好')
    expect(sources[0].title).toBe('KB')
    expect(clarification[0].slot).toBe('device')
    expect(doneModel).toBe('mock')
    expect(error).toBeUndefined()
  })

  it('reports HTTP errors through onError', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, status: 500 }))

    let error = ''
    await chatApi.sendMessageStream(
      1, 'hi', undefined, undefined, undefined,
      (err) => { error = err },
    )

    expect(error).toContain('500')
  })

  it('reports network errors through onError', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('offline')))

    let error = ''
    await chatApi.sendMessageStream(
      1, 'hi', undefined, undefined, undefined,
      (err) => { error = err },
    )

    expect(error).toContain('offline')
  })
})
