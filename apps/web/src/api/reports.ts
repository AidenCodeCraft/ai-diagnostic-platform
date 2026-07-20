import client from './client'

export interface ReportItem {
  id: number
  log_id: number | null
  title: string | null
  summary: string
  root_cause: string
  confidence: number | null
  next_steps: string[]
  model: string
  created_at: string
}

export const reportApi = {
  generate(logId: number) {
    return client.post(`/reports/${logId}`)
  },
  list(params?: { page?: number; page_size?: number }) {
    return client.get('/reports', { params })
  },
  get(id: number) {
    return client.get<ReportItem>(`/reports/${id}`)
  },
  exportMarkdown(id: number) {
    return client.get(`/reports/${id}/markdown`, { responseType: 'text' })
  },
  delete(id: number) {
    return client.delete(`/reports/${id}`)
  },
}
