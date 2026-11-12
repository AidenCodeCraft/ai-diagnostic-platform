<template>
  <div class="audit-page">
    <h2 class="page-title">审核与日志监控</h2>

    <el-tabs v-model="activeTab" class="audit-tabs">
      <!-- 分析任务监控 -->
      <el-tab-pane label="分析任务监控" name="analyses">
        <div class="tab-header">
          <el-select v-model="analysisStatus" placeholder="状态筛选" clearable style="width:140px" @change="fetchAnalyses">
            <el-option label="运行中" value="running" />
            <el-option label="已完成" value="completed" />
            <el-option label="失败" value="failed" />
          </el-select>
        </div>
        <div class="audit-table-wrap">
          <el-table :data="analyses" stripe v-loading="analysesLoading">
            <el-table-column prop="id" label="ID" width="60" />
            <el-table-column prop="log_id" label="日志ID" width="80" />
            <el-table-column prop="status" label="状态" width="90">
              <template #default="{ row }">
                <el-tag :type="statusTag(row.status)" size="small">{{ row.status }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="model" label="模型" width="100"><template #default="{ row }">{{ row.model || '—' }}</template></el-table-column>
            <el-table-column prop="confidence" label="置信度" width="90">
              <template #default="{ row }">{{ row.confidence != null ? (row.confidence * 100).toFixed(0) + '%' : '—' }}</template>
            </el-table-column>
            <el-table-column prop="error_message" label="错误信息" min-width="180"><template #default="{ row }">{{ row.error_message || '—' }}</template></el-table-column>
            <el-table-column prop="created_at" label="创建时间" width="170">
              <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
            </el-table-column>
          </el-table>
          <div v-if="!analysesLoading && analyses.length === 0" class="empty-hint">暂无分析任务</div>
        </div>
      </el-tab-pane>

      <!-- Bug 案例审核 -->
      <el-tab-pane label="Bug 案例" name="bugs">
        <div class="audit-table-wrap">
          <el-table :data="bugCases" stripe v-loading="bugsLoading">
            <el-table-column prop="id" label="ID" width="60" />
            <el-table-column prop="title" label="标题" min-width="160" />
            <el-table-column prop="severity" label="严重程度" width="90">
              <template #default="{ row }">
                <el-tag :type="severityTag(row.severity)" size="small">{{ row.severity || '—' }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="module" label="模块" width="100"><template #default="{ row }">{{ row.module || '—' }}</template></el-table-column>
            <el-table-column prop="root_cause" label="根因" min-width="160"><template #default="{ row }">{{ row.root_cause || '—' }}</template></el-table-column>
            <el-table-column prop="confidence" label="置信度" width="80">
              <template #default="{ row }">{{ row.confidence != null ? (row.confidence * 100).toFixed(0) + '%' : '—' }}</template>
            </el-table-column>
            <el-table-column prop="created_at" label="创建时间" width="170">
              <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
            </el-table-column>
          </el-table>
          <div v-if="!bugsLoading && bugCases.length === 0" class="empty-hint">暂无 Bug 案例</div>
        </div>
      </el-tab-pane>

      <!-- 规则管理 -->
      <el-tab-pane label="诊断规则" name="rules">
        <div class="audit-table-wrap">
          <el-table :data="rules" stripe v-loading="rulesLoading">
            <el-table-column prop="name" label="规则名称" min-width="160" />
            <el-table-column prop="category" label="分类" width="120"><template #default="{ row }">{{ row.category || '—' }}</template></el-table-column>
            <el-table-column prop="description" label="描述" min-width="200"><template #default="{ row }">{{ row.description || '—' }}</template></el-table-column>
          </el-table>
          <div v-if="!rulesLoading && rules.length === 0" class="empty-hint">暂无诊断规则</div>
        </div>
      </el-tab-pane>

      <!-- 知识自进化审核 -->
      <el-tab-pane label="知识自进化审核" name="drafts">
        <div class="tab-header">
          <span class="tab-hint">用户标记「已解决」后自动蒸馏出的知识库候选，审核通过后才会进入检索。</span>
          <el-button size="small" @click="fetchDrafts" :loading="draftsLoading">刷新</el-button>
        </div>
        <div class="audit-table-wrap">
          <el-table :data="drafts" stripe v-loading="draftsLoading">
            <el-table-column prop="title" label="候选标题" min-width="180" />
            <el-table-column prop="symptom" label="现象" min-width="150">
              <template #default="{ row }">{{ row.symptom || '—' }}</template>
            </el-table-column>
            <el-table-column prop="log_keywords" label="日志关键词" min-width="150">
              <template #default="{ row }">{{ (row.log_keywords || []).join('、') || '—' }}</template>
            </el-table-column>
            <el-table-column prop="confidence" label="置信度" width="80">
              <template #default="{ row }">{{ row.confidence != null ? (row.confidence * 100).toFixed(0) + '%' : '—' }}</template>
            </el-table-column>
            <el-table-column prop="quality_score" label="质量分" width="80">
              <template #default="{ row }">{{ row.quality_score != null ? Math.round(row.quality_score) : '—' }}</template>
            </el-table-column>
            <el-table-column prop="created_at" label="创建时间" width="170">
              <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
            </el-table-column>
            <el-table-column label="操作" width="220" fixed="right">
              <template #default="{ row }">
                <el-button size="small" @click="openDraft(row)">查看</el-button>
                <el-button size="small" type="primary" @click="approveDraft(row)">通过</el-button>
                <el-button size="small" type="danger" @click="rejectDraft(row)">驳回</el-button>
              </template>
            </el-table-column>
          </el-table>
          <div v-if="!draftsLoading && drafts.length === 0" class="empty-hint">暂无自进化候选</div>
        </div>
      </el-tab-pane>
    </el-tabs>

    <!-- 候选详情 -->
    <el-dialog v-model="viewDraftVisible" title="候选详情" width="760px" top="6vh">
      <div v-if="viewDraftLoading" class="empty-hint">加载中…</div>
      <template v-else>
        <div class="draft-meta">
          <span>质量分：{{ viewDraftQuality != null ? Math.round(viewDraftQuality) : '—' }}</span>
        </div>
        <div v-if="viewDraftIssues.length" class="draft-issues">
          <div v-for="(it, i) in viewDraftIssues" :key="i" :class="['draft-issue', it.level]">
            {{ it.level === 'error' ? '✕' : '⚠' }} {{ it.message }}
          </div>
        </div>
        <pre class="draft-content">{{ viewDraftContent }}</pre>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import client from '@/api/client'
import { ElMessage } from 'element-plus'

const activeTab = ref('analyses')

const analyses = ref<any[]>([])
const bugCases = ref<any[]>([])
const rules = ref<any[]>([])
const drafts = ref<any[]>([])

const analysesLoading = ref(false)
const bugsLoading = ref(false)
const rulesLoading = ref(false)
const draftsLoading = ref(false)

const analysisStatus = ref('')

/** 使用 Intl.DateTimeFormat 统一处理时区（浏览器本地时区） */
const timeFormatter = new Intl.DateTimeFormat('zh-CN', {
  year: 'numeric', month: '2-digit', day: '2-digit',
  hour: '2-digit', minute: '2-digit', second: '2-digit',
  hour12: false,
})

function formatTime(ts: string) {
  if (!ts) return ''
  try { return timeFormatter.format(new Date(ts)) } catch { return ts }
}

function statusTag(s: string) {
  if (s === 'completed') return 'success'
  if (s === 'failed') return 'danger'
  if (s === 'running') return 'warning'
  return 'info'
}

function severityTag(s: string) {
  if (s === 'critical') return 'danger'
  if (s === 'high') return 'warning'
  return 'info'
}

async function fetchAnalyses() {
  analysesLoading.value = true
  try {
    const params: any = { page_size: 50 }
    if (analysisStatus.value) params.status = analysisStatus.value
    const { data } = await client.get('/analyses', { params })
    analyses.value = data.items || []
  } catch (e: any) {
    analyses.value = []
    console.error('[Audit] fetchAnalyses failed:', e?.response?.data?.detail || e?.message || e)
  } finally {
    analysesLoading.value = false
  }
}

async function fetchBugCases() {
  bugsLoading.value = true
  try {
    const { data } = await client.get('/bug-cases', { params: { page_size: 50 } })
    bugCases.value = data.items || []
  } catch (e: any) {
    bugCases.value = []
    console.error('[Audit] fetchBugCases failed:', e?.response?.data?.detail || e?.message || e)
  } finally {
    bugsLoading.value = false
  }
}

async function fetchRules() {
  rulesLoading.value = true
  try {
    const { data } = await client.get('/rules')
    rules.value = Array.isArray(data) ? data : []
  } catch (e: any) {
    rules.value = []
    console.error('[Audit] fetchRules failed:', e?.response?.data?.detail || e?.message || e)
  } finally {
    rulesLoading.value = false
  }
}

// ── 知识自进化审核 ─────────────────────────────────────
async function fetchDrafts() {
  draftsLoading.value = true
  try {
    const { data } = await client.get('/admin/knowledge/profiles/drafts')
    drafts.value = data.items || []
  } catch (e: any) {
    drafts.value = []
    console.error('[Audit] fetchDrafts failed:', e?.response?.data?.detail || e?.message || e)
  } finally {
    draftsLoading.value = false
  }
}

async function approveDraft(row: any) {
  try {
    await client.post(`/admin/knowledge/profiles/${row.id}/approve`)
    ElMessage.success('已通过，候选已进入知识库检索')
    await fetchDrafts()
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '操作失败')
  }
}

async function rejectDraft(row: any) {
  try {
    await client.post(`/admin/knowledge/profiles/${row.id}/reject`)
    ElMessage.success('已驳回')
    await fetchDrafts()
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '操作失败')
  }
}

// ── 候选详情 ──
const viewDraftVisible = ref(false)
const viewDraftLoading = ref(false)
const viewDraftContent = ref('')
const viewDraftQuality = ref<number | null>(null)
const viewDraftIssues = ref<any[]>([])

async function openDraft(row: any) {
  viewDraftVisible.value = true
  viewDraftLoading.value = true
  viewDraftContent.value = row.content || ''
  viewDraftQuality.value = row.quality_score != null ? row.quality_score : null
  viewDraftIssues.value = []
  try {
    const { data } = await client.post('/knowledge/format/preview', {
      content: row.content || '',
      doc_type: row.doc_type,
    })
    viewDraftContent.value = data.normalized_content || row.content || ''
    viewDraftQuality.value = data.quality_score != null ? data.quality_score : viewDraftQuality.value
    viewDraftIssues.value = data.issues || []
  } catch (e: any) {
    console.warn('[Audit] preview failed:', e?.response?.data?.detail || e?.message || e)
  } finally {
    viewDraftLoading.value = false
  }
}

onMounted(() => {
  fetchAnalyses()
  fetchBugCases()
  fetchRules()
  fetchDrafts()
})
</script>

<style scoped>
.page-title { font-size: 20px; font-weight: 600; color: #1f2937; margin: 0 0 20px; }
.audit-tabs { background: #fff; border: 1px solid #e5e7eb; border-radius: 10px; padding: 0 16px 16px; }
.tab-header { display: flex; align-items: center; gap: 12px; margin-bottom: 12px; padding-top: 8px; }
.tab-hint { font-size: 12px; color: #9ca3af; margin-right: auto; }
.draft-meta { font-size: 13px; color: #374151; margin-bottom: 8px; }
.draft-issues { margin-bottom: 8px; }
.draft-issue { font-size: 12px; line-height: 1.7; }
.draft-issue.error { color: #dc2626; }
.draft-issue.warn { color: #d97706; }
.draft-content { max-height: 55vh; overflow: auto; background: #f9fafb; border: 1px solid #e5e7eb; border-radius: 8px; padding: 12px; font-size: 12px; line-height: 1.6; white-space: pre-wrap; }
.audit-table-wrap { min-height: 200px; }
.empty-hint { text-align: center; padding: 40px 0; color: #9ca3af; font-size: 14px; }
</style>
