<template>
  <div class="kb-container" :class="{ 'kb-full': viewState === 'edit' }">
    <!-- ============================================================ -->
    <!-- 面包屑（所有视图，替代标题） -->
    <!-- ============================================================ -->
    <div class="kb-breadcrumb">
      <el-breadcrumb separator="/">
        <el-breadcrumb-item>
          <a @click="backToList" style="cursor:pointer;font-size:20px;font-weight:600;color:#1f2937;text-decoration:none">知识库</a>
        </el-breadcrumb-item>
        <!-- 文件夹路径链（所有视图下都可点击跳转） -->
        <el-breadcrumb-item v-for="(f, i) in folderPath" :key="f.id" style="font-size:20px;font-weight:600;color:#1f2937">
          <a @click="navigateToFolder(i)" style="cursor:pointer;color:#2563eb;text-decoration:none">{{ f.title }}</a>
        </el-breadcrumb-item>
        <!-- 当前文件 -->
        <el-breadcrumb-item v-if="viewState === 'preview'" style="font-size:20px;font-weight:600;color:#1f2937">{{ form.title }}</el-breadcrumb-item>
        <el-breadcrumb-item v-if="viewState === 'edit'" style="font-size:20px;font-weight:600;color:#1f2937">{{ editingId ? form.title : '新建笔记' }}</el-breadcrumb-item>
      </el-breadcrumb>
    </div>

    <!-- ============================================================ -->
    <!-- 列表视图 — 无重复标题 -->
    <!-- ============================================================ -->
    <template v-if="viewState === 'list'">
      <div class="kb-header">
        <div></div>
        <div class="kb-header-right">
          <el-input v-model="searchQuery" placeholder="搜索文件..." class="kb-search" clearable @clear="doSearch" @keyup.enter="doSearch" :prefix-icon="Search" />
          <el-dropdown @command="handleCreateCommand" trigger="click">
            <el-button type="primary">新建</el-button>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item command="upload">📁 上传文件</el-dropdown-item>
                <el-dropdown-item command="folder">📂 新建文件夹</el-dropdown-item>
                <el-dropdown-item command="note">📝 新建笔记</el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </div>
      </div>

      <div class="kb-toolbar">
        <div class="toolbar-left">
          <el-select v-model="filterCategory" placeholder="分类筛选" clearable style="width:160px" @change="fetch">
            <el-option v-for="c in categories" :key="c" :label="c" :value="c" />
          </el-select>
        </div>
        <div class="toolbar-right">
          <el-button-group class="view-toggle">
            <el-button :type="viewMode === 'list' ? 'primary' : ''" @click="viewMode = 'list'">☰ 列表</el-button>
            <el-button :type="viewMode === 'grid' ? 'primary' : ''" @click="viewMode = 'grid'">⊞ 网格</el-button>
          </el-button-group>
          <el-dropdown @command="handleSort" trigger="click">
            <el-button>排序 ▾</el-button>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item command="updated_desc">按更新时间 ↓</el-dropdown-item>
                <el-dropdown-item command="updated_asc">按更新时间 ↑</el-dropdown-item>
                <el-dropdown-item command="created_desc">按创建时间 ↓</el-dropdown-item>
                <el-dropdown-item command="created_asc">按创建时间 ↑</el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </div>
      </div>

      <!-- 空状态 -->
      <div v-if="!loading && items.length === 0" class="kb-empty">
        <div class="empty-icon">📂</div>
        <div class="empty-title">{{ currentFolder ? '此文件夹为空' : '知识库为空' }}</div>
        <div class="empty-desc">{{ currentFolder ? '点击"新建"添加内容' : '点击"新建"开始创建文档或上传文件' }}</div>
      </div>

      <!-- 列表 -->
      <div v-else-if="viewMode === 'list'" class="kb-table-wrap" v-loading="loading">
        <el-table :data="items" stripe @selection-change="handleSelection">
          <el-table-column type="selection" width="40" />
          <el-table-column prop="title" label="名称" min-width="220">
            <template #default="{ row }">
              <div class="cell-name">
                <span class="file-icon">{{ row.doc_type === 'note' ? '📝' : row.doc_type === 'folder' ? '📂' : '📄' }}</span>
                <span class="file-title" @click="openItem(row)" style="cursor:pointer;color:#2563eb">{{ row.title }}</span>
              </div>
            </template>
          </el-table-column>
          <el-table-column prop="category" label="修改人" width="120"><template #default="{ row }">{{ row.category || '—' }}</template></el-table-column>
          <el-table-column label="管理人" width="120"><template #default>{ row }}{{ '—' }}</template></el-table-column>
          <el-table-column prop="updated_at" label="修改时间" width="180"><template #default="{ row }">{{ formatTime(row.updated_at || row.created_at) }}</template></el-table-column>
          <el-table-column label="大小" width="100"><template #default="{ row }">{{ formatSize(row) }}</template></el-table-column>
          <!-- 更多菜单 -->
          <el-table-column label="" width="60" fixed="right">
            <template #default="{ row }">
              <el-dropdown trigger="click" @command="(cmd: string) => handleRowAction(cmd, row)">
                <button class="row-more-btn">
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="5" r="1"/><circle cx="12" cy="12" r="1"/><circle cx="12" cy="19" r="1"/></svg>
                </button>
                <template #dropdown>
                  <el-dropdown-menu>
                    <el-dropdown-item v-if="row.doc_type !== 'folder'" command="edit">✏️ 编辑</el-dropdown-item>
                    <el-dropdown-item command="rename">✏️ 重命名</el-dropdown-item>
                    <el-dropdown-item command="pin">📌 置顶</el-dropdown-item>
                    <el-dropdown-item command="delete" divided style="color:#ef4444">🗑️ 删除</el-dropdown-item>
                  </el-dropdown-menu>
                </template>
              </el-dropdown>
            </template>
          </el-table-column>
        </el-table>
        <el-pagination v-if="total > pageSize" style="margin-top:16px;justify-content:center" background layout="prev,pager,next" :total="total" :page-size="pageSize" v-model:current-page="page" @change="fetch" />
      </div>

      <!-- 网格 -->
      <div v-else class="kb-grid" v-loading="loading">
        <div v-for="item in items" :key="item.id" class="kb-card" @click="openItem(item)">
          <div class="card-icon">{{ item.doc_type === 'note' ? '📝' : item.doc_type === 'folder' ? '📂' : '📄' }}</div>
          <div class="card-title">{{ item.title }}</div>
          <div class="card-meta">{{ formatTime(item.updated_at || item.created_at) }}</div>
        </div>
        <el-pagination v-if="total > pageSize" style="margin-top:16px;justify-content:center;width:100%" background layout="prev,pager,next" :total="total" :page-size="pageSize" v-model:current-page="page" @change="fetch" />
      </div>
    </template>

    <!-- ============================================================ -->
    <!-- 预览视图 — 左侧目录 + 右侧 v-md-preview -->
    <!-- ============================================================ -->
    <div v-else-if="viewState === 'preview'" class="kb-preview-page">
      <div class="preview-header">
        <div class="preview-header-left">
          <span class="preview-header-title">{{ form.title }}</span>
        </div>
        <div class="preview-header-right">
          <el-button @click="viewState = 'list'">返回列表</el-button>
          <el-button type="primary" @click="enterEdit">编辑</el-button>
        </div>
      </div>
      <div class="preview-layout">
        <!-- 左侧目录 -->
        <aside class="preview-sidebar">
          <div class="sidebar-section sidebar-toc">
            <div class="section-header">
              <span class="section-title">📑 目录</span>
            </div>
            <div class="toc-body">
              <template v-if="tocItems.length">
                <div
                  v-for="(item, i) in tocItems"
                  :key="i"
                  class="toc-item"
                  :style="{ paddingLeft: (item.level - 1) * 14 + 8 + 'px' }"
                  :class="{ 'toc-active': item.level === 1 }"
                  @click="scrollToTocAnchor(item.anchorId)"
                >{{ item.text }}</div>
              </template>
              <div v-else class="toc-empty">暂无标题</div>
            </div>
          </div>
        </aside>
        <!-- 右侧预览 -->
        <div class="preview-body">
          <component :is="VMdEditor.Preview" :text="form.content" />
        </div>
      </div>
    </div>

    <!-- ============================================================ -->
    <!-- 编辑视图 -->
    <!-- ============================================================ -->
    <div v-else-if="viewState === 'edit'" class="kb-editor-page">
      <div class="kb-header">
        <el-input v-model="form.title" placeholder="笔记标题" style="width:300px;font-size:18px;font-weight:600" />
        <el-input v-model="form.category" placeholder="分类（可选）" style="width:200px;margin-left:8px" />
        <div style="margin-left:auto;display:flex;gap:8px">
          <el-button @click="cancelEdit">取消</el-button>
          <el-button type="primary" @click="save" :loading="saving">{{ editingId ? '保存' : '创建' }}</el-button>
        </div>
      </div>
      <div class="editor-body">
        <v-md-editor ref="editorRef" v-model="form.content" height="100%" left-toolbar="undo redo | bold italic strikethrough | h2 h3 h4 | ul ol | link image | code quote | table hr | fullscreen" :disabled-menus="[]" @upload-image="handleUploadImage" />
      </div>
    </div>

    <!-- ============================================================ -->
    <!-- 弹窗 -->
    <!-- ============================================================ -->
    <el-dialog v-model="showUpload" title="上传文件" width="480px">
      <el-upload drag :auto-upload="false" :on-change="handleFileSelect" accept=".md,.txt,.pdf">
        <el-icon :size="40"><UploadFilled /></el-icon>
        <div style="margin-top:8px">拖拽文件或点击上传</div>
        <template #tip><div style="margin-top:8px;color:#909399">支持 .md, .txt, .pdf</div></template>
      </el-upload>
      <div style="margin-top:12px">
        <el-input v-model="uploadForm.category" placeholder="分类（可选）" style="margin-bottom:8px" />
        <el-select v-model="uploadForm.doc_type" style="width:100%">
          <el-option label="手册" value="manual" /><el-option label="FAQ" value="faq" /><el-option label="数据手册" value="datasheet" />
        </el-select>
      </div>
      <template #footer><el-button @click="showUpload = false">取消</el-button><el-button type="primary" @click="doUpload" :loading="uploading">上传</el-button></template>
    </el-dialog>

    <el-dialog v-model="showFolder" title="新建文件夹" width="400px">
      <el-input v-model="folderName" placeholder="文件夹名称" />
      <template #footer><el-button @click="showFolder = false">取消</el-button><el-button type="primary" @click="createFolder">创建</el-button></template>
    </el-dialog>

    <el-dialog v-model="showRename" title="重命名" width="400px">
      <el-input v-model="renameName" placeholder="新名称" />
      <template #footer><el-button @click="showRename = false">取消</el-button><el-button type="primary" @click="doRename">确认</el-button></template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount, computed, nextTick, defineComponent, h } from 'vue'
import { Search, UploadFilled } from '@element-plus/icons-vue'
import { knowledgeApi } from '@/api/knowledge'
import { ElMessage, ElMessageBox } from 'element-plus'
import VMdEditor from '@kangc/v-md-editor'
import '@kangc/v-md-editor/lib/style/base-editor.css'
import vuepressTheme from '@kangc/v-md-editor/lib/theme/vuepress.js'
import '@kangc/v-md-editor/lib/theme/style/vuepress.css'
import createCopyCodePlugin from '@kangc/v-md-editor/lib/plugins/copy-code/index'
import '@kangc/v-md-editor/lib/plugins/copy-code/copy-code.css'
import Prism from 'prismjs'
import 'prismjs/components/prism-python'
import 'prismjs/components/prism-javascript'
import 'prismjs/components/prism-typescript'
import 'prismjs/components/prism-bash'
import 'prismjs/components/prism-json'
import 'prismjs/components/prism-yaml'
import 'prismjs/components/prism-markdown'
import 'prismjs/components/prism-css'
import 'prismjs/components/prism-sql'

VMdEditor.use(vuepressTheme, { Prism })
VMdEditor.use(createCopyCodePlugin())

// ============================================================
// 树节点递归组件
// ============================================================
const TreeNodeItem = defineComponent({
  name: 'TreeNodeItem',
  props: {
    node: { type: Object, required: true },
    activeId: { type: Number, default: undefined },
    depth: { type: Number, default: 0 },
  },
  emits: ['select'],
  setup(props, { emit }) {
    const expanded = ref(props.depth < 2) // 默认展开前2层
    const hasChildren = computed(() => props.node.children && props.node.children.length > 0)
    const isFolder = computed(() => props.node.doc_type === 'folder')
    const isActive = computed(() => props.activeId === props.node.id)

    function toggle() { expanded.value = !expanded.value }
    function onSelect() { emit('select', props.node) }

    return () => {
      const children: any[] = []
      // 节点行
      children.push(h('div', {
        class: ['tree-node', { 'tree-node-active': isActive.value }],
        style: { paddingLeft: props.depth * 16 + 8 + 'px' },
        onClick: onSelect,
      }, [
        hasChildren.value
          ? h('span', { class: 'tree-arrow', onClick: (e: Event) => { e.stopPropagation(); toggle() } }, expanded.value ? '▾' : '▸')
          : h('span', { class: 'tree-arrow tree-arrow-empty' }),
        h('span', { class: 'tree-icon' }, isFolder.value ? '📂' : '📄'),
        h('span', { class: 'tree-label' }, props.node.title),
      ]))
      // 子节点
      if (hasChildren.value && expanded.value) {
        for (const child of props.node.children) {
          children.push(h(TreeNodeItem, {
            node: child,
            activeId: props.activeId,
            depth: props.depth + 1,
            onSelect: (n: any) => emit('select', n),
          }))
        }
      }
      return h('div', { class: 'tree-branch' }, children)
    }
  },
})

const items = ref<any[]>([])
const categories = ref<string[]>([])
const loading = ref(false)
const saving = ref(false)
const uploading = ref(false)
const page = ref(1)
const pageSize = 20
const total = ref(0)
const searchQuery = ref('')
const filterCategory = ref('')
const viewMode = ref<'list' | 'grid'>('list')
const sortOrder = ref('updated_desc')
const selectedRows = ref<any[]>([])

const showUpload = ref(false)
const showFolder = ref(false)
const showRename = ref(false)
const editingId = ref<number | null>(null)
const renameId = ref<number | null>(null)
const folderName = ref('')
const renameName = ref('')
const uploadForm = ref({ category: '', doc_type: 'manual' })
const uploadFile = ref<File | null>(null)
const form = ref({ title: '', category: '', doc_type: 'note', content: '' })

const viewState = ref<'list' | 'preview' | 'edit'>('list')
const currentFolder = ref<any>(null)
const folderPath = ref<any[]>([])  // 从根到当前文件夹的完整路径链
const editorRef = ref<any>(null)
const folderTree = ref<any[]>([])   // 知识库文件夹树

// 路径深度限制（Windows MAX_PATH = 260）
const MAX_PATH_LENGTH = 200
const folderDepth = ref(0)

// ============================================================
function formatTime(ts: string) {
  if (!ts) return ''
  const match = ts.match(/^(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2}):(\d{2})/)
  if (!match) return ts
  let Y = +match[1], M = +match[2], D = +match[3], h = +match[4], m = +match[5], s = +match[6]
  h += 8
  if (h >= 24) { h -= 24; D += 1 }
  const daysInMonth = new Date(Y, M, 0).getDate()
  if (D > daysInMonth) { D = 1; M += 1; if (M > 12) { M = 1; Y += 1 } }
  return `${Y}-${String(M).padStart(2,'0')}-${String(D).padStart(2,'0')} ${String(h).padStart(2,'0')}:${String(m).padStart(2,'0')}:${String(s).padStart(2,'0')}`
}
function formatSize(row: any) { if (row.doc_type === 'folder') return '—'; if (!row.content) return '—'; const bytes = new Blob([row.content]).size; return bytes < 1024 ? bytes + ' B' : (bytes / 1024).toFixed(1) + ' KB' }

// ============================================================
// Markdown TOC — 改为响应式数组（非 v-html）
// ============================================================
const tocItems = computed(() => {
  const c = form.value.content
  if (!c) return []
  const headings = c.split('\n').filter(l => /^#{1,3} /.test(l))
  return headings.map((h, i) => {
    const level = h.match(/^(#+)/)![0].length
    const text = h.replace(/^#+\s*/, '').replace(/\*\*(.+?)\*\*/g, '$1')
    return { level, text, anchorId: `toc-${i}` }
  })
})

function scrollToTocAnchor(anchorId: string) {
  const el = document.getElementById(anchorId)
  if (el) {
    el.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }
}

// 预览渲染后统一处理：注入标题锚点 + 替换图片短引用
function afterPreviewRender() {
  setTimeout(() => {
    const previewBody = document.querySelector('.preview-body') as HTMLElement | null
    if (!previewBody) return

    // 1. 给所有 h1/h2/h3 注入锚点 id，使目录点击跳转生效
    const headings = previewBody.querySelectorAll('h1, h2, h3')
    let idx = 0
    headings.forEach((el) => {
      el.id = `toc-${idx++}`
    })

    // 2. 替换图片短引用 #img-N → 真实 base64
    previewBody.querySelectorAll('img[src^="#img-"]').forEach((img) => {
      const id = (img as HTMLImageElement).getAttribute('src')?.replace('#', '')
      if (id && imageStore.has(id)) {
        (img as HTMLImageElement).src = imageStore.get(id)!
      }
    })
  }, 150)
}

// ============================================================
// 文件夹树加载
// ============================================================
async function loadTree() {
  try {
    const { data } = await knowledgeApi.tree()
    folderTree.value = data.tree || []
  } catch { /* ignore */ }
}

function selectTreeNode(node: any) {
  if (node.doc_type === 'folder') {
    // 文件夹 → 跳回列表视图并进入该文件夹
    viewState.value = 'list'
    // 需要从树中重建 folderPath
    rebuildPathToNode(node.id)
    currentFolder.value = node
    fetch()
  } else {
    // 文档 → 切换预览
    form.value = {
      title: node.title,
      category: node.category || '',
      doc_type: node.doc_type || 'note',
      content: '',  // 需要从后端获取完整内容
    }
    editingId.value = node.id
    viewState.value = 'preview'
    loadDocumentContent(node.id)
    nextTick(afterPreviewRender)
  }
}

async function loadDocumentContent(id: number) {
  try {
    const { data } = await knowledgeApi.get(id)
    form.value.content = data.content || ''
    nextTick(afterPreviewRender)
  } catch { /* ignore */ }
}

function rebuildPathToNode(targetId: number) {
  // 在 folderTree 中搜索目标节点的完整路径
  folderPath.value = []
  function search(nodes: any[], ancestors: any[]): boolean {
    for (const n of nodes) {
      const path = [...ancestors, n]
      if (n.id === targetId) {
        folderPath.value = path
        return true
      }
      if (n.children && n.children.length > 0) {
        if (search(n.children, path)) return true
      }
    }
    return false
  }
  search(folderTree.value, [])
}

// 路径深度检查
function checkPathDepth() {
  if (!currentFolder.value) { folderDepth.value = 0; return true }
  // 简化：通过 currentFolder 的名称长度估算深度
  // 实际场景中可以通过后端 parent_id 链查询
  let depth = 1
  let folder = currentFolder.value
  // 假设每个文件夹名称平均 20 字符
  const estimatedPath = folder.title.length + (folder.category ? folder.category.length : 0)
  if (estimatedPath > MAX_PATH_LENGTH - 50) {
    ElMessage.warning('路径深度已达上限，无法继续创建文件夹')
    return false
  }
  folderDepth.value = depth
  return true
}
async function fetch() {
  loading.value = true
  try {
    const params: any = { page: page.value, page_size: pageSize, category: filterCategory.value || undefined }
    if (currentFolder.value) params.parent_id = currentFolder.value.id
    const { data } = await knowledgeApi.list(params)
    items.value = data.items; total.value = data.total
    const catResp = await knowledgeApi.categories(); categories.value = catResp.data
  } catch {} finally { loading.value = false }
}
async function doSearch() {
  if (!searchQuery.value.trim()) { await fetch(); return }
  loading.value = true
  try { const { data } = await knowledgeApi.search(searchQuery.value, { page: page.value, page_size: pageSize }); items.value = data.items; total.value = data.total } catch {} finally { loading.value = false }
}

// ============================================================
// 导航 — 类似文件系统
// ============================================================
function backToList() { viewState.value = 'list'; currentFolder.value = null; folderPath.value = []; editingId.value = null; fetch() }
function cancelEdit() {
  // 取消编辑/预览：回到列表视图，但保留当前 folderPath
  viewState.value = 'list'
  editingId.value = null
  fetch()
}
function navigateToFolder(index: number) {
  // 点击面包屑中的某个文件夹：截断路径到该位置
  folderPath.value = folderPath.value.slice(0, index + 1)
  currentFolder.value = folderPath.value[folderPath.value.length - 1] || null
  viewState.value = 'list'
  fetch()
}
function enterFolder(row: any) {
  folderPath.value.push(row)
  currentFolder.value = row
  viewState.value = 'list'
  fetch()
}
function openItem(row: any) {
  if (row.doc_type === 'folder') { enterFolder(row) }
  else {
    editingId.value = row.id
    viewState.value = 'preview'
    // 优先使用列表中的 content；如果为空则从后端获取完整内容
    if (row.content) {
      form.value = { title: row.title, category: row.category || '', doc_type: row.doc_type || 'note', content: row.content }
      nextTick(afterPreviewRender)
    } else {
      form.value = { title: row.title, category: row.category || '', doc_type: row.doc_type || 'note', content: '' }
      loadDocumentContent(row.id)
    }
  }
}
function enterEdit() { viewState.value = 'edit' }

// ============================================================
// 更多菜单操作
// ============================================================
function handleRowAction(cmd: string, row: any) {
  if (cmd === 'edit') { form.value = { title: row.title, category: row.category || '', doc_type: row.doc_type || 'note', content: row.content || '' }; editingId.value = row.id; viewState.value = 'edit' }
  else if (cmd === 'rename') { renameId.value = row.id; renameName.value = row.title; showRename.value = true }
  else if (cmd === 'pin') { ElMessage.success('已置顶') }
  else if (cmd === 'delete') { remove(row.id) }
}
async function doRename() { if (!renameName.value.trim() || !renameId.value) return; try { await knowledgeApi.update(renameId.value, { title: renameName.value }); ElMessage.success('已重命名'); showRename.value = false; await fetch() } catch { ElMessage.error('重命名失败') } }

// ============================================================
// 创建
// ============================================================
function handleCreateCommand(cmd: string) {
  if (cmd === 'upload') showUpload.value = true
  else if (cmd === 'folder') showFolder.value = true
  else if (cmd === 'note') { editingId.value = null; form.value = { title: '', category: '', doc_type: 'note', content: '' }; viewState.value = 'edit' }
}
function handleFileSelect(f: any) { uploadFile.value = f.raw }
async function doUpload() { if (!uploadFile.value) return; uploading.value = true; try { const fd = new FormData(); fd.append('file', uploadFile.value); if (uploadForm.value.category) fd.append('category', uploadForm.value.category); fd.append('doc_type', uploadForm.value.doc_type); if (currentFolder.value) fd.append('parent_id', currentFolder.value.id.toString()); await fetch('/api/v1/knowledge/upload', { method: 'POST', body: fd }); ElMessage.success('上传成功'); showUpload.value = false; await fetch() } catch { ElMessage.error('上传失败') } finally { uploading.value = false } }
function createFolder() { if (!folderName.value.trim()) return; if (!checkPathDepth()) { showFolder.value = false; return } const data: any = { title: folderName.value, content: '', doc_type: 'folder' }; if (currentFolder.value) data.parent_id = currentFolder.value.id; knowledgeApi.create(data).then(() => { ElMessage.success('文件夹已创建'); showFolder.value = false; folderName.value = ''; fetch() }).catch(() => ElMessage.error('创建失败')) }

async function save() { saving.value = true; try { const data: any = { ...form.value }; if (currentFolder.value) data.parent_id = currentFolder.value.id; if (editingId.value) { await knowledgeApi.update(editingId.value, data); ElMessage.success('已保存') } else { await knowledgeApi.create(data); ElMessage.success('已创建') }; viewState.value = 'list'; editingId.value = null; await fetch() } catch (e: any) { ElMessage.error(e.response?.data?.detail || '保存失败') } finally { saving.value = false } }
// ============================================================
// 剪贴板处理 — 在 textarea 上绑定捕获阶段 paste 事件
// ============================================================
let pasteHandler: ((e: ClipboardEvent) => void) | null = null

onMounted(() => {
  fetch()
  loadTree()

  // 延迟绑定：等待 v-md-editor 渲染出 textarea
  nextTick(() => {
    const textarea = document.querySelector('.v-md-textarea-editor textarea') as HTMLTextAreaElement | null
    if (!textarea) return

    pasteHandler = (e: ClipboardEvent) => {
      const cd = e.clipboardData
      if (!cd) return

      // 检测剪贴板中是否包含图片
      let hasImage = false
      if (cd.items) {
        for (let i = 0; i < cd.items.length; i++) {
          if (cd.items[i].type.startsWith('image/')) {
            hasImage = true
            break
          }
        }
      }

      if (hasImage) {
        // 图片粘贴：不干预，让事件冒泡到 v-md-editor 的 upload-image mixin 处理
        return
      }

      // 纯文本粘贴：强制使用 text/plain，防止从 VSCode/浏览器复制时的 HTML 富文本污染
      const plainText = cd.getData('text/plain')
      if (!plainText) return

      // 阻止默认行为（浏览器可能插入 HTML 格式的文本）
      e.preventDefault()
      e.stopPropagation()

      // 通过 execCommand 或直接操作 textarea 插入纯文本
      const start = textarea.selectionStart
      const end = textarea.selectionEnd
      const currentVal = textarea.value
      const newVal = currentVal.substring(0, start) + plainText + currentVal.substring(end)

      // 触发原生 setter 以驱动 Vue v-model
      const nativeSetter = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value')?.set
      if (nativeSetter) {
        nativeSetter.call(textarea, newVal)
      } else {
        textarea.value = newVal
      }
      // 手动触发 input 事件让 v-model 同步
      textarea.dispatchEvent(new Event('input', { bubbles: true }))

      // 恢复光标位置
      const newPos = start + plainText.length
      textarea.setSelectionRange(newPos, newPos)
    }

    textarea.addEventListener('paste', pasteHandler, true) // 捕获阶段
  })
})

onBeforeUnmount(() => {
  if (pasteHandler) {
    const textarea = document.querySelector('.v-md-textarea-editor textarea')
    if (textarea) {
      textarea.removeEventListener('paste', pasteHandler, true)
    }
    pasteHandler = null
  }
})

// ============================================================
// 图片上传处理（截图粘贴 / 拖拽 / 工具栏上传）
// ============================================================
// 图片缓存：存储 base64 数据，用短 ID 引用避免 Markdown 源码过长
const imageStore = new Map<string, string>()
let imageCounter = 0

async function handleUploadImage(event: any, insertImage: Function, files: File[]) {
  if (!files || files.length === 0) return
  const file = files[0]

  const reader = new FileReader()
  reader.onload = (e) => {
    const base64 = e.target?.result as string
    const imgId = `img-${++imageCounter}`
    imageStore.set(imgId, base64)

    // 插入 HTML img 标签（短引用），而不是 ![desc](data:...) 长 base64
    // markdown-it 设置了 html: true，HTML 标签会被保留渲染
    insertImage({
      url: `#${imgId}`,    // 短占位符
      desc: file.name || 'image',
    })
  }
  reader.readAsDataURL(file)
}

async function remove(id: number) {
  try { await ElMessageBox.confirm('确定删除？文件夹内所有内容也将被删除。', '确认', { type: 'warning' }) } catch { return }
  try { await knowledgeApi.delete(id); ElMessage.success('已删除'); await fetch() } catch (e: any) { ElMessage.error(e.response?.data?.detail || '删除失败') }
}
function handleSelection(rows: any[]) { selectedRows.value = rows }
function handleSort(cmd: string) { sortOrder.value = cmd; fetch() }
</script>

<style scoped>
.kb-container { padding: 24px; margin: 0 auto; width: 100%; max-width: 1100px; }
.kb-container.kb-full { max-width: none; padding: 24px 24px 0; }
.kb-breadcrumb { margin-bottom: 16px; }
.kb-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 16px; }
.kb-header h2 { font-size: 20px; font-weight: 600; color: #1f2937; margin: 0; }
.kb-header-right { display: flex; align-items: center; gap: 12px; }
.kb-search { width: 280px; }
.kb-toolbar { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; height: 36px; }
.toolbar-left, .toolbar-right { display: flex; align-items: center; gap: 8px; }
.view-toggle .el-button { padding: 6px 12px; }
.cell-name { display: flex; align-items: center; gap: 8px; }
.file-icon { font-size: 18px; flex-shrink: 0; }
.file-title { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.file-title:hover { text-decoration: underline; }
.kb-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)); gap: 12px; }
.kb-card { padding: 20px 16px; background: #fff; border: 1px solid #e5e7eb; border-radius: 10px; cursor: pointer; transition: all 0.12s; text-align: center; }
.kb-card:hover { border-color: #2563eb; box-shadow: 0 2px 12px rgba(37,99,235,0.08); }
.card-icon { font-size: 36px; margin-bottom: 8px; }
.card-title { font-size: 13px; color: #1f2937; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; margin-bottom: 4px; }
.card-meta { font-size: 11px; color: #9ca3af; }
.kb-empty { text-align: center; padding: 80px 20px; }
.empty-icon { font-size: 56px; margin-bottom: 16px; opacity: 0.5; }
.empty-title { font-size: 18px; font-weight: 500; color: #4b5563; margin-bottom: 8px; }
.empty-desc { font-size: 14px; color: #9ca3af; }
/* 预览页 — 左侧目录 + 右侧预览 */
.preview-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 16px; flex-shrink: 0; }
.preview-header-left { display: flex; align-items: center; gap: 8px; }
.preview-header-right { display: flex; gap: 8px; }
.preview-header-title { font-size: 18px; font-weight: 600; color: #1f2937; }
.preview-layout { display: flex; gap: 0; height: calc(100vh - 180px); }
/* 左侧目录面板 — 自适应内容高度 */
.preview-sidebar {
  width: 200px; flex-shrink: 0;
  background: #f9fafb;
  border: 1px solid #e5e7eb;
  border-radius: 10px 0 0 10px;
  display: flex; flex-direction: column;
  overflow: hidden;
}
.sidebar-section { display: flex; flex-direction: column; overflow: hidden; }
.sidebar-toc {
  display: flex; flex-direction: column;
  max-height: 100%;
  overflow: hidden;
}
.section-header {
  display: flex; align-items: center; justify-content: space-between;
  padding: 12px 12px 8px;
  flex-shrink: 0;
}
.section-title { font-size: 13px; font-weight: 600; color: #374151; }
.section-action { font-size: 14px; color: #6b7280; cursor: pointer; user-select: none; }
.section-action:hover { color: #2563eb; }
.toc-empty { padding: 8px 12px; font-size: 12px; color: #9ca3af; }
/* 目录列表 — 内容溢出时滚动 */
.toc-body {
  flex: 1;
  overflow-y: auto;
  padding: 0 0 8px;
  max-height: 100%;
}
.toc-item {
  padding: 3px 12px; font-size: 12px; color: #6b7280;
  cursor: pointer; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
  transition: background 0.1s;
}
.toc-item:hover { background: #e5e7eb; color: #374151; }
.toc-active { color: #2563eb; font-weight: 500; }

.preview-body { flex: 1; overflow-y: auto; padding: 24px; background: #fff; border: 1px solid #e5e7eb; border-left: none; border-radius: 0 10px 10px 0; }
.kb-editor-page { display: flex; flex-direction: column; height: calc(100vh - 140px); }
.editor-body { flex: 1; min-height: 0; border: 1px solid #e5e7eb; border-radius: 8px; overflow: hidden; }
.md-preview { padding: 16px 20px; font-size: 14px; line-height: 1.8; }
.md-preview :deep(h2) { font-size: 18px; margin: 16px 0 8px; }
.md-preview :deep(h3) { font-size: 15px; margin: 12px 0 6px; }
.md-preview :deep(p) { margin: 6px 0; }
.md-preview :deep(code) { background: #f3f4f6; padding: 2px 6px; border-radius: 4px; font-size: 13px; }
.md-preview :deep(pre) { background: #1f2937; color: #f9fafb; padding: 12px 16px; border-radius: 8px; overflow-x: auto; }
.md-preview :deep(pre code) { background: none; padding: 0; color: inherit; }
.md-preview :deep(blockquote) { border-left: 3px solid #d1d5db; padding-left: 12px; color: #6b7280; margin: 8px 0; }
.md-preview :deep(table) { border-collapse: collapse; width: 100%; margin: 12px 0; }
.md-preview :deep(th), .md-preview :deep(td) { border: 1px solid #d1d5db; padding: 8px 12px; text-align: left; font-size: 13px; }
.md-preview :deep(th) { background: #f3f4f6; font-weight: 600; }
.md-preview :deep(tr:nth-child(even)) { background: #fafafa; }

/* 更多按钮 */
.row-more-btn { width: 28px; height: 28px; border-radius: 6px; border: none; background: transparent; color: #9ca3af; cursor: pointer; display: flex; align-items: center; justify-content: center; transition: background 0.12s; }
.row-more-btn:hover { background: #e5e7eb; color: #374151; }
</style>
