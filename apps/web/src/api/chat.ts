import client from './client'

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
  updateSession(id: number, title: string) {
    return client.put<ChatSession>(`/chat-sessions/${id}`, { title })
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
  saveMessage(sessionId: number, role: string, content: string, sources?: ChatSource[], thinking?: { text: string, elapsed: number }) {
    return client.post<ChatMessage>(`/chat-sessions/${sessionId}/messages`, { role, content, sources, thinking })
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
  ) {
    const token = sessionStorage.getItem('token')
    const resp = await fetch(`/api/v1/chat-sessions/${sessionId}/stream`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}) },
      body: JSON.stringify({ content, model, log_analysis: logAnalysis }),
    })
    if (!resp.ok) {
      onError(`HTTP ${resp.status}`)
      return
    }
    const reader = resp.body?.getReader()
    if (!reader) { onError('No response body'); return }
    const decoder = new TextDecoder()
    let pending = ''
    const handleEvent = (line: string) => {
      if (!line.startsWith('data: ')) return
      try {
        const data = JSON.parse(line.slice(6))
        if (data.token) onToken(data.token)
        if (data.reasoning) onReasoning?.(data.reasoning)
        if (data.sources) onSources?.(data.sources)
        if (data.done) onDone(data.model)
      } catch { /* ignore incomplete or invalid SSE payloads */ }
    }
    while (true) {
      const { done, value } = await reader.read()
      pending += decoder.decode(value, { stream: !done })
      const events = pending.split('\n\n')
      pending = done ? '' : events.pop() || ''
      for (const event of events) {
        for (const line of event.split('\n')) handleEvent(line)
      }
      if (done) break
    }
  },

  // Log analysis (kept for file upload support)
  uploadLog(formData: FormData) {
    return client.post('/logs/upload', formData, {
      timeout: 60000, // 大文件上传需要更长超时
    })
  },
  runAnalysis(logId: number, model?: string) {
    const params: any = { log_id: logId }
    if (model) params.model = model
    // 诊断流水线（解析+RAG+LLM）可能需要 60-120s，给足超时
    return client.post('/analyses/run', null, { params, timeout: 180000 })
  },
  getAnalysisResult(analysisId: number) {
    return client.get(`/analyses/${analysisId}/result`, { timeout: 30000 })
  },
  searchKnowledge(q: string) {
    return client.get('/knowledge/search', { params: { q } })
  },
  generateReport(logId: number) {
    return client.post(`/reports/${logId}`)
  },
}

export interface ChatSource {
  id?: number
  title: string
  source: string
  excerpt: string
}
