import client from './client'

export interface ModelOption {
  label: string
  value: string
  isDefault: boolean
}

export const adminApi = {
  // 获取可用模型列表（用于对话界面选择器）
  getAvailableModels() {
    return client.get<{ models: ModelOption[] }>('/admin/config/llm/models')
  },
  
  // 获取完整的 LLM 配置
  getLLMConfig() {
    return client.get('/admin/config/llm')
  },
  
  // 保存 LLM 配置
  saveLLMConfig(config: any) {
    return client.put('/admin/config/llm', config)
  },
  
  // 获取系统统计信息
  getStats() {
    return client.get('/admin/stats')
  }
}
