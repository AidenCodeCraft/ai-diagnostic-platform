import client from './client'

export interface ChatMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  timestamp: string
  status?: 'sending' | 'sent' | 'error'
}

export interface ChatSession {
  id: string
  title: string
  model: string
  created_at: string
  updated_at: string
}

export const chatApi = {
  /** 上传日志文件并返回 log_id */
  uploadLog(formData: FormData) {
    return client.post('/logs/upload', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
  },
  /** 运行分析 */
  runAnalysis(logId: number) {
    return client.post('/analyses/run', null, { params: { log_id: logId } })
  },
  /** 获取分析结果 */
  getAnalysisResult(analysisId: number) {
    return client.get(`/analyses/${analysisId}/result`)
  },
  /** 搜索知识库 */
  searchKnowledge(q: string) {
    return client.get('/knowledge/search', { params: { q } })
  },
  /** 生成报告 */
  generateReport(logId: number) {
    return client.post(`/reports/${logId}`)
  },
}
