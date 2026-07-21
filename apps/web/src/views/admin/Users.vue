<template>
  <div class="users-page">
    <h2 class="page-title">用户与角色管理</h2>

    <!-- 筛选栏 -->
    <div class="users-toolbar">
      <el-select v-model="filterRole" placeholder="角色筛选" clearable style="width:140px" @change="fetchUsers">
        <el-option label="管理员" value="admin" />
        <el-option label="工程师" value="engineer" />
        <el-option label="查看者" value="viewer" />
      </el-select>
      <el-select v-model="filterActive" placeholder="状态筛选" clearable style="width:140px" @change="fetchUsers">
        <el-option label="已启用" :value="true" />
        <el-option label="已禁用" :value="false" />
      </el-select>
      <div style="margin-left:auto;font-size:13px;color:#6b7280">共 {{ total }} 个用户</div>
    </div>

    <!-- 用户表格 -->
    <div class="users-table-wrap">
      <el-table :data="users" stripe v-loading="loading">
        <el-table-column prop="id" label="ID" width="60" />
        <el-table-column prop="username" label="用户名" min-width="120" />
        <el-table-column prop="email" label="邮箱" min-width="160"><template #default="{ row }">{{ row.email || '—' }}</template></el-table-column>
        <el-table-column prop="role" label="角色" width="120">
          <template #default="{ row }">
            <el-select :model-value="row.role" size="small" style="width:100px" @change="(v: string) => updateField(row.id, 'role', v)">
              <el-option label="管理员" value="admin" />
              <el-option label="工程师" value="engineer" />
              <el-option label="查看者" value="viewer" />
            </el-select>
          </template>
        </el-table-column>
        <el-table-column prop="is_active" label="状态" width="80">
          <template #default="{ row }">
            <el-switch :model-value="row.is_active" size="small" @change="(v: boolean) => updateField(row.id, 'is_active', v)" />
          </template>
        </el-table-column>
        <el-table-column prop="created_at" label="注册时间" width="170">
          <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
        </el-table-column>
      </el-table>
    </div>

    <el-pagination
      v-if="total > pageSize"
      style="margin-top:16px;justify-content:center"
      background layout="prev,pager,next"
      :total="total" :page-size="pageSize"
      v-model:current-page="page" @change="fetchUsers"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { adminApi, UserInfo } from '@/api/admin'
import { ElMessage } from 'element-plus'

const users = ref<UserInfo[]>([])
const loading = ref(false)
const page = ref(1)
const pageSize = 20
const total = ref(0)
const filterRole = ref('')
const filterActive = ref<boolean | ''>('')

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

async function fetchUsers() {
  loading.value = true
  try {
    const params: any = { page: page.value, page_size: pageSize }
    if (filterRole.value) params.role = filterRole.value
    if (filterActive.value !== '') params.is_active = filterActive.value
    const { data } = await adminApi.listUsers(params)
    users.value = data
    total.value = data.length >= pageSize ? page.value * pageSize + 1 : page.value * pageSize
  } catch { /* ignore */ } finally { loading.value = false }
}

async function updateField(userId: number, field: string, value: any) {
  try {
    await adminApi.updateUser(userId, { [field]: value })
    // 更新本地数据
    const user = users.value.find(u => u.id === userId)
    if (user) (user as any)[field] = value
    ElMessage.success('已更新')
  } catch { ElMessage.error('更新失败') }
}

onMounted(fetchUsers)
</script>

<style scoped>
.page-title { font-size: 20px; font-weight: 600; color: #1f2937; margin: 0 0 20px; }
.users-toolbar { display: flex; align-items: center; gap: 12px; margin-bottom: 16px; }
.users-table-wrap { background: #fff; border: 1px solid #e5e7eb; border-radius: 10px; overflow: hidden; }
</style>
