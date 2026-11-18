<template>
  <div class="admin-page">
    <div class="page-header">
      <h2 class="page-title">项目管理</h2>
      <el-button type="primary" @click="openCreate">新建项目</el-button>
    </div>

    <el-table :data="items" stripe v-loading="loading">
      <el-table-column prop="id" label="ID" width="70" />
      <el-table-column prop="name" label="项目名称" min-width="180" />
      <el-table-column label="芯片" width="130">
        <template #default="{ row }">{{ row.chip || '—' }}</template>
      </el-table-column>
      <el-table-column label="固件" width="140">
        <template #default="{ row }">{{ row.firmware || '—' }}</template>
      </el-table-column>
      <el-table-column label="设备类型" width="130">
        <template #default="{ row }">{{ row.device_type || '—' }}</template>
      </el-table-column>
      <el-table-column label="描述" min-width="180">
        <template #default="{ row }">{{ row.description || '—' }}</template>
      </el-table-column>
      <el-table-column label="更新时间" width="170">
        <template #default="{ row }">{{ formatTime(row.updated_at || row.created_at) }}</template>
      </el-table-column>
      <el-table-column label="操作" width="140" fixed="right">
        <template #default="{ row }">
          <el-button link type="primary" size="small" @click="openEdit(row)">编辑</el-button>
          <el-button link type="danger" size="small" @click="remove(row)">删除</el-button>
        </template>
      </el-table-column>
      <template #empty>
        <div class="empty-hint">暂无项目</div>
      </template>
    </el-table>

    <el-pagination v-if="total > pageSize" class="pager" background layout="prev,pager,next" :total="total"
      :page-size="pageSize" v-model:current-page="page" @change="fetch" />

    <el-dialog v-model="dialogVisible" class="admin-dialog" :title="editingId ? '编辑项目' : '新建项目'" width="520px">
      <el-form label-width="90px">
        <el-form-item label="名称">
          <el-input v-model="form.name" placeholder="项目名称" />
        </el-form-item>
        <el-form-item label="芯片">
          <el-input v-model="form.chip" placeholder="如 ATS3607" />
        </el-form-item>
        <el-form-item label="固件">
          <el-input v-model="form.firmware" placeholder="固件版本" />
        </el-form-item>
        <el-form-item label="设备类型">
          <el-input v-model="form.device_type" placeholder="如 车机 / 记录仪" />
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="form.description" type="textarea" :rows="3" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="submit">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { adminApi, type ProjectInfo } from '@/api/admin'

const items = ref<ProjectInfo[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = 20
const loading = ref(false)
const saving = ref(false)

const dialogVisible = ref(false)
const editingId = ref<number | null>(null)
const form = reactive({ name: '', chip: '', firmware: '', device_type: '', description: '' })

function formatTime(value?: string | null) {
  if (!value) return '—'
  const d = new Date(value)
  return Number.isNaN(d.getTime()) ? value : d.toLocaleString('zh-CN', { hour12: false })
}

async function fetch() {
  loading.value = true
  try {
    const { data } = await adminApi.listProjects({ page: page.value, page_size: pageSize })
    items.value = data.items || []
    total.value = data.total || 0
  } catch (e: any) {
    ElMessage.error('加载项目失败: ' + (e?.response?.data?.detail || e?.message))
  } finally {
    loading.value = false
  }
}

function resetForm() {
  form.name = ''
  form.chip = ''
  form.firmware = ''
  form.device_type = ''
  form.description = ''
}

function openCreate() {
  editingId.value = null
  resetForm()
  dialogVisible.value = true
}

function openEdit(row: ProjectInfo) {
  editingId.value = row.id
  form.name = row.name || ''
  form.chip = row.chip || ''
  form.firmware = row.firmware || ''
  form.device_type = row.device_type || ''
  form.description = row.description || ''
  dialogVisible.value = true
}

async function submit() {
  if (!form.name.trim()) {
    ElMessage.warning('请填写项目名称')
    return
  }
  saving.value = true
  try {
    const payload = {
      name: form.name.trim(),
      chip: form.chip || undefined,
      firmware: form.firmware || undefined,
      device_type: form.device_type || undefined,
      description: form.description || undefined,
    }
    if (editingId.value) {
      await adminApi.updateProject(editingId.value, payload)
      ElMessage.success('项目已更新')
    } else {
      await adminApi.createProject(payload)
      ElMessage.success('项目已创建')
    }
    dialogVisible.value = false
    await fetch()
  } catch (e: any) {
    ElMessage.error('保存失败: ' + (e?.response?.data?.detail || e?.message))
  } finally {
    saving.value = false
  }
}

async function remove(row: ProjectInfo) {
  try {
    await ElMessageBox.confirm(`确定删除项目「${row.name}」？`, '确认删除', {
      type: 'warning',
      confirmButtonText: '删除',
      cancelButtonText: '取消',
    })
    await adminApi.deleteProject(row.id)
    ElMessage.success('项目已删除')
    await fetch()
  } catch { /* cancelled or failed */ }
}

onMounted(fetch)
</script>

<style scoped>
.admin-page {
  max-width: 1200px;
}
.page-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
}
.page-title {
  font-size: 20px;
  font-weight: 600;
  color: var(--chat-layout-text);
  margin: 0;
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
</style>
