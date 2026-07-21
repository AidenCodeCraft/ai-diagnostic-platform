import client from './client'

export interface AdminStats {
  total_users: number
  total_projects: number
  total_logs: number
  total_analyses: number
  total_knowledge: number
  analysis_completed: number
  analysis_failed: number
  analysis_trend: { date: string; count: number }[]
  total_log_size_bytes: number
  active_plugins: number
}

export interface UserInfo {
  id: number
  username: string
  email: string | null
  role: string
  is_active: boolean
  created_at: string
}

export const adminApi = {
  getStats() {
    return client.get<AdminStats>('/admin/stats')
  },
  listUsers(params?: { page?: number; page_size?: number; role?: string; is_active?: boolean }) {
    return client.get<UserInfo[]>('/users', { params })
  },
  updateUser(id: number, data: Record<string, any>) {
    return client.put<UserInfo>(`/users/${id}`, data)
  },
}
