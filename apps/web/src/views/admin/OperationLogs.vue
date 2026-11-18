<template>
  <div class="op-logs">
    <div class="page-header">
      <h2 class="page-title">操作审计</h2>
      <div class="filters">
        <el-input v-model="filters.operator" placeholder="操作人" clearable style="width:150px" @keyup.enter="reload" />
        <el-input v-model="filters.action" placeholder="动作（如 user.create）" clearable style="width:210px"
          @keyup.enter="reload" />
        <el-select v-model="filters.result" placeholder="结果" clearable style="width:110px">
          <el-option label="成功" value="success" />
          <el-option label="失败" value="failed" />
        </el-select>
        <el-button type="primary" :loading="loading" @click="reload">查询</el-button>
      </div>
    </div>

    <el-table :data="items" stripe v-loading="loading">
      <el-table-column label="时间" width="180">
        <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
      </el-table-column>
      <el-table-column label="操作人" width="130">
        <template #default="{ row }">{{ row.operator_name || '—' }}</template>
      </el-table-column>
      <el-table-column prop="action" label="动作" width="190" />
      <el-table-column label="对象" width="180">
        <template #default="{ row }">{{ targetText(row) }}</template>
      </el-table-column>
      <el-table-column label="结果" width="90">
        <template #default="{ row }">
          <el-tag :type="row.result === 'success' ? 'success' : 'danger'" size="small">
            {{ row.result === 'success' ? '成功' : '失败' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="IP" width="140">
        <template #default="{ row }">{{ row.ip || '—' }}</template>
      </el-table-column>
      <el-table-column label="详情" min-width="120">
        <template #default="{ row }">
          <el-button v-if="row.detail" link type="primary" size="small" @click="showDetail(row)">查看</el-button>
          <span v-else>—</span>
        </template>
      </el-table-column>
      <template #empty>
        <div class="empty-hint">暂无操作记录</div>
      </template>
    </el-table>

    <el-pagination v-if="total > pageSize" class="pager" background layout="prev,pager,next" :total="total"
      :page-size="pageSize" v-model:current-page="page" @change="fetch" />

    <el-dialog v-model="detailVisible" class="admin-dialog" title="操作详情" width="640px">
      <div class="detail-head">{{ detailTitle }}</div>
      <pre class="detail-pre">{{ prettyDetail }}</pre>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { adminApi, type AdminAuditLog } from '@/api/admin'

const items = ref<AdminAuditLog[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = 20
const loading = ref(false)
const filters = reactive({ operator: '', action: '', result: '' })

const detailVisible = ref(false)
const detailTitle = ref('')
const detailRaw = ref('')

const prettyDetail = computed(() => {
  if (!detailRaw.value) return ''
  try {
    return JSON.stringify(JSON.parse(detailRaw.value), null, 2)
  } catch {
    return detailRaw.value
  }
})

function formatTime(value?: string | null) {
  if (!value) return '—'
  const d = new Date(value)
  return Number.isNaN(d.getTime()) ? value : d.toLocaleString('zh-CN', { hour12: false })
}

function targetText(row: AdminAuditLog) {
  if (!row.target_type && !row.target_id) return '—'
  return `${row.target_type || '—'}${row.target_id ? ' #' + row.target_id : ''}`
}

function showDetail(row: AdminAuditLog) {
  detailTitle.value = `${row.action} · ${formatTime(row.created_at)}`
  detailRaw.value = row.detail || ''
  detailVisible.value = true
}

async function fetch() {
  loading.value = true
  try {
    const { data } = await adminApi.listAuditLogs({
      page: page.value,
      page_size: pageSize,
      operator: filters.operator || undefined,
      action: filters.action || undefined,
      result: filters.result || undefined,
    })
    items.value = data.items || []
    total.value = data.total || 0
  } catch (e: any) {
    ElMessage.error('加载操作审计失败: ' + (e?.response?.data?.detail || e?.message))
  } finally {
    loading.value = false
  }
}

function reload() {
  page.value = 1
  fetch()
}

onMounted(fetch)
</script>

<style scoped>
.op-logs {
  max-width: 1280px;
}

.page-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 16px;
  flex-wrap: wrap;
}

.page-title {
  font-size: 20px;
  font-weight: 600;
  color: var(--chat-layout-text);
  margin: 0;
}

.filters {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.pager {
  margin-top: 16px;
  justify-content: center;
}

.empty-hint {
  padding: 24px;
  text-align: center;
  color: var(--chat-copy-text);
  font-size: 13px;
}

.detail-head {
  margin-bottom: 8px;
  color: var(--chat-copy-text);
  font-size: 12px;
}

.detail-pre {
  margin: 0;
  max-height: 55vh;
  overflow: auto;
  white-space: pre-wrap;
  word-break: break-word;
  background: var(--chat-msg-pre-bg);
  color: var(--chat-msg-pre-text);
  border: 1px solid var(--chat-msg-pre-border);
  border-radius: 8px;
  padding: 12px;
  font-size: 12px;
  line-height: 1.6;
}
</style>
