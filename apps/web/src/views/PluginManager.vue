<template>
  <div class="page-container">
    <div class="card-header"><h2>插件管理</h2></div>
    <el-card>
      <el-table :data="plugins" stripe v-loading="loading">
        <el-table-column prop="name" label="名称" min-width="160" />
        <el-table-column prop="type" label="类型" width="100" />
        <el-table-column prop="status" label="状态" width="100"><template #default="{ row }"><el-tag size="small" :type="row.status === 'running' ? 'success' : 'warning'">{{ row.status }}</el-tag></template></el-table-column>
        <el-table-column prop="description" label="描述" show-overflow-tooltip />
        <el-table-column label="操作" width="140">
          <template #default="{ row }">
            <el-button size="small" :type="row.status === 'running' ? 'warning' : 'success'" @click="toggle(row)">
              {{ row.status === 'running' ? '禁用' : '启用' }}
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import client from '@/api/client'
import { ElMessage } from 'element-plus'

const plugins = ref<any[]>([])
const loading = ref(false)

async function fetch() {
  loading.value = true
  try {
    const { data } = await client.get('/plugins')
    const byType = data.plugins || {}
    const flat: any[] = []
    for (const [type, items] of Object.entries(byType)) {
      for (const item of items as any[]) {
        flat.push({ ...item, type })
      }
    }
    plugins.value = flat
  } catch { /* 后端未连接 */ }
  finally { loading.value = false }
}

function toggle(row: any) {
  ElMessage.info('插件管理功能开发中')
}

onMounted(fetch)
</script>
