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
        </div>
      </el-tab-pane>

      <!-- 插件状态 -->
      <el-tab-pane label="插件状态" name="plugins">
        <div class="audit-table-wrap">
          <el-table :data="plugins" stripe v-loading="pluginsLoading">
            <el-table-column prop="name" label="插件名称" min-width="140" />
            <el-table-column prop="type" label="类型" width="100" />
            <el-table-column prop="version" label="版本" width="80" />
            <el-table-column prop="enabled" label="状态" width="80">
              <template #default="{ row }">
                <el-tag :type="row.enabled ? 'success' : 'info'" size="small">{{ row.enabled ? '启用' : '禁用' }}</el-tag>
              </template>
            </el-table-column>
          </el-table>
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
        </div>
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import axios from 'axios'
import { ElMessage } from 'element-plus'

const activeTab = ref('analyses')

const analyses = ref<any[]>([])
const bugCases = ref<any[]>([])
const plugins = ref<any[]>([])
const rules = ref<any[]>([])

const analysesLoading = ref(false)
const bugsLoading = ref(false)
const pluginsLoading = ref(false)
const rulesLoading = ref(false)

const analysisStatus = ref('')

function formatTime(ts: string) {
  if (!ts) return ''
  const match = ts.match(/^(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2}):(\d{2})/)
  if (!match) return ts
  let Y = +match[1], M = +match[2], D = +match[3], h = +match[4], m = +match[5], s = +match[6]
  h += 8; if (h >= 24) { h -= 24; D += 1 }
  const daysInMonth = new Date(Y, M, 0).getDate()
  if (D > daysInMonth) { D = 1; M += 1; if (M > 12) { M = 1; Y += 1 } }
  return `${Y}-${String(M).padStart(2,'0')}-${String(D).padStart(2,'0')} ${String(h).padStart(2,'0')}:${String(m).padStart(2,'0')}`
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
    const { data } = await axios.get('/api/v1/analyses', { params })
    analyses.value = data.items || []
  } catch {} finally { analysesLoading.value = false }
}

async function fetchBugCases() {
  bugsLoading.value = true
  try {
    const { data } = await axios.get('/api/v1/bug-cases', { params: { page_size: 50 } })
    bugCases.value = data.items || []
  } catch {} finally { bugsLoading.value = false }
}

async function fetchPlugins() {
  pluginsLoading.value = true
  try {
    const { data } = await axios.get('/api/v1/plugins')
    plugins.value = Array.isArray(data) ? data : data.plugins || []
  } catch {} finally { pluginsLoading.value = false }
}

async function fetchRules() {
  rulesLoading.value = true
  try {
    const { data } = await axios.get('/api/v1/rules')
    rules.value = Array.isArray(data) ? data : []
  } catch {} finally { rulesLoading.value = false }
}

onMounted(() => {
  fetchAnalyses()
  fetchBugCases()
  fetchPlugins()
  fetchRules()
})
</script>

<style scoped>
.page-title { font-size: 20px; font-weight: 600; color: #1f2937; margin: 0 0 20px; }
.audit-tabs { background: #fff; border: 1px solid #e5e7eb; border-radius: 10px; padding: 0 16px 16px; }
.tab-header { display: flex; align-items: center; gap: 12px; margin-bottom: 12px; padding-top: 8px; }
.audit-table-wrap { min-height: 200px; }
</style>
