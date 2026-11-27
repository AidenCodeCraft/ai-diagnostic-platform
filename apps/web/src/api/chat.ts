import client from './client'

export interface ChatMessageVersion {
  content: string
  sources?: ChatSource[]
  thinking?: {
    text: string
    elapsed: number
  }
}

export interface ChatMessage {
  id: number
  session_id: number
  role: 'user' | 'assistant' | 'system'
  content: string
  sources?: ChatSource[]
  thinking?: {
    text: string
    elapsed: number
  }
  /** 编辑重发的版本历史（缺省=单版本） */
  versions?: ChatMessageVersion[]
  /** versions 中当前展示的下标 */
  active_version?: number
  /** 提问附带的截图 id（chat_images.id），用于历史消息回显 */
  image_ids?: number[]
  created_at: string
}

export interface ChatSession {
  id: number
  title: string | null
  user_id: number | null
  log_id: number | null
  model: string | null
  created_at: string
  updated_at: string
}

export interface ChatReply {
  reply: string
  model: string
}

export const chatApi = {
  // Sessions
  createSession(title?: string, model?: string) {
    return client.post<ChatSession>('/chat-sessions', { title, model })
  },
  listSessions() {
    return client.get<{ items: ChatSession[]; total: number }>('/chat-sessions')
  },
  getSession(id: number) {
    return client.get<ChatSession>(`/chat-sessions/${id}`)
  },
  updateSession(id: number, data: { title?: string; is_pinned?: boolean }) {
    return client.put<ChatSession>(`/chat-sessions/${id}`, data)
  },
  deleteSession(id: number) {
    return client.delete(`/chat-sessions/${id}`)
  },

  // Messages
  getMessages(sessionId: number) {
    return client.get<ChatMessage[]>(`/chat-sessions/${sessionId}/messages`)
  },

  // Chat
  sendMessage(sessionId: number, content: string, model?: string) {
    return client.post<ChatReply>(`/chat-sessions/${sessionId}/chat`, { content, model })
  },
  /** Store a message directly (without LLM call) — for persisting analysis results */
  saveMessage(sessionId: number, role: string, content: string, sources?: ChatSource[], thinking?: { text: string, elapsed: number }, versions?: ChatMessageVersion[], activeVersion?: number, imageIds?: number[]) {
    return client.post<ChatMessage>(`/chat-sessions/${sessionId}/messages`, { role, content, sources, thinking, versions, active_version: activeVersion, image_ids: imageIds })
  },
  /** 更新消息（编辑重发：content / versions / active_version 等） */
  updateMessage(sessionId: number, messageId: number, payload: {
    content?: string
    sources?: ChatSource[]
    thinking?: { text: string, elapsed: number }
    versions?: ChatMessageVersion[]
    active_version?: number
  }) {
    return client.put<ChatMessage>(`/chat-sessions/${sessionId}/messages/${messageId}`, payload)
  },
  /** 更新消息反馈（like / dislike / null） */
  updateFeedback(sessionId: number, messageId: number, feedback: string | null) {
    return client.put(`/chat-sessions/${sessionId}/messages/${messageId}/feedback`, { feedback })
  },
  /** 标记消息已解决并触发自进化蒸馏（生成待审核的知识库候选） */
  resolveMessage(sessionId: number, messageId: number | string, resolved = true) {
    return client.post(`/chat-sessions/${sessionId}/messages/${messageId}/resolve`, { resolved })
  },
  /** SSE stream with optional diagnostic context */
  async sendMessageStream(
    sessionId: number,
    content: string,
    model?: string,
    onToken?: (token: string) => void,
    onDone?: (model: string) => void,
    onError?: (err: string) => void,
    logAnalysis?: Record<string, any>,
    onReasoning?: (reasoning: string) => void,
    onSources?: (sources: ChatSource[]) => void,
    onClarification?: (questions: any[]) => void,
    onStopped?: () => void,
    signal?: AbortSignal,
    onTruncated?: () => void,
    imageIds?: number[],
  ) {
    const token = sessionStorage.getItem('token')
    let resp: Response
    try {
      resp = await fetch(`/api/v1/chat-sessions/${sessionId}/stream`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}) },
        body: JSON.stringify({ content, model, log_analysis: logAnalysis, image_ids: imageIds }),
        signal,
      })
    } catch (e: any) {
      // 用户主动停止（AbortController）不是错误
      if (signal?.aborted || e?.name === 'AbortError') { onStopped?.(); return }
      onError?.(`网络错误: ${e.message || '无法连接到服务器'}`)
      return
    }
    if (!resp.ok) {
      onError?.(`HTTP ${resp.status}`)
      return
    }
    const reader = resp.body?.getReader()
    if (!reader) { onError?.('No response body'); return }
    const decoder = new TextDecoder()
    let pending = ''
    const handleEvent = (line: string) => {
      if (!line.startsWith('data: ')) return
      try {
        const data = JSON.parse(line.slice(6))
        if (data.error) {
          onError?.(data.error)
          return
        }
        if (data.token) onToken?.(data.token)
        if (data.reasoning) onReasoning?.(data.reasoning)
        if (data.sources) onSources?.(data.sources)
        if (data.clarification) onClarification?.(data.clarification)
        if (data.truncated) onTruncated?.()
        if (data.done) onDone?.(data.model)
      } catch { /* ignore incomplete or invalid SSE payloads */ }
    }
    try {
      while (true) {
        const { done, value } = await reader.read()
        if (value) pending += decoder.decode(value, { stream: !done })
        const events = pending.split('\n\n')
        pending = done ? '' : events.pop() || ''
        for (const event of events) {
          for (const line of event.split('\n')) handleEvent(line)
        }
        if (done) break
      }
    } catch (e: any) {
      if (signal?.aborted || e?.name === 'AbortError') { onStopped?.(); return }
      onError?.(`流读取错误: ${e.message || '连接中断'}`)
    } finally {
      try { reader.cancel() } catch { /* ignore */ }
    }
  },

  // Log analysis (kept for file upload support)
  uploadLog(formData: FormData) {
    return client.post('/logs/upload', formData, {
      timeout: 60000, // 大文件上传需要更长超时
    })
  },
  runAnalysis(logId: number, model?: string, userQuery?: string) {
    const params: any = { log_id: logId }
    if (model) params.model = model
    if (userQuery) params.user_query = userQuery
    // 诊断流水线（解析+RAG+LLM）可能需要 60-120s，给足超时
    return client.post('/analyses/run', null, { params, timeout: 180000 })
  },
  runAnalysisAsync(logId: number, model?: string, userQuery?: string) {
    const params: any = { log_id: logId }
    if (model) params.model = model
    if (userQuery) params.user_query = userQuery
    return client.post('/analyses/async', null, { params, timeout: 30000 })
  },
  getAnalysis(analysisId: number) {
    return client.get(`/analyses/${analysisId}`, { timeout: 15000 })
  },
  getAnalysisResult(analysisId: number) {
    return client.get(`/analyses/${analysisId}/result`, { timeout: 30000 })
  },
  /** 上传对话截图并同步识别（OCR 主路径 + 视觉兜底） */
  uploadChatImage(file: File, sessionId?: number) {
    const form = new FormData()
    form.append('file', file)
    if (sessionId) form.append('session_id', String(sessionId))
    return client.post<ChatImageUpload>('/chat/images', form, { timeout: 120000 })
  },
  /** 取截图原图（鉴权接口），返回可直接用于 <img> 的 objectURL */
  async getChatImageFile(imageId: number): Promise<string> {
    const { data } = await client.get(`/chat/images/${imageId}/file`, { responseType: 'blob' })
    return URL.createObjectURL(data as Blob)
  },

  searchKnowledge(q: string) {
    return client.get('/knowledge/search', { params: { q } })
  },
  generateReport(logId: number) {
    return client.post(`/reports/${logId}`)
  },
}

export interface ChatImageUpload {
  id: number
  filename?: string
  status: 'pending' | 'recognizing' | 'succeeded' | 'failed'
  recognize_path?: string | null
  text: string
  text_preview: string
  error_message?: string | null
}

export interface ChatImage {
  id: number
  url: string
  caption?: string | null
  anchor?: string | null
  width?: number | null
  height?: number | null
}

export interface ChatSource {
  id?: number
  /** 检索结果编号（与 LLM 引用中的文档编号一致，用于 ref://N 解析） */
  num?: number
  title: string
  source: string
  excerpt: string
  section?: string
  section_key?: string
  start_line?: number
  end_line?: number
  images?: ChatImage[]
}
