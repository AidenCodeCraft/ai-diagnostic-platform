import client from './client'

/** 黄金集样本（回归测试基准） */
export interface GoldenSample {
  id: number
  question: string
  slots: Record<string, unknown> | null
  kb_expected: Array<{ doc_id?: number; section?: string; pk?: string }> | null
  log_expected: Record<string, unknown> | null
  expected_conclusion: 'answered' | 'refused' | 'ask_slot' | 'time_mismatch' | string
  category: string | null
  device_model: string | null
  status: 'draft' | 'in_review' | 'approved' | 'rejected' | 'superseded' | 'needs_recheck' | string
  sample_version: number
  review_chain: string[]
  review_step: number
  next_reviewer: string | null
  submitted_by: number | null
  submitted_at: string | null
  approved_by: number | null
  approved_at: string | null
  trace_id: number | null
  replay_snapshot_ref: string | null
  note: string | null
  created_at: string | null
  updated_at: string | null
}

export interface SampleReviewItem {
  id: number
  sample_version: number
  actor_id: number | null
  actor_name: string | null
  role: string | null
  action: string
  reason: string | null
  created_at: string | null
}

export interface Paged<T> {
  items: T[]
  total: number
  page: number
  page_size: number
}

export interface RetrievalTrace {
  id: number
  session_id: number | null
  message_id: number | null
  log_id: number | null
  question: string
  kb_candidates: {
    candidates?: Array<Record<string, unknown>>
    clarification?: Array<Record<string, unknown>>
  } | null
  log_patterns: Record<string, unknown> | null
  log_blocks: Record<string, unknown> | null
  timings: Record<string, unknown> | null
  conclusion: string | null
  pipeline_version: string | null
  created_at: string | null
}

export async function listGoldenSamples(params: {
  status?: string
  category?: string
  device_model?: string
  mine?: boolean
  page?: number
  page_size?: number
}): Promise<Paged<GoldenSample>> {
  const { data } = await client.get('/quality/golden-samples', { params })
  return data
}

export async function listPendingSamples(): Promise<Paged<GoldenSample>> {
  const { data } = await client.get('/quality/golden-samples/pending')
  return data
}

export async function reviewGoldenSample(
  id: number, approve: boolean, reason?: string,
): Promise<GoldenSample> {
  const { data } = await client.post(`/quality/golden-samples/${id}/review`, { approve, reason })
  return data
}

export async function confirmGoldenSample(id: number, reason?: string): Promise<GoldenSample> {
  const { data } = await client.post(`/quality/golden-samples/${id}/confirm`, { reason })
  return data
}

export async function supersedeGoldenSample(id: number, reason: string): Promise<GoldenSample> {
  const { data } = await client.post(`/quality/golden-samples/${id}/supersede`, { reason })
  return data
}

export async function listSampleReviews(id: number): Promise<{ items: SampleReviewItem[] }> {
  const { data } = await client.get(`/quality/golden-samples/${id}/reviews`)
  return data
}

export async function exportGoldenSamples(): Promise<{ total: number; items: GoldenSample[] }> {
  const { data } = await client.get('/quality/golden-samples/export')
  return data
}

export async function getRetrievalTrace(id: number): Promise<RetrievalTrace> {
  const { data } = await client.get(`/quality/traces/${id}`)
  return data
}

/** 状态 → 中文标签与颜色 */
export function sampleStatusLabel(status: string): { text: string; type: string } {
  switch (status) {
    case 'draft': return { text: '草稿', type: 'info' }
    case 'in_review': return { text: '审核中', type: 'warning' }
    case 'approved': return { text: '已生效', type: 'success' }
    case 'rejected': return { text: '已驳回', type: 'danger' }
    case 'superseded': return { text: '已失效', type: 'info' }
    case 'needs_recheck': return { text: '待复核', type: 'warning' }
    default: return { text: status, type: 'info' }
  }
}

export function roleLabel(role: string | null): string {
  switch (role) {
    case 'admin': return '管理员'
    case 'developer': return '开发'
    case 'engineer': return '测试'
    case 'user': return '用户'
    default: return role || '—'
  }
}
