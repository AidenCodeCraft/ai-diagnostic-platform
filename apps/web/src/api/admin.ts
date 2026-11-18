import client from './client'
import type { UserInfo } from '@/stores/user'

export type { UserInfo }

export interface ModelOption {
  label: string
  value: string
  isDefault: boolean
}

/** 系统参数（管理后台 → 系统配置 → 系统参数） */
export interface SystemConfig {
  max_upload_mb: number
  timeout_seconds: number
  log_retention_days: number
  /** 允许多对话并行提问 */
  parallel_chat_enabled: boolean
  /** 单用户最大并行提问对话数 */
  max_parallel_chats: number
  /** 最大同时在线人数（全系统并发提问上限，0 = 不限制） */
  max_online_users: number
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
  active_users_30d?: number
  knowledge_by_category?: Array<{ category: string; count: number }>
}

/** 管理员统计信息（从后端 /admin/stats 返回） */
export interface AdminStatsResponse extends AdminStats {}

/** 管理后台操作审计记录 */
export interface AdminAuditLog {
  id: number
  operator_id?: number | null
  operator_name?: string | null
  action: string
  target_type?: string | null
  target_id?: string | null
  detail?: string | null
  result: string
  ip?: string | null
  created_at?: string | null
}

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

  // ── 操作审计 ──────────────────────────────────────────────
  /** 查询管理后台操作记录 */
  listAuditLogs(params?: {
    page?: number
    page_size?: number
    action?: string
    operator?: string
    result?: string
  }) {
    return client.get<{
      items: AdminAuditLog[]
      total: number
      page: number
      page_size: number
    }>('/admin/audit-logs', { params })
  },

  // ── 系统参数 ──────────────────────────────────────────────
  /** 获取系统参数配置 */
  getSystemConfig() {
    return client.get<SystemConfig>('/admin/config/system')
  },

  /** 保存系统参数配置 */
  saveSystemConfig(config: SystemConfig) {
    return client.put('/admin/config/system', config)
  },

  // ── 数据管理 ──────────────────────────────────────────────
  /** 导入知识库示例数据（reset=true 时先删除同名示例再重建） */
  seedKnowledge(reset = false) {
    return client.post<{ created: number; skipped: number; deleted: number }>(
      '/admin/knowledge/seed', null, { params: { reset } },
    )
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
