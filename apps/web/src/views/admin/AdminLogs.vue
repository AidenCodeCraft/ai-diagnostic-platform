<template>
  <div class="admin-logs">
    <div class="page-header">
      <h2 class="page-title">日志分析</h2>
      <div class="header-actions">
        <el-button size="small" :loading="loading" @click="fetchLogs">刷新</el-button>
        <el-button type="primary" size="small" :disabled="!selectedIds.length" :loading="batching" @click="runBatch">
          批量分析（{{ selectedIds.length }}）
        </el-button>
      </div>
    </div>

    <el-card>
      <el-table :data="logs" stripe v-loading="loading" @selection-change="onSelectionChange">
        <el-table-column type="selection" width="45" />
        <el-table-column prop="id" label="ID" width="70" />
        <el-table-column prop="filename" label="文件名" min-width="180" show-overflow-tooltip />
        <el-table-column label="大小" width="100">
          <template #default="{ row }">{{ formatSize(row.size) }}</template>
        </el-table-column>
        <el-table-column prop="device" label="设备" width="100" />
        <el-table-column prop="status" label="状态" width="110">
          <template #default="{ row }"><el-tag size="small">{{ row.status }}</el-tag></template>
        </el-table-column>
        <el-table-column label="上传时间" width="180">
          <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="140">
          <template #default="{ row }">
            <el-button size="small" @click="openEvents(row)">查看事件</el-button>
          </template>
        </el-table-column>
      </el-table>
      <div v-if="!loading && logs.length === 0" class="empty-hint">暂无日志</div>
    </el-card>

    <el-card v-if="tasks.length" style="margin-top:16px">
      <template #header><span>批量分析任务（{{ tasks.length }}）</span></template>
      <el-table :data="tasks" stripe>
        <el-table-column prop="analysisId" label="分析ID" width="90" />
        <el-table-column prop="logId" label="日志ID" width="90" />
        <el-table-column label="状态" width="110">
          <template #default="{ row }">
            <el-tag size="small" :type="statusType(row.status)">{{ statusLabel(row.status) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="error" label="错误" show-overflow-tooltip />
        <el-table-column label="操作" width="190">
          <template #default="{ row }">
            <el-button size="small" :disabled="row.status !== 'completed'" @click="viewResult(row)">查看结果</el-button>
            <el-button size="small" type="warning" :disabled="!['failed', 'completed'].includes(row.status)" @click="retryTask(row)">重试</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-dialog v-model="showEvents" title="日志解析事件" width="900px">
      <div class="event-filter">
        <el-input v-model="eventKeyword" placeholder="关键字过滤" size="small" style="width:220px" clearable />
        <el-checkbox v-model="eventOnlyError">仅错误</el-checkbox>
        <el-button size="small" type="primary" :loading="eventsLoading" @click="loadEvents(1)">查询</el-button>
        <span class="event-total">共 {{ eventsTotal }} 条</span>
      </div>
      <el-table :data="events" stripe size="small" max-height="420" v-loading="eventsLoading">
        <el-table-column prop="line_no" label="行号" width="80" />
        <el-table-column prop="level" label="级别" width="90" />
        <el-table-column prop="module" label="模块" width="110" />
        <el-table-column prop="classification" label="分类" width="130" />
        <el-table-column prop="message" label="内容" show-overflow-tooltip />
      </el-table>
      <el-pagination
        v-if="eventsTotal > eventPageSize"
        background layout="prev,pager,next"
        :total="eventsTotal" :page-size="eventPageSize"
        v-model:current-page="eventPage"
        @change="loadEvents"
        style="margin-top:12px"
      />
    </el-dialog>

    <el-dialog v-model="showResult" title="诊断结果" width="760px">
      <pre class="result-pre">{{ resultText }}</pre>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import { ElMessage } from 'element-plus'
import { logApi, analysisApi, type LogItem, type LogEventItem } from '@/api/logs'
import {
  analysisStatusLabel,
  analysisStatusType,
  formatBytes,
  formatDateTime,
} from '@/utils/format'

const logs = ref<LogItem[]>([])
const loading = ref(false)
const batching = ref(false)
const selectedIds = ref<number[]>([])

interface BatchTask {
  analysisId: number
  logId: number
  status: string
  error: string
}
const tasks = ref<BatchTask[]>([])
let pollTimer: number | undefined

const showEvents = ref(false)
const eventsLoading = ref(false)
const events = ref<LogEventItem[]>([])
const eventsTotal = ref(0)
const eventPage = ref(1)
const eventPageSize = 50
const eventKeyword = ref('')
const eventOnlyError = ref(true)
const currentLogId = ref(0)

const showResult = ref(false)
const resultText = ref('')

const formatTime = formatDateTime
const formatSize = formatBytes
const statusLabel = analysisStatusLabel
const statusType = analysisStatusType

async function fetchLogs() {
  loading.value = true
  try {
    const { data } = await logApi.list()
    logs.value = Array.isArray(data) ? data : []
  } catch (e: any) {
    logs.value = []
    ElMessage.error('获取日志列表失败: ' + (e.response?.data?.detail || e.message))
  } finally {
    loading.value = false
  }
}

function onSelectionChange(rows: LogItem[]) {
  selectedIds.value = rows.map((row) => row.id)
}

function stopPolling() {
  if (pollTimer) {
    window.clearInterval(pollTimer)
    pollTimer = undefined
  }
}

async function pollTasks() {
  const pending = tasks.value.filter((task) => ['pending', 'running'].includes(task.status))
  if (!pending.length) {
    stopPolling()
    return
  }
  await Promise.all(pending.map(async (task) => {
    try {
      const { data } = await analysisApi.get(task.analysisId)
      task.status = data?.status || task.status
      if (data?.error_message) task.error = data.error_message
    } catch { /* 单条轮询失败忽略，下轮重试 */ }
  }))
}

function startPolling() {
  stopPolling()
  pollTimer = window.setInterval(pollTasks, 2000)
  void pollTasks()
}

async function runBatch() {
  if (!selectedIds.value.length) return
  batching.value = true
  try {
    const { data } = await analysisApi.runBatch(selectedIds.value)
    const items = data?.items || []
    tasks.value = items.map((item: any) => ({
      analysisId: item.id,
      logId: item.log_id,
      status: item.status || 'pending',
      error: item.error || '',
    }))
    ElMessage.success(`已创建 ${tasks.value.length} 个分析任务`)
    startPolling()
  } catch (e: any) {
    ElMessage.error('批量分析失败: ' + (e.response?.data?.detail || e.message))
  } finally {
    batching.value = false
  }
}

async function viewResult(task: BatchTask) {
  try {
    const { data } = await analysisApi.getResult(task.analysisId)
    resultText.value = data?.diagnosis_markdown || data?.summary || '暂无结果'
    showResult.value = true
  } catch (e: any) {
    ElMessage.error('获取结果失败: ' + (e.response?.data?.detail || e.message))
  }
}

async function retryTask(task: BatchTask) {
  try {
    await analysisApi.retry(task.analysisId)
    task.status = 'pending'
    task.error = ''
    startPolling()
    ElMessage.success('已重新提交分析')
  } catch (e: any) {
    ElMessage.error('重试失败: ' + (e.response?.data?.detail || e.message))
  }
}

async function openEvents(row: LogItem) {
  currentLogId.value = row.id
  showEvents.value = true
  await loadEvents(1)
}

async function loadEvents(page = 1) {
  if (!currentLogId.value) return
  eventsLoading.value = true
  try {
    try {
      await logApi.parse(currentLogId.value)
    } catch { /* 已解析或解析失败时仍尝试查询已持久化事件 */ }
    const { data } = await logApi.queryEvents(currentLogId.value, {
      page,
      page_size: eventPageSize,
      is_error: eventOnlyError.value || undefined,
      keyword: eventKeyword.value || undefined,
    })
    events.value = data?.items || []
    eventsTotal.value = data?.total || 0
    eventPage.value = page
  } catch (e: any) {
    events.value = []
    eventsTotal.value = 0
    ElMessage.error('查询事件失败: ' + (e.response?.data?.detail || e.message))
  } finally {
    eventsLoading.value = false
  }
}

onMounted(fetchLogs)
onUnmounted(stopPolling)
</script>

<style scoped>
.admin-logs { max-width: 1200px; }
.page-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 16px; }
.page-title { font-size: 20px; font-weight: 600; color: #1f2937; margin: 0; }
.header-actions { display: flex; gap: 8px; }
.empty-hint { padding: 24px; text-align: center; color: #9ca3af; font-size: 13px; }
.event-filter { display: flex; align-items: center; gap: 12px; margin-bottom: 12px; }
.event-total { color: #6b7280; font-size: 13px; }
.result-pre { white-space: pre-wrap; word-break: break-word; font-family: ui-monospace, Menlo, Consolas, monospace; font-size: 13px; line-height: 1.7; margin: 0; }
</style>
