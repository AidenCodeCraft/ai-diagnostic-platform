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

export interface KnowledgeIssue {
  code: string
  level: 'error' | 'warn'
  message: string
  section_key?: string
}

export interface FormatSection {
  section_key: string
  title: string
  level: number
  start_line: number
  end_line: number
  content: string
}

export interface KnowledgeTemplateSection {
  key: string
  title: string
  level: 'required' | 'recommended' | 'optional'
  aliases?: string[]
}

export interface KnowledgeTemplateInfo {
  doc_type: string
  name: string
  free_form: boolean
  skeleton: string
  guide: string
  example: string
  sections: KnowledgeTemplateSection[]
}

export interface FormatPreview {
  title: string
  doc_type: string | null
  normalized_content: string
  sections: FormatSection[]
  profile_draft: Record<string, any>
  features: Record<string, string>
  suggested_keywords: string[]
  notes: string[]
  issues: KnowledgeIssue[]
  quality_score: number
  status_hint: 'active' | 'draft'
  template: any
}

export interface KnowledgeDoc {
  id: number
  title: string
  content: string
  category: string | null
  doc_type: string
  status: string
  images?: KnowledgeImage[]
  quality_score?: number | null
  issues?: KnowledgeIssue[]
  suggested_keywords?: string[]
  created_at: string
}

export interface KnowledgeProfile {
  id?: number
  doc_id?: number
  symptom?: string | null
  environment?: string | null
  log_keywords?: string[]
  log_patterns?: string[]
  negative_patterns?: string[]
  expected?: string | null
  root_cause?: string | null
  solution?: string | null
  confidence?: number
  status?: string
  source?: string
}

export const knowledgeApi = {
  create(data: { title: string; content: string; category?: string; doc_type?: string; parent_id?: number; profile?: KnowledgeProfile }) {
    return client.post<KnowledgeDoc>('/knowledge', data)
  },
  list(params?: { page?: number; page_size?: number; category?: string; doc_type?: string; parent_id?: number; sort?: 'updated_asc' | 'updated_desc' }) {
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
  /** 诊断剧本（结构化诊断信息） */
  getProfile(docId: number) {
    return client.get<KnowledgeProfile | null>(`/knowledge/${docId}/profile`)
  },
  saveProfile(docId: number, data: KnowledgeProfile) {
    return client.put<KnowledgeProfile>(`/knowledge/${docId}/profile`, data)
  },
  /** 不落库：规范化 + 校验，返回「提交后格式」预览 */
  formatPreview(data: { content: string; doc_type?: string; title?: string }) {
    return client.post<FormatPreview>('/knowledge/format/preview', data)
  },
  /** 知识模板契约（含骨架 / 格式说明 / 示例） */
  templates() {
    return client.get<{ templates: KnowledgeTemplateInfo[] }>('/knowledge/templates')
  },
  /** AI 润色：按模板规范化内容（LLM 不可用时后端自动回退规则整理） */
  polish(data: { content: string; doc_type?: string; title?: string }) {
    return client.post<FormatPreview & { polished_content: string; source: 'llm' | 'rule' }>(
      '/knowledge/polish', data, { timeout: 120000 },
    )
  },
}
