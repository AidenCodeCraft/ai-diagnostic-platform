import client from './client'

export interface LogItem {
  id: number
  filename: string
  size: number | null
  status: string
  project_id: number | null
  device: string | null
  version: string | null
  description: string | null
  created_at: string
}

export interface LogEventItem {
  id: number
  log_id: number
  line_no: number
  level: string
  module: string
  source_type: string
  is_error: boolean
  classification: string
  message: string | null
  raw: string | null
}

export const logApi = {
  list(params?: { project_id?: number }) {
    return client.get<LogItem[]>('/logs', { params })
  },
  parse(logId: number) {
    return client.post(`/logs/${logId}/parse`)
  },
  queryEvents(logId: number, params?: {
    page?: number
    page_size?: number
    is_error?: boolean
    level?: string
    module?: string
    keyword?: string
  }) {
    return client.get<{ items: LogEventItem[]; total: number; page: number; page_size: number }>(
      `/logs/${logId}/events/query`, { params },
    )
  },
}

export const analysisApi = {
  runBatch(logIds: number[], model?: string, userQuery?: string) {
    return client.post<{ items: any[]; total: number }>('/analyses/batch', {
      log_ids: logIds,
      model,
      user_query: userQuery,
    })
  },
  get(id: number) {
    return client.get(`/analyses/${id}`)
  },
  getResult(id: number) {
    return client.get(`/analyses/${id}/result`)
  },
  retry(id: number) {
    return client.post(`/analyses/${id}/retry`)
  },
}
