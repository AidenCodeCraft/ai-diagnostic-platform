import client from './client'

export interface KnowledgeDoc {
  id: number
  title: string
  content: string
  category: string | null
  doc_type: string
  status: string
  created_at: string
}

export const knowledgeApi = {
  create(data: { title: string; content: string; category?: string; doc_type?: string }) {
    return client.post<KnowledgeDoc>('/knowledge', data)
  },
  list(params?: { page?: number; page_size?: number; category?: string; doc_type?: string }) {
    return client.get('/knowledge', { params })
  },
  get(id: number) {
    return client.get<KnowledgeDoc>(`/knowledge/${id}`)
  },
  update(id: number, data: Record<string, any>) {
    return client.put<KnowledgeDoc>(`/knowledge/${id}`, data)
  },
  delete(id: number) {
    return client.delete(`/knowledge/${id}`)
  },
  search(q: string, params?: { page?: number; page_size?: number }) {
    return client.get('/knowledge/search', { params: { q, ...params } })
  },
  categories() {
    return client.get<string[]>('/knowledge/categories')
  },
}
