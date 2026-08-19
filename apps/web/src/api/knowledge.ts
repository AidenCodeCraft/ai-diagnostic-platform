import client from './client'

export interface KnowledgeImage {
  id: number
  doc_id?: number | null
  url: string
  caption?: string | null
  anchor?: string | null
  mime_type?: string
  width?: number | null
  height?: number | null
}

export interface KnowledgeDoc {
  id: number
  title: string
  content: string
  category: string | null
  doc_type: string
  status: string
  images?: KnowledgeImage[]
  created_at: string
}

export const knowledgeApi = {
  create(data: { title: string; content: string; category?: string; doc_type?: string }) {
    return client.post<KnowledgeDoc>('/knowledge', data)
  },
  list(params?: { page?: number; page_size?: number; category?: string; doc_type?: string; parent_id?: number }) {
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
  tree() {
    return client.get<{ tree: any[] }>('/knowledge/tree')
  },
  upload(formData: FormData) {
    return client.post('/knowledge/upload', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
  },
  /** 上传单张图片（编辑器插入用），返回 { id, url, ... } */
  uploadImage(formData: FormData) {
    return client.post<KnowledgeImage>('/knowledge/images', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
  },
  /** 逐图反馈：标记「不相关」以优化后续关联 */
  feedbackImage(imageId: number, feedback: 'irrelevant') {
    return client.post(`/knowledge/images/${imageId}/feedback`, { feedback })
  },
}
