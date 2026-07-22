<template>
  <div class="page-container">
    <div class="card-header"><h2>诊断报告</h2></div>
    <el-card>
      <el-table :data="items" stripe v-loading="loading" @row-click="viewDetail" style="cursor:pointer">
        <el-table-column prop="id" label="ID" width="60" />
        <el-table-column prop="title" label="标题" min-width="200" />
        <el-table-column prop="model" label="模型" width="100" />
        <el-table-column prop="confidence" label="置信度" width="120"><template #default="{ row }">{{ row.confidence ? (row.confidence * 100).toFixed(0) + '%' : '-' }}</template></el-table-column>
        <el-table-column prop="summary" label="摘要" show-overflow-tooltip />
        <el-table-column prop="created_at" label="时间" width="180"><template #default="{ row }">{{ formatTime(row.created_at) }}</template></el-table-column>
        <el-table-column label="操作" width="180">
          <template #default="{ row }">
            <el-button size="small" type="success" @click.stop="exportMd(row.id)">导出MD</el-button>
            <el-button size="small" type="danger" @click.stop="remove(row.id)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
      <el-pagination v-if="total > pageSize" style="margin-top:16px;justify-content:center" background layout="prev,pager,next" :total="total" :page-size="pageSize" v-model:current-page="page" @change="fetch" />
    </el-card>

    <el-dialog v-model="showDetail" title="报告详情" width="700px">
      <template v-if="detail">
        <el-descriptions :column="2" border style="margin-bottom:16px">
          <el-descriptions-item label="模型">{{ detail.model }}</el-descriptions-item>
          <el-descriptions-item label="置信度">{{ detail.confidence ? (detail.confidence * 100).toFixed(0) + '%' : '-' }}</el-descriptions-item>
        </el-descriptions>
        <h4 style="margin:12px 0 8px">分析摘要</h4><p style="white-space:pre-wrap;line-height:1.8;margin-bottom:12px">{{ detail.summary }}</p>
        <h4 style="margin:12px 0 8px">根因分析</h4><p style="white-space:pre-wrap;line-height:1.8;margin-bottom:12px">{{ detail.root_cause }}</p>
        <h4 style="margin:12px 0 8px">建议措施</h4><ol style="padding-left:20px;line-height:2.2"><li v-for="(s,i) in detail.next_steps" :key="i">{{ s }}</li></ol>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { reportApi } from '@/api/reports'
import { useLogger } from '@/logger'

const { warn } = useLogger()
import { ElMessage } from 'element-plus'

const items = ref<any[]>([])
const loading = ref(false)
const page = ref(1)
const pageSize = 20
const total = ref(0)
const showDetail = ref(false)
const detail = ref<any>(null)

function formatTime(ts: string) { return ts ? new Date(ts).toLocaleString() : '' }

async function fetch() {
  loading.value = true
  try { const { data } = await reportApi.list({ page: page.value, page_size: pageSize }); items.value = data.items; total.value = data.total } catch { warn('Failed to fetch reports', 'api') }
  finally { loading.value = false }
}

async function viewDetail(row: any) {
  try { const { data } = await reportApi.get(row.id); detail.value = data; showDetail.value = true } catch {}
}

async function exportMd(id: number) {
  try {
    const { data } = await reportApi.exportMarkdown(id)
    const blob = new Blob([data], { type: 'text/markdown' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a'); a.href = url; a.download = `report-${id}.md`; a.click()
    URL.revokeObjectURL(url)
    ElMessage.success('下载成功！')
  } catch { ElMessage.error('导出失败') }
}

async function remove(id: number) {
  try { await reportApi.delete(id); await fetch(); ElMessage.success('已删除') } catch { ElMessage.error('删除失败') }
}

onMounted(fetch)
</script>
