<template>
  <div class="quality-page">
    <div class="page-head">
      <h2 class="page-title">质量回归 · 黄金集</h2>
      <div class="head-actions">
        <el-button size="small" @click="downloadExport">导出 CI 样本</el-button>
        <el-button size="small" @click="reloadAll">刷新</el-button>
      </div>
    </div>

    <p class="page-hint">
      黄金集是检索与问答质量的标尺：样本必须经审核才进入 CI 回归。
      审核链按提交人角色决定——管理员提交直接生效，开发需管理员终审，
      测试需开发复审 + 管理员终审，用户（售后/产品）需测试初审 + 开发复审 + 管理员终审。
    </p>

    <el-tabs v-model="activeTab" @tab-change="onTabChange">
      <el-tab-pane :label="`待我审核 (${pendingTotal})`" name="pending">
        <el-table :data="pending" stripe v-loading="loading">
          <el-table-column prop="id" label="ID" width="70" />
          <el-table-column prop="question" label="问题" min-width="220" show-overflow-tooltip />
          <el-table-column prop="category" label="类别" width="110">
            <template #default="{ row }">{{ row.category || '—' }}</template>
          </el-table-column>
          <el-table-column prop="device_model" label="设备" width="100">
            <template #default="{ row }">{{ row.device_model || '—' }}</template>
          </el-table-column>
          <el-table-column label="结论" width="100">
            <template #default="{ row }">{{ conclusionLabel(row.expected_conclusion) }}</template>
          </el-table-column>
          <el-table-column label="审核进度" width="150">
            <template #default="{ row }">
              {{ row.review_step }}/{{ row.review_chain.length }}
              <el-tag v-if="row.next_reviewer" size="small" type="warning" style="margin-left:6px">
                待{{ roleLabel(row.next_reviewer) }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="220" fixed="right">
            <template #default="{ row }">
              <el-button size="small" type="primary" @click="doReview(row, true)">通过</el-button>
              <el-button size="small" type="danger" plain @click="doReject(row)">驳回</el-button>
              <el-button size="small" text @click="openDetail(row)">详情</el-button>
            </template>
          </el-table-column>
        </el-table>
        <div v-if="!loading && pending.length === 0" class="empty-hint">当前没有待你审核的样本</div>
      </el-tab-pane>

      <el-tab-pane label="待复核" name="recheck">
        <div class="tab-tip">
          知识条目上线/改版后，依赖它的样本会自动进入待复核：确认期望仍成立即可恢复生效，
          期望过期则标记失效。
        </div>
        <el-table :data="recheck" stripe v-loading="loading">
          <el-table-column prop="id" label="ID" width="70" />
          <el-table-column prop="question" label="问题" min-width="240" show-overflow-tooltip />
          <el-table-column prop="category" label="类别" width="110">
            <template #default="{ row }">{{ row.category || '—' }}</template>
          </el-table-column>
          <el-table-column label="操作" width="260" fixed="right">
            <template #default="{ row }">
              <el-button size="small" type="primary" @click="doConfirm(row)">确认仍有效</el-button>
              <el-button size="small" type="danger" plain @click="doSupersede(row)">标记失效</el-button>
              <el-button size="small" text @click="openDetail(row)">详情</el-button>
            </template>
          </el-table-column>
        </el-table>
        <div v-if="!loading && recheck.length === 0" class="empty-hint">没有待复核样本</div>
      </el-tab-pane>

      <el-tab-pane label="全部样本" name="all">
        <div class="tab-header">
          <el-select v-model="statusFilter" placeholder="状态筛选" clearable style="width:150px" @change="loadAll">
            <el-option label="草稿" value="draft" />
            <el-option label="审核中" value="in_review" />
            <el-option label="已生效" value="approved" />
            <el-option label="已驳回" value="rejected" />
            <el-option label="待复核" value="needs_recheck" />
            <el-option label="已失效" value="superseded" />
          </el-select>
        </div>
        <el-table :data="allItems" stripe v-loading="loading">
          <el-table-column prop="id" label="ID" width="70" />
          <el-table-column prop="question" label="问题" min-width="240" show-overflow-tooltip />
          <el-table-column prop="category" label="类别" width="110">
            <template #default="{ row }">{{ row.category || '—' }}</template>
          </el-table-column>
          <el-table-column label="状态" width="100">
            <template #default="{ row }">
              <el-tag size="small" :type="sampleStatusLabel(row.status).type">
                {{ sampleStatusLabel(row.status).text }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="sample_version" label="版本" width="70" />
          <el-table-column label="更新时间" width="170">
            <template #default="{ row }">{{ formatTime(row.updated_at) }}</template>
          </el-table-column>
          <el-table-column label="操作" width="140" fixed="right">
            <template #default="{ row }">
              <el-button size="small" text @click="openDetail(row)">详情</el-button>
              <el-button
                v-if="row.status === 'approved'"
                size="small" text type="danger"
                @click="doSupersede(row)"
              >失效</el-button>
            </template>
          </el-table-column>
        </el-table>
        <div v-if="!loading && allItems.length === 0" class="empty-hint">暂无样本</div>
      </el-tab-pane>
    </el-tabs>

    <el-drawer v-model="detailVisible" title="样本详情" size="560px">
      <div v-if="current">
        <el-descriptions :column="1" border size="small">
          <el-descriptions-item label="问题">{{ current.question }}</el-descriptions-item>
          <el-descriptions-item label="期望结论">{{ conclusionLabel(current.expected_conclusion) }}</el-descriptions-item>
          <el-descriptions-item label="类别 / 设备">
            {{ current.category || '—' }} / {{ current.device_model || '—' }}
          </el-descriptions-item>
          <el-descriptions-item label="状态">
            {{ sampleStatusLabel(current.status).text }}
          </el-descriptions-item>
          <el-descriptions-item label="审核链">
            <span v-if="current.review_chain.length === 0">无需审核（管理员提交）</span>
            <span v-else>
              {{ current.review_chain.map(roleLabel).join(' → ') }}
              （已过 {{ current.review_step }} 级）
            </span>
          </el-descriptions-item>
          <el-descriptions-item label="槽位">
            <pre class="json-block">{{ pretty(current.slots) }}</pre>
          </el-descriptions-item>
          <el-descriptions-item label="期望章节">
            <pre class="json-block">{{ pretty(current.kb_expected) }}</pre>
          </el-descriptions-item>
          <el-descriptions-item label="期望日志">
            <pre class="json-block">{{ pretty(current.log_expected) }}</pre>
          </el-descriptions-item>
        </el-descriptions>

        <h4 class="section-title">审核轨迹</h4>
        <el-timeline v-if="reviews.length">
          <el-timeline-item
            v-for="item in reviews" :key="item.id"
            :timestamp="formatTime(item.created_at)"
          >
            <strong>{{ actionLabel(item.action) }}</strong>
            · {{ item.actor_name || '—' }}（{{ roleLabel(item.role) }}）
            <span v-if="item.reason">：{{ item.reason }}</span>
          </el-timeline-item>
        </el-timeline>
        <div v-else class="empty-hint">暂无审核记录</div>

        <template v-if="current.trace_id">
          <h4 class="section-title">当时的检索轨迹</h4>
          <div v-if="trace" class="trace-box">
            <div class="trace-line">
              结论分支：{{ trace.conclusion || '—' }} · 流水线：{{ trace.pipeline_version || '—' }}
            </div>
            <div class="trace-line">召回候选：</div>
            <ul class="trace-list">
              <li v-for="(cand, idx) in (trace.kb_candidates?.candidates || [])" :key="idx">
                #{{ idx + 1 }} {{ cand.title || cand.doc_id }} · {{ cand.section || '—' }}
                <span v-if="cand.score">（{{ Number(cand.score).toFixed(2) }}）</span>
              </li>
            </ul>
          </div>
          <div v-else class="empty-hint">加载中…</div>
        </template>
      </div>
    </el-drawer>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  confirmGoldenSample,
  exportGoldenSamples,
  getRetrievalTrace,
  listGoldenSamples,
  listPendingSamples,
  listSampleReviews,
  reviewGoldenSample,
  roleLabel,
  sampleStatusLabel,
  supersedeGoldenSample,
  type GoldenSample,
  type RetrievalTrace,
  type SampleReviewItem,
} from '@/api/quality'

const activeTab = ref<'pending' | 'recheck' | 'all'>('pending')
const loading = ref(false)
const statusFilter = ref<string | undefined>(undefined)

const pending = ref<GoldenSample[]>([])
const pendingTotal = ref(0)
const recheck = ref<GoldenSample[]>([])
const allItems = ref<GoldenSample[]>([])

const detailVisible = ref(false)
const current = ref<GoldenSample | null>(null)
const reviews = ref<SampleReviewItem[]>([])
const trace = ref<RetrievalTrace | null>(null)

function conclusionLabel(value: string): string {
  switch (value) {
    case 'answered': return '应作答'
    case 'refused': return '应拒答'
    case 'ask_slot': return '应追问'
    case 'time_mismatch': return '时间不符'
    default: return value
  }
}

function actionLabel(action: string): string {
  switch (action) {
    case 'submit': return '提交'
    case 'approve': return '审核通过'
    case 'reject': return '驳回'
    case 'revise': return '内容修改'
    case 'recheck': return '标记待复核'
    case 'recheck_confirmed': return '复核确认'
    case 'supersede': return '标记失效'
    case 'draft': return '保存草稿'
    default: return action
  }
}

function formatTime(value: string | null): string {
  if (!value) return '—'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString('zh-CN')
}

function pretty(value: unknown): string {
  if (value == null) return '—'
  try {
    return JSON.stringify(value, null, 2)
  } catch {
    return String(value)
  }
}

async function loadPending() {
  const data = await listPendingSamples()
  pending.value = data.items
  pendingTotal.value = data.total
}

async function loadRecheck() {
  const data = await listGoldenSamples({ status: 'needs_recheck', page_size: 100 })
  recheck.value = data.items
}

async function loadAll() {
  const data = await listGoldenSamples({ status: statusFilter.value, page_size: 100 })
  allItems.value = data.items
}

async function reloadAll() {
  loading.value = true
  try {
    await Promise.all([loadPending(), loadRecheck()])
    if (activeTab.value === 'all') await loadAll()
  } catch (error) {
    ElMessage.error('加载失败')
  } finally {
    loading.value = false
  }
}

function onTabChange(name: string) {
  if (name === 'all') loadAll()
}

async function doReview(row: GoldenSample, approve: boolean) {
  try {
    await reviewGoldenSample(row.id, approve)
    ElMessage.success(approve ? '已通过' : '已驳回')
    await reloadAll()
  } catch (error: any) {
    ElMessage.error(error?.response?.data?.detail || '操作失败')
  }
}

async function doReject(row: GoldenSample) {
  try {
    const { value } = await ElMessageBox.prompt('请填写驳回原因（必填）', '驳回样本', {
      inputValidator: (val: string) => (val && val.trim() ? true : '原因不能为空'),
    })
    await reviewGoldenSample(row.id, false, value)
    ElMessage.success('已驳回')
    await reloadAll()
  } catch (error: any) {
    if (error === 'cancel' || error === 'close') return
    ElMessage.error(error?.response?.data?.detail || '驳回失败')
  }
}

async function doConfirm(row: GoldenSample) {
  try {
    await confirmGoldenSample(row.id, '复核确认期望仍成立')
    ElMessage.success('已恢复生效')
    await reloadAll()
  } catch (error: any) {
    ElMessage.error(error?.response?.data?.detail || '操作失败')
  }
}

async function doSupersede(row: GoldenSample) {
  try {
    const { value } = await ElMessageBox.prompt('请填写失效原因（必填）', '标记失效', {
      inputValidator: (val: string) => (val && val.trim() ? true : '原因不能为空'),
    })
    await supersedeGoldenSample(row.id, value)
    ElMessage.success('已标记失效')
    await reloadAll()
  } catch (error: any) {
    if (error === 'cancel' || error === 'close') return
    ElMessage.error(error?.response?.data?.detail || '操作失败')
  }
}

async function openDetail(row: GoldenSample) {
  current.value = row
  detailVisible.value = true
  reviews.value = []
  trace.value = null
  try {
    const data = await listSampleReviews(row.id)
    reviews.value = data.items
  } catch {
    /* 轨迹缺失不影响详情展示 */
  }
  if (row.trace_id) {
    try {
      trace.value = await getRetrievalTrace(row.trace_id)
    } catch {
      trace.value = null
    }
  }
}

async function downloadExport() {
  try {
    const data = await exportGoldenSamples()
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `golden-samples-${Date.now()}.json`
    link.click()
    URL.revokeObjectURL(url)
    ElMessage.success(`已导出 ${data.total} 条 approved 样本`)
  } catch {
    ElMessage.error('导出失败')
  }
}

onMounted(reloadAll)
</script>

<style scoped>
.quality-page { padding: 20px; }
.page-head { display: flex; align-items: center; justify-content: space-between; }
.page-title { margin: 0 0 6px; font-size: 18px; font-weight: 600; }
.head-actions { display: flex; gap: 8px; }
.page-hint {
  margin: 0 0 16px; font-size: 12px; line-height: 1.6;
  color: var(--el-text-color-secondary, #909399);
}
.tab-header { display: flex; justify-content: flex-end; margin-bottom: 10px; }
.tab-tip {
  margin-bottom: 10px; padding: 8px 12px; font-size: 12px;
  background: var(--el-fill-color-light, #f5f7fa); border-radius: 4px;
}
.empty-hint { padding: 20px; text-align: center; font-size: 13px; color: #909399; }
.json-block {
  margin: 0; max-height: 160px; overflow: auto; font-size: 12px;
  white-space: pre-wrap; word-break: break-all;
}
.section-title { margin: 18px 0 8px; font-size: 14px; font-weight: 600; }
.trace-box { font-size: 12px; line-height: 1.7; }
.trace-line { color: var(--el-text-color-regular, #606266); }
.trace-list { margin: 4px 0 0; padding-left: 18px; }
</style>
