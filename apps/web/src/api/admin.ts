import client from './client'

export interface ModelOption {
  label: string
  value: string
  isDefault: boolean
}

/** 用户信息（匹配后端 UserResponse schema） */
export interface UserInfo {
  id: number
  username: string
  email?: string | null
  role: string
  is_active: boolean
  organization?: string | null
  created_at?: string | null
}

/** 用户列表响应（匹配后端 UserListResponse） */
export interface UserListResponse {
  items: UserInfo[]
  total: number
  page: number
  page_size: number
}

/** 创建用户参数 */
export interface CreateUserParams {
  username: string
  password: string
  role: string
  organization?: string
  is_active: boolean
}

/** 更新用户参数 */
export interface UpdateUserParams {
  role?: string
  is_active?: boolean
  organization?: string | null
  password?: string
}

/** 管理员统计信息 */
export interface AdminStats {
  total_users: number
  total_projects: number
  total_logs: number
  total_analyses: number
  total_knowledge: number
  total_sessions?: number
  total_messages?: number
  analysis_completed: number
  analysis_failed: number
  analysis_success_rate?: number
  analysis_trend: Array<{ date: string; count: number }>
  total_log_size_bytes: number
  total_log_size_mb?: number
  active_plugins?: number
  active_users_30d?: number
  knowledge_by_category?: Array<{ category: string; count: number }>
}

/** 管理员统计信息（从后端 /admin/stats 返回） */
export interface AdminStatsResponse extends AdminStats {}

export const adminApi = {
  // ── 模型配置 ──────────────────────────────────────────────
  /** 获取可用模型列表（用于对话界面选择器） */
  getAvailableModels() {
    return client.get<{ models: ModelOption[] }>('/admin/config/llm/models')
  },

  /** 获取完整的 LLM 配置 */
  getLLMConfig() {
    return client.get('/admin/config/llm')
  },

  /** 保存 LLM 配置 */
  saveLLMConfig(config: any) {
    return client.put('/admin/config/llm', config)
  },

  // ── 系统统计 ──────────────────────────────────────────────
  /** 获取系统统计信息 */
  getStats() {
    return client.get<AdminStatsResponse>('/admin/stats')
  },

  // ── 系统参数 ──────────────────────────────────────────────
  /** 获取系统参数配置 */
  getSystemConfig() {
    return client.get<{ maxUploadMb: number; timeoutSeconds: number; logRetentionDays: number }>('/admin/config/system')
  },

  /** 保存系统参数配置 */
  saveSystemConfig(config: { maxUploadMb: number; timeoutSeconds: number; logRetentionDays: number }) {
    return client.put('/admin/config/system', config)
  },

  // ── 用户管理 ──────────────────────────────────────────────
  /** 获取用户列表（支持分页、搜索、筛选） */
  listUsers(params?: {
    page?: number
    page_size?: number
    search?: string
    role?: string
    is_active?: boolean
  }) {
    return client.get<UserListResponse>('/users', { params })
  },

  /** 创建新用户 */
  createUser(data: CreateUserParams) {
    return client.post<UserInfo>('/users', data)
  },

  /** 更新用户信息 */
  updateUser(userId: number, data: UpdateUserParams) {
    return client.put<UserInfo>(`/users/${userId}`, data)
  },

  /** 删除用户 */
  deleteUser(userId: number) {
    return client.delete(`/users/${userId}`)
  },
}
