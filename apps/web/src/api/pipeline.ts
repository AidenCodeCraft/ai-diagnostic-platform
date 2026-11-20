import client from './client'

/** 预处理链单个阶段统计 */
export interface IngestStageStat {
  [status: string]: number
}

export interface IngestStats {
  total: number
  by_status: Record<string, number>
  by_stage: Record<string, IngestStageStat>
  failed: Array<{ task_id: string; stage: string; error: string }>
  running_oldest_seconds: number | null
  healthy: boolean
}

export interface RetrievalStats {
  window_hours: number
  count: number
  zero_hit_rate: number | null
  latency_ms: { p50: number | null; p95: number | null; max: number | null }
  conclusions: Record<string, number>
}

export interface VectorHealth {
  embedding_provider?: string
  embedding_dimension?: number
  is_semantic?: boolean
  collection?: string
  milvus_available?: boolean
  schema_error?: string | null
  entities?: number | null
  error?: string
}

export interface ImageCostStats {
  window_hours: number
  images: number
  by_status: Record<string, number>
  by_path: Record<string, number>
  ocr_pages: number
  vision_input_tokens: number
  vision_output_tokens: number
  estimated_cost_yuan: number
  unit_prices: Record<string, number>
}

export interface PipelineHealth {
  ingest: IngestStats
  retrieval: RetrievalStats
  vector: VectorHealth
  image_cost: ImageCostStats
  generated_at: string
}

export const pipelineApi = {
  /** 运行快照：预处理链 + 检索质量 + 向量库 + 截图识别成本 */
  health(windowHours = 24) {
    return client.get<PipelineHealth>('/logs/pipeline/health', {
      params: { window_hours: windowHours },
    })
  },

  /** 单条日志的预处理进度 */
  ingestStatus(logId: number) {
    return client.get(`/logs/${logId}/ingest-status`)
  },
}
