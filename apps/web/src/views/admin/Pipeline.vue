<template>
  <div class="pipeline-page">
    <div class="page-head">
      <h2 class="page-title">运行监控</h2>
      <div class="head-actions">
        <el-select v-model="windowHours" size="small" style="width: 120px" @change="load">
          <el-option :value="24" label="近 24 小时" />
          <el-option :value="72" label="近 3 天" />
          <el-option :value="168" label="近 7 天" />
        </el-select>
        <el-button size="small" @click="load">刷新</el-button>
      </div>
    </div>

    <p class="page-hint">
      本页只读数据库与进程状态，不访问消息队列——队列故障时本页仍应可打开。
      「估算费用」按高峰单价计算（宁高估不低估），真实账单以服务商为准。
    </p>

    <el-alert
      v-if="vectorAlert"
      :title="vectorAlert"
      type="warning"
      :closable="false"
      show-icon
      class="vector-alert"
    />

    <div class="cards">
      <el-card shadow="never" class="card">
        <template #header>
          <div class="card-head">
            <span>预处理链</span>
            <el-tag size="small" :type="health?.ingest?.healthy ? 'success' : 'danger'">
              {{ health?.ingest?.healthy ? '正常' : '有失败任务' }}
            </el-tag>
          </div>
        </template>
        <div class="metrics">
          <div class="metric"><span class="k">任务总数</span><span class="v">{{ health?.ingest?.total ?? '—' }}</span></div>
          <div class="metric">
            <span class="k">运行最久</span>
            <span class="v">{{ formatSeconds(health?.ingest?.running_oldest_seconds) }}</span>
          </div>
        </div>
        <el-table :data="stageRows" size="small" stripe>
          <el-table-column prop="stage" label="阶段" width="120" />
          <el-table-column prop="succeeded" label="成功" width="80" />
          <el-table-column prop="failed" label="失败" width="80" />
          <el-table-column prop="running" label="运行中" width="90" />
        </el-table>
        <div v-if="failedTasks.length" class="failed-block">
          <div class="failed-title">失败任务</div>
          <div v-for="task in failedTasks" :key="task.task_id" class="failed-item">
            <code>{{ task.task_id }}</code> · {{ task.error || '无错误信息' }}
          </div>
        </div>
      </el-card>

      <el-card shadow="never" class="card">
        <template #header><span>检索质量</span></template>
        <div class="metrics">
          <div class="metric"><span class="k">提问数</span><span class="v">{{ health?.retrieval?.count ?? '—' }}</span></div>
          <div class="metric">
            <span class="k">零命中率</span>
            <span class="v">{{ formatRate(health?.retrieval?.zero_hit_rate) }}</span>
          </div>
          <div class="metric"><span class="k">P50</span><span class="v">{{ health?.retrieval?.latency_ms?.p50 ?? '—' }} ms</span></div>
          <div class="metric"><span class="k">P95</span><span class="v">{{ health?.retrieval?.latency_ms?.p95 ?? '—' }} ms</span></div>
        </div>
        <el-table :data="conclusionRows" size="small" stripe>
          <el-table-column prop="conclusion" label="结论分支" />
          <el-table-column prop="count" label="次数" width="90" />
        </el-table>
      </el-card>

      <el-card shadow="never" class="card">
        <template #header><span>截图识别成本</span></template>
        <div class="metrics">
          <div class="metric"><span class="k">图片数</span><span class="v">{{ health?.image_cost?.images ?? '—' }}</span></div>
          <div class="metric"><span class="k">OCR 页数</span><span class="v">{{ health?.image_cost?.ocr_pages ?? '—' }}</span></div>
          <div class="metric">
            <span class="k">视觉 tokens</span>
            <span class="v">{{ (health?.image_cost?.vision_input_tokens ?? 0) + (health?.image_cost?.vision_output_tokens ?? 0) }}</span>
          </div>
          <div class="metric highlight">
            <span class="k">估算费用</span>
            <span class="v">¥{{ (health?.image_cost?.estimated_cost_yuan ?? 0).toFixed(4) }}</span>
          </div>
        </div>
        <el-table :data="pathRows" size="small" stripe>
          <el-table-column prop="path" label="识别路径" />
          <el-table-column prop="count" label="数量" width="90" />
        </el-table>
      </el-card>
    </div>

    <p class="foot">快照时间：{{ health?.generated_at || '—' }}</p>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { pipelineApi, type PipelineHealth } from '@/api/pipeline'

const health = ref<PipelineHealth | null>(null)
const windowHours = ref(24)

const stageRows = computed(() => {
  const byStage = health.value?.ingest?.by_stage || {}
  return Object.entries(byStage).map(([stage, stats]) => ({
    stage,
    succeeded: stats.succeeded || 0,
    failed: stats.failed || 0,
    running: stats.running || 0,
  }))
})

const conclusionRows = computed(() =>
  Object.entries(health.value?.retrieval?.conclusions || {}).map(([conclusion, count]) => ({
    conclusion,
    count,
  })),
)

const pathRows = computed(() =>
  Object.entries(health.value?.image_cost?.by_path || {}).map(([path, count]) => ({ path, count })),
)

const failedTasks = computed(() => health.value?.ingest?.failed || [])

/** 向量侧异常必须显式提示：它决定检索是否有语义能力 */
const vectorAlert = computed(() => {
  const vector = health.value?.vector
  if (!vector) return ''
  if (vector.error) return `向量服务不可用：${vector.error}`
  if (vector.schema_error) return `集合与配置不兼容：${vector.schema_error}`
  if (vector.is_semantic === false) return `当前 embedding 是哈希兜底（非语义），检索质量不可信`
  if (vector.milvus_available === false) return 'Milvus 未连通，检索已退化为关键词'
  return ''
})

function formatSeconds(value: number | null | undefined): string {
  if (value == null) return '—'
  if (value < 60) return `${Math.round(value)} 秒`
  if (value < 3600) return `${Math.round(value / 60)} 分钟`
  return `${(value / 3600).toFixed(1)} 小时`
}

function formatRate(value: number | null | undefined): string {
  if (value == null) return '—'
  return `${(value * 100).toFixed(1)}%`
}

async function load() {
  try {
    const { data } = await pipelineApi.health(windowHours.value)
    health.value = data
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '加载运行监控失败')
  }
}

onMounted(load)
</script>

<style scoped>
.pipeline-page {
  padding: 20px 24px;
}
.page-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}
.page-title {
  font-size: 18px;
  font-weight: 600;
  margin: 0;
}
.head-actions {
  display: flex;
  gap: 8px;
  align-items: center;
}
.page-hint {
  color: var(--el-text-color-secondary);
  font-size: 12px;
  margin: 0 0 12px;
  line-height: 1.6;
}
.vector-alert {
  margin-bottom: 12px;
}
.cards {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(340px, 1fr));
  gap: 16px;
}
.card-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.metrics {
  display: flex;
  flex-wrap: wrap;
  gap: 18px;
  margin-bottom: 12px;
}
.metric {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.metric .k {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.metric .v {
  font-size: 16px;
  font-weight: 600;
}
.metric.highlight .v {
  color: var(--el-color-danger);
}
.failed-block {
  margin-top: 12px;
  font-size: 12px;
}
.failed-title {
  color: var(--el-color-danger);
  margin-bottom: 4px;
}
.failed-item {
  color: var(--el-text-color-regular);
  line-height: 1.6;
  word-break: break-all;
}
.foot {
  margin-top: 16px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
</style>
