<template>
  <div class="admin-page">
    <div class="page-header">
      <h2 class="page-title">组织与成员</h2>
      <el-button type="primary" @click="openCreate">新建组织</el-button>
    </div>

    <el-table :data="items" stripe v-loading="loading">
      <el-table-column prop="id" label="ID" width="80" />
      <el-table-column prop="name" label="组织名称" min-width="200" />
      <el-table-column label="负责人" width="120">
        <template #default="{ row }">{{ row.owner_id ?? '—' }}</template>
      </el-table-column>
      <el-table-column label="创建时间" width="180">
        <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
      </el-table-column>
      <el-table-column label="操作" width="120">
        <template #default="{ row }">
          <el-button link type="primary" size="small" @click="openMembers(row)">成员</el-button>
        </template>
      </el-table-column>
      <template #empty>
        <div class="empty-hint">暂无组织</div>
      </template>
    </el-table>

    <el-dialog v-model="createVisible" class="admin-dialog" title="新建组织" width="440px">
      <el-form label-width="90px">
        <el-form-item label="名称">
          <el-input v-model="createForm.name" placeholder="组织名称" />
        </el-form-item>
        <el-form-item label="负责人ID">
          <el-input-number v-model="createForm.owner_id" :min="1" style="width:100%" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="createVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="submitCreate">创建</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="membersVisible" class="admin-dialog" :title="`成员 · ${currentOrg?.name || ''}`" width="640px">
      <div class="member-add">
        <el-input-number v-model="memberForm.user_id" :min="1" style="width:160px" />
        <el-select v-model="memberForm.role" style="width:140px">
          <el-option label="管理员" value="admin" />
          <el-option label="工程师" value="engineer" />
          <el-option label="只读" value="viewer" />
        </el-select>
        <el-button type="primary" :loading="saving" @click="submitMember">添加成员</el-button>
      </div>
      <el-table :data="members" stripe class="member-table">
        <el-table-column prop="user_id" label="用户ID" width="100" />
        <el-table-column prop="role" label="角色" width="120" />
        <el-table-column label="加入时间">
          <template #default="{ row }">{{ formatTime(row.joined_at) }}</template>
        </el-table-column>
        <template #empty>
          <div class="empty-hint">暂无成员</div>
        </template>
      </el-table>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { adminApi, type OrganizationInfo, type OrganizationMemberInfo } from '@/api/admin'

const items = ref<OrganizationInfo[]>([])
const loading = ref(false)
const saving = ref(false)

const createVisible = ref(false)
const createForm = reactive({ name: '', owner_id: 1 })

const membersVisible = ref(false)
const currentOrg = ref<OrganizationInfo | null>(null)
const members = ref<OrganizationMemberInfo[]>([])
const memberForm = reactive({ user_id: 1, role: 'engineer' })

function formatTime(value?: string | null) {
  if (!value) return '—'
  const d = new Date(value)
  return Number.isNaN(d.getTime()) ? value : d.toLocaleString('zh-CN', { hour12: false })
}

async function fetch() {
  loading.value = true
  try {
    const { data } = await adminApi.listOrganizations()
    items.value = Array.isArray(data) ? data : []
  } catch (e: any) {
    ElMessage.error('加载组织失败: ' + (e?.response?.data?.detail || e?.message))
  } finally {
    loading.value = false
  }
}

function openCreate() {
  createForm.name = ''
  createForm.owner_id = 1
  createVisible.value = true
}

async function submitCreate() {
  if (!createForm.name.trim()) {
    ElMessage.warning('请填写组织名称')
    return
  }
  saving.value = true
  try {
    await adminApi.createOrganization({ name: createForm.name.trim(), owner_id: createForm.owner_id })
    ElMessage.success('组织已创建')
    createVisible.value = false
    await fetch()
  } catch (e: any) {
    ElMessage.error('创建失败: ' + (e?.response?.data?.detail || e?.message))
  } finally {
    saving.value = false
  }
}

async function openMembers(org: OrganizationInfo) {
  currentOrg.value = org
  membersVisible.value = true
  members.value = []
  try {
    const { data } = await adminApi.listOrganizationMembers(org.id)
    members.value = Array.isArray(data) ? data : []
  } catch (e: any) {
    ElMessage.error('加载成员失败: ' + (e?.response?.data?.detail || e?.message))
  }
}

async function submitMember() {
  if (!currentOrg.value) return
  saving.value = true
  try {
    await adminApi.addOrganizationMember(currentOrg.value.id, {
      user_id: memberForm.user_id,
      role: memberForm.role,
    })
    ElMessage.success('成员已添加')
    await openMembers(currentOrg.value)
  } catch (e: any) {
    ElMessage.error('添加失败: ' + (e?.response?.data?.detail || e?.message))
  } finally {
    saving.value = false
  }
}

onMounted(fetch)
</script>

<style scoped>
.admin-page {
  max-width: 1100px;
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
.empty-hint {
  padding: 24px;
  text-align: center;
  color: var(--chat-copy-text);
  font-size: 13px;
}
.member-add {
  display: flex;
  align-items: center;
  gap: 12px;
}
.member-table {
  margin-top: 12px;
}
</style>
