<template>
  <div class="users-page">
    <h2 class="page-title">用户管理</h2>

    <!-- 工具栏 -->
    <div class="users-toolbar">
      <el-input v-model="searchText" placeholder="搜索用户名..." clearable style="width:240px" @clear="doSearch" @keyup.enter="doSearch">
        <template #prefix><el-icon><Search /></el-icon></template>
      </el-input>
      <el-button type="primary" @click="openCreate">新增用户</el-button>
      <div class="toolbar-total">共 {{ total }} 个用户</div>
    </div>

    <!-- 用户表格 -->
    <div class="users-table-wrap">
      <el-table :data="users" stripe v-loading="loading">
        <el-table-column prop="id" label="ID" width="70" />
        <el-table-column prop="username" label="用户名" width="140" />
        <el-table-column prop="organization" label="企业/单位" min-width="160">
          <template #default="{ row }">{{ row.organization || '—' }}</template>
        </el-table-column>
        <el-table-column prop="role" label="角色" width="90">
          <template #default="{ row }">{{ roleLabel(row.role) }}</template>
        </el-table-column>
        <el-table-column prop="is_active" label="状态" width="80">
          <template #default="{ row }">
            <el-tag :type="row.is_active ? 'success' : 'info'" size="small">{{ row.is_active ? '启用' : '禁用' }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="created_at" label="创建时间" width="180">
          <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="70" fixed="right">
          <template #default="{ row }">
            <el-dropdown trigger="click" @command="(cmd: string) => handleRowAction(cmd, row)">
              <button class="row-more-btn">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="5" r="1"/><circle cx="12" cy="12" r="1"/><circle cx="12" cy="19" r="1"/></svg>
              </button>
              <template #dropdown>
                <el-dropdown-menu>
                  <el-dropdown-item command="edit">✏️ 编辑</el-dropdown-item>
                  <el-dropdown-item v-if="isDeveloper" command="delete" divided style="color:#ef4444">🗑️ 删除</el-dropdown-item>
                </el-dropdown-menu>
              </template>
            </el-dropdown>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <!-- 分页 -->
    <el-pagination
      v-if="total > pageSize"
      style="margin-top:16px;justify-content:center"
      background layout="prev,pager,next"
      :total="total" :page-size="pageSize"
      v-model:current-page="page" @change="fetchUsers"
    />

    <!-- 新增 / 编辑 弹窗（共用） -->
    <el-dialog
      v-model="dialogVisible"
      :title="dialogMode === 'create' ? '新增用户' : '编辑用户'"
      width="480px"
      :key="dialogMode + '-' + (editingUserId ?? 'new')"
      destroy-on-close
    >
      <el-form label-width="80px">
        <el-form-item label="用户名" required>
          <el-input v-model="form.username" placeholder="3-50 字符" maxlength="50" :disabled="dialogMode === 'edit'" />
        </el-form-item>
        <el-form-item label="密码" :required="dialogMode === 'create'">
          <div style="width:100%">
            <div style="display:flex;gap:8px">
              <el-input v-model="form.password" type="password" show-password :placeholder="dialogMode === 'create' ? '至少12位，含大小写字母+数字+特殊字符' : '留空则不修改密码'" maxlength="128" style="flex:1" />
              <el-button v-if="dialogMode === 'create'" @click="generatePassword" :loading="generatingPwd">随机生成</el-button>
            </div>
          </div>
        </el-form-item>
        <el-form-item label="角色" required>
          <el-select v-model="form.role" style="width:100%">
            <el-option label="开发" value="developer" />
            <el-option label="管理员" value="admin" />
            <el-option label="用户" value="user" />
          </el-select>
        </el-form-item>
        <el-form-item label="企业/单位">
          <el-input v-model="form.organization" placeholder="选填" maxlength="100" />
        </el-form-item>
        <el-form-item label="状态">
          <el-switch v-model="form.is_active" active-text="启用" inactive-text="禁用" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="handleSubmit">{{ dialogMode === 'create' ? '创建' : '保存' }}</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { adminApi, UserInfo } from '@/api/admin'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Search } from '@element-plus/icons-vue'
import { useUserStore } from '@/stores/user'

const userStore = useUserStore()
const isDeveloper = computed(() => userStore.user?.role === 'developer')

const users = ref<UserInfo[]>([])
const loading = ref(false)
const page = ref(1)
const pageSize = 20
const total = ref(0)
const searchText = ref('')

// Dialog — 新增和编辑共用
const dialogVisible = ref(false)
const dialogMode = ref<'create' | 'edit'>('create')
const editingUserId = ref<number | null>(null)
const submitting = ref(false)
const generatingPwd = ref(false)
const form = ref({ username: '', password: '', role: 'user', organization: '', is_active: true })

function roleLabel(r: string) {
  if (r === 'developer') return '开发'
  if (r === 'admin') return '管理员'
  if (r === 'user') return '用户'
  return r
}

function generatePassword() {
  generatingPwd.value = true
  const upper = 'ABCDEFGHJKLMNPQRSTUVWXYZ'
  const lower = 'abcdefghjkmnpqrstuvwxyz'
  const digits = '23456789'
  const special = '!@#$%&*_+-='
  const all = upper + lower + digits + special
  const parts = [
    upper[Math.floor(Math.random() * upper.length)],
    lower[Math.floor(Math.random() * lower.length)],
    digits[Math.floor(Math.random() * digits.length)],
    special[Math.floor(Math.random() * special.length)],
  ]
  for (let i = 0; i < 8; i++) {
    parts.push(all[Math.floor(Math.random() * all.length)])
  }
  for (let i = parts.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [parts[i], parts[j]] = [parts[j], parts[i]]
  }
  form.value.password = parts.join('')
  generatingPwd.value = false
}

function openCreate() {
  dialogMode.value = 'create'
  editingUserId.value = null
  form.value = { username: '', password: '', role: 'user', organization: '', is_active: true }
  dialogVisible.value = true
}

function openEdit(row: UserInfo) {
  dialogMode.value = 'edit'
  editingUserId.value = row.id
  form.value = {
    username: row.username,
    password: '',
    role: row.role,
    organization: row.organization || '',
    is_active: row.is_active,
  }
  dialogVisible.value = true
}

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
    if (searchText.value) params.search = searchText.value
    const { data } = await adminApi.listUsers(params)
    users.value = data.items
    total.value = data.total
  } catch {} finally { loading.value = false }
}

function doSearch() { page.value = 1; fetchUsers() }

function handleRowAction(cmd: string, row: UserInfo) {
  if (cmd === 'edit') {
    openEdit(row)
  } else if (cmd === 'delete') {
    handleDelete(row)
  }
}

async function handleSubmit() {
  if (!form.value.username.trim()) { ElMessage.warning('请输入用户名'); return }

  if (dialogMode.value === 'create') {
    if (!form.value.password) { ElMessage.warning('请输入密码'); return }
    if (form.value.password.length < 12) { ElMessage.warning('密码至少12位'); return }
  }

  submitting.value = true
  try {
    if (dialogMode.value === 'create') {
      await adminApi.createUser({
        username: form.value.username,
        password: form.value.password,
        role: form.value.role,
        organization: form.value.organization || undefined,
        is_active: form.value.is_active,
      })
      ElMessage.success('用户创建成功')
    } else {
      const updateData: Record<string, any> = {
        role: form.value.role,
        organization: form.value.organization || null,
        is_active: form.value.is_active,
      }
      if (form.value.password) {
        // 编辑模式下输入了新密码才更新
        updateData.password = form.value.password
      }
      await adminApi.updateUser(editingUserId.value!, updateData)
      ElMessage.success('已保存')
    }
    dialogVisible.value = false
    fetchUsers()
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail || '操作失败')
  } finally { submitting.value = false }
}

async function handleDelete(row: UserInfo) {
  try {
    await ElMessageBox.confirm(`确定删除用户「${row.username}」？此操作不可恢复。`, '确认删除', { type: 'warning' })
  } catch { return }
  try {
    await adminApi.deleteUser(row.id)
    ElMessage.success('已删除')
    fetchUsers()
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail || '删除失败')
  }
}

onMounted(fetchUsers)
</script>

<style scoped>
.page-title { font-size: 20px; font-weight: 600; color: #1f2937; margin: 0 0 20px; }

.users-toolbar { display: flex; align-items: center; gap: 12px; margin-bottom: 16px; }
.toolbar-total { margin-left: auto; font-size: 13px; color: #6b7280; }

.users-table-wrap { background: #fff; border: 1px solid #e5e7eb; border-radius: 10px; overflow: hidden; }

/* 更多按钮 */
.row-more-btn { width: 28px; height: 28px; border-radius: 6px; border: none; background: transparent; color: #9ca3af; cursor: pointer; display: flex; align-items: center; justify-content: center; transition: background 0.12s; }
.row-more-btn:hover { background: #e5e7eb; color: #374151; }
</style>
