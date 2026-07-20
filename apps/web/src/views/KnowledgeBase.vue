<template>
  <div class="page-container">
    <div class="card-header"><h2>知识库</h2><el-button type="primary" @click="showCreate = true">添加文档</el-button></div>

    <el-row :gutter="16" style="margin-bottom:16px">
      <el-col :span="6"><el-input v-model="searchQuery" placeholder="搜索关键词..." clearable @clear="fetch" @keyup.enter="doSearch" /></el-col>
      <el-col :span="4"><el-select v-model="filterCategory" placeholder="分类筛选" clearable @change="fetch"><el-option v-for="c in categories" :key="c" :label="c" :value="c" /></el-select></el-col>
      <el-col :span="3"><el-button @click="doSearch" :icon="'Search'">搜索</el-button></el-col>
    </el-row>

    <el-card>
      <el-table :data="items" stripe v-loading="loading">
        <el-table-column prop="title" label="标题" min-width="200" />
        <el-table-column prop="category" label="分类" width="120" />
        <el-table-column prop="doc_type" label="类型" width="100" />
        <el-table-column prop="status" label="状态" width="100"><template #default="{ row }"><el-tag size="small">{{ row.status }}</el-tag></template></el-table-column>
        <el-table-column prop="created_at" label="时间" width="180"><template #default="{ row }">{{ formatTime(row.created_at) }}</template></el-table-column>
        <el-table-column label="操作" width="200">
          <template #default="{ row }">
            <el-button size="small" @click="edit(row)">编辑</el-button>
            <el-button size="small" type="danger" @click="remove(row.id)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
      <el-pagination v-if="total > pageSize" style="margin-top:16px;justify-content:center" background layout="prev,pager,next" :total="total" :page-size="pageSize" v-model:current-page="page" @change="fetch" />
    </el-card>

    <el-dialog v-model="showCreate" :title="editingId ? '编辑文档' : '新建文档'" width="600px" @closed="resetForm">
      <el-form label-position="top">
        <el-form-item label="标题"><el-input v-model="form.title" /></el-form-item>
        <el-form-item label="分类"><el-input v-model="form.category" placeholder="如：usb, kernel, bluetooth" /></el-form-item>
        <el-form-item label="类型"><el-select v-model="form.doc_type"><el-option label="手册" value="manual" /><el-option label="常见问题" value="faq" /><el-option label="Bug报告" value="bug_report" /><el-option label="数据手册" value="datasheet" /></el-select></el-form-item>
        <el-form-item label="内容"><el-input v-model="form.content" type="textarea" :rows="8" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showCreate = false">取消</el-button>
        <el-button type="primary" @click="save" :loading="saving">{{ editingId ? '更新' : '创建' }}</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { knowledgeApi } from '@/api/knowledge'
import { ElMessage } from 'element-plus'

const items = ref<any[]>([])
const categories = ref<string[]>([])
const loading = ref(false)
const saving = ref(false)
const showCreate = ref(false)
const editingId = ref<number | null>(null)
const page = ref(1)
const pageSize = 20
const total = ref(0)
const searchQuery = ref('')
const filterCategory = ref('')
const form = ref({ title: '', category: '', doc_type: 'manual', content: '' })

function formatTime(ts: string) { return ts ? new Date(ts).toLocaleString() : '' }
function resetForm() { editingId.value = null; form.value = { title: '', category: '', doc_type: 'manual', content: '' } }
function edit(row: any) { editingId.value = row.id; form.value = { title: row.title, category: row.category || '', doc_type: row.doc_type, content: row.content }; showCreate.value = true }

async function fetch() {
  loading.value = true
  try {
    const { data } = await knowledgeApi.list({ page: page.value, page_size: pageSize, category: filterCategory.value || undefined })
    items.value = data.items; total.value = data.total
    const catResp = await knowledgeApi.categories(); categories.value = catResp.data
  } catch {}
  finally { loading.value = false }
}

async function doSearch() {
  if (!searchQuery.value.trim()) { await fetch(); return }
  loading.value = true
  try { const { data } = await knowledgeApi.search(searchQuery.value, { page: page.value, page_size: pageSize }); items.value = data.items; total.value = data.total } catch {}
  finally { loading.value = false }
}

async function save() {
  saving.value = true
  try {
    if (editingId.value) { await knowledgeApi.update(editingId.value, form.value); ElMessage.success('更新成功') }
    else { await knowledgeApi.create(form.value); ElMessage.success('创建成功') }
    showCreate.value = false; resetForm(); await fetch()
  } catch (e: any) { ElMessage.error(e.response?.data?.detail || '保存失败') }
  finally { saving.value = false }
}

async function remove(id: number) { try { await knowledgeApi.delete(id); await fetch(); ElMessage.success('已删除') } catch { ElMessage.error('删除失败') } }

onMounted(fetch)
</script>
