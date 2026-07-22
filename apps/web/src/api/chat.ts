import client from './client'

export interface ChatMessage {
  id: number
  session_id: number
  role: 'user' | 'assistant' | 'system'
  content: string
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
  /** SSE stream with optional diagnostic context */
  async sendMessageStream(
    sessionId: number,
    content: string,
    model?: string,
    onToken?: (token: string) => void,
    onDone?: (model: string) => void,
    onError?: (err: string) => void,
    logAnalysis?: Record<string, any>,
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
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      const text = decoder.decode(value, { stream: true })
      for (const line of text.split('\n')) {
        if (line.startsWith('data: ')) {
          try {
            const data = JSON.parse(line.slice(6))
            if (data.token) onToken(data.token)
            if (data.done) onDone(data.model)
          } catch { /* ignore parse errors */ }
        }
      }
    }
  },

  // Log analysis (kept for file upload support)
  uploadLog(formData: FormData) {
    return client.post('/logs/upload', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
  },
  runAnalysis(logId: number) {
    return client.post('/analyses/run', null, { params: { log_id: logId } })
  },
  getAnalysisResult(analysisId: number) {
    return client.get(`/analyses/${analysisId}/result`)
  },
  searchKnowledge(q: string) {
    return client.get('/knowledge/search', { params: { q } })
  },
  generateReport(logId: number) {
    return client.post(`/reports/${logId}`)
  },
}
