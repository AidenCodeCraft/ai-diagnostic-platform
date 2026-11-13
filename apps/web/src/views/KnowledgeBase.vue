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
        <el-breadcrumb-item v-if="viewState === 'edit'" style="font-size:20px;font-weight:600;color:#1f2937">{{ editingId ? form.title : createLabel }}</el-breadcrumb-item>
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
                <el-dropdown-item command="note">📄 新建文件</el-dropdown-item>
                <el-dropdown-item command="faq">❓ 新建FAQ</el-dropdown-item>
                <el-dropdown-item command="case">🛠️ 新建现场问题</el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </div>
      </div>

      <div class="kb-toolbar">
        <div class="toolbar-left"></div>
        <div class="toolbar-right">
          <el-button-group class="view-toggle">
            <el-button :type="viewMode === 'list' ? 'primary' : ''" @click="viewMode = 'list'">☰ 列表</el-button>
            <el-button :type="viewMode === 'grid' ? 'primary' : ''" @click="viewMode = 'grid'">⊞ 网格</el-button>
          </el-button-group>
          <el-button @click="toggleSort">修改时间 {{ sortOrder === 'updated_asc' ? '↑' : '↓' }}</el-button>
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
          <el-table-column label="文档类型" width="120"><template #default="{ row }">{{ typeLabel(row.doc_type) }}</template></el-table-column>
          <el-table-column label="质量" width="120">
            <template #default="{ row }">
              <template v-if="row.doc_type === 'folder'">—</template>
              <template v-else>
                <el-tag v-if="row.quality_score != null" :type="row.quality_score >= 60 ? 'success' : (row.quality_score >= 40 ? 'warning' : 'info')" size="small">{{ Math.round(row.quality_score) }}</el-tag>
                <el-tag v-if="row.status && row.status !== 'active'" type="info" size="small" style="margin-left:4px">草稿</el-tag>
                <span v-if="row.quality_score == null && (!row.status || row.status === 'active')">—</span>
              </template>
            </template>
          </el-table-column>
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
          <div v-if="item.doc_type !== 'folder' && item.quality_score != null" class="card-quality">
            {{ Math.round(item.quality_score) }} 分<template v-if="item.status && item.status !== 'active'"> · 草稿</template>
          </div>
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
        <!-- 右侧预览（正文全宽） -->
        <div class="preview-body" @scroll.passive="onPreviewScroll">
          <component :is="VMdEditor.Preview" :text="form.content" />
        </div>
        <!-- 右侧悬浮目录（docsify 风格） -->
        <nav
          v-if="tocItems.length"
          class="toc-float"
          :class="{ 'toc-float-expanded': tocHovered }"
          @mouseenter="tocHovered = true"
          @mouseleave="tocHovered = false"
        >
          <button class="toc-float-toggle" @click="tocHovered = !tocHovered" title="目录">
            <span class="toc-float-dot" :style="{ top: tocProgress + '%' }" />
          </button>
          <div class="toc-float-panel">
            <div class="toc-float-title">目录</div>
            <div
              v-for="(item, i) in tocItems"
              :key="i"
              class="toc-item"
              :class="[
                { 'toc-active': activeTocId === item.anchorId },
                `toc-level-${item.level}`,
              ]"
              @click="scrollToTocAnchor(item.anchorId)"
            >{{ item.text }}</div>
          </div>
        </nav>
      </div>
    </div>

    <!-- ============================================================ -->
    <!-- 编辑视图 -->
    <!-- ============================================================ -->
    <div v-else-if="viewState === 'edit'" class="kb-editor-page">
      <div class="kb-header">
        <el-input v-model="form.title" placeholder="标题" style="width:240px;font-size:18px;font-weight:600" />
        <el-select v-model="form.doc_type" style="width:170px;margin-left:8px" @change="onDocTypeChange">
          <el-option label="现场问题示例" value="case" />
          <el-option label="FAQ" value="faq" />
          <el-option label="代码逻辑" value="code_logic" />
          <el-option label="基础知识" value="knowledge" />
          <el-option label="笔记" value="note" />
          <el-option label="手册" value="manual" />
        </el-select>
        <div style="margin-left:auto;display:flex;gap:8px;align-items:center">
          <el-button-group class="mode-toggle">
            <el-button :type="editMode === 'edit' ? 'primary' : ''" @click="editMode = 'edit'">编辑</el-button>
            <el-button :type="editMode === 'split' ? 'primary' : ''" @click="editMode = 'split'; refreshPreview()">分屏</el-button>
            <el-button :type="editMode === 'preview' ? 'primary' : ''" @click="editMode = 'preview'; refreshPreview()">预览</el-button>
          </el-button-group>
          <el-button @click="aiPolish" :loading="polishing">AI润色</el-button>
          <el-button v-if="polishSnapshot !== null" @click="undoPolish">撤销AI润色</el-button>
          <el-button @click="showGuide = true">格式说明</el-button>
          <el-tooltip placement="bottom" effect="light">
            <template #content>
              <div style="max-width:340px;line-height:1.7">
                进阶覆盖：手动修正系统自动生成的「诊断剧本」（现象、日志关键词、正则、根因、解决方案等）。
                不填写则使用模板/日志解析自动生成的结果；填写后会覆盖自动值，用于提升日志定位与诊断准确率。
              </div>
            </template>
            <el-button @click="showProfile = true">进阶覆盖</el-button>
          </el-tooltip>
          <el-button @click="cancelEdit">取消</el-button>
          <el-button type="primary" @click="save" :loading="saving">{{ editingId ? '保存' : '创建' }}</el-button>
        </div>
      </div>
      <div v-if="currentTemplate" class="format-hint">
        <span class="format-hint-text">格式要求：{{ currentTemplate.guide }}</span>
        <el-button link type="primary" size="small" @click="showGuide = true">查看示例 / 插入模板</el-button>
      </div>
      <div class="editor-body" :class="'mode-' + editMode">
        <div v-show="editMode !== 'preview'" class="editor-pane">
          <v-md-editor ref="editorRef" v-model="form.content" height="100%" left-toolbar="undo redo | bold italic strikethrough | h2 h3 h4 | ul ol | link image | code quote | table hr | fullscreen" :disabled-menus="[]" @upload-image="handleUploadImage" />
        </div>
        <div v-show="editMode !== 'edit'" class="preview-pane">
          <div class="preview-pane-header">
            <span>提交后预览</span>
            <span class="preview-quality">
              质量分
              <b>{{ previewResult ? Math.round(previewResult.quality_score) : '—' }}</b>
              <el-tag v-if="previewResult" :type="previewResult.status_hint === 'active' ? 'success' : 'warning'" size="small">
                {{ previewResult.status_hint === 'active' ? '可发布' : '待完善' }}
              </el-tag>
            </span>
          </div>
          <div class="preview-pane-body">
            <div v-if="previewLoading" class="preview-loading">规范化中…</div>
            <template v-else-if="previewResult">
              <div v-if="previewResult.issues.length" class="preview-issues">
                <div v-for="(issue, i) in previewResult.issues" :key="i" :class="['preview-issue', issue.level]">
                  {{ issue.level === 'error' ? '✕' : '⚠' }} {{ issue.message }}
                </div>
              </div>
              <div v-if="previewResult.suggested_keywords.length" class="preview-suggest">
                候选关键词：{{ previewResult.suggested_keywords.join('、') }}（可加入「日志特征」）
              </div>
              <div v-if="previewResult.notes && previewResult.notes.length" class="preview-notes">
                <div v-for="(note, i) in previewResult.notes" :key="i">✨ {{ note }}</div>
              </div>
              <div class="preview-rendered">
                <component :is="VMdEditor.Preview" :text="previewResult.normalized_content" />
              </div>
            </template>
            <div v-else class="preview-loading">暂无内容</div>
          </div>
        </div>
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

    <el-dialog v-model="showGuide" :title="guideTitle" width="760px" top="6vh">
      <div v-if="currentTemplate" class="guide-body">
        <h4>格式要求</h4>
        <p class="guide-text">{{ currentTemplate.guide }}</p>
        <h4>章节结构</h4>
        <el-table :data="currentTemplate.sections" size="small" border>
          <el-table-column prop="title" label="章节" width="160" />
          <el-table-column prop="level" label="级别" width="110">
            <template #default="{ row }">{{ levelLabel(row.level) }}</template>
          </el-table-column>
          <el-table-column label="填写说明">
            <template #default="{ row }">{{ sectionHint(row) }}</template>
          </el-table-column>
        </el-table>
        <h4>填写示例</h4>
        <div class="guide-example">
          <component :is="VMdEditor.Preview" :text="currentTemplate.example" />
        </div>
      </div>
      <div v-else class="guide-body">
        <p class="guide-text">自由格式：建议使用小标题分节、条目化表达，便于阅读与检索。</p>
      </div>
      <template #footer>
        <el-button @click="showGuide = false">关闭</el-button>
        <el-button type="primary" @click="insertSkeleton">插入模板骨架</el-button>
      </template>
    </el-dialog>

    <!-- 诊断剧本（结构化诊断信息），随知识条目保存 -->
    <el-dialog v-model="showProfile" title="进阶覆盖 · 诊断配置（可选）" width="640px" top="6vh">
      <div class="profile-tip">
        系统会根据模板/日志解析自动生成诊断剧本；这里填写的字段会覆盖自动值，只需补充或修正关键字段即可。
      </div>
      <el-form label-width="110px" label-position="left">
        <el-form-item label="现象/问题">
          <el-input v-model="profileForm.symptom" type="textarea" :rows="2" placeholder="如：设备黑屏、程序版本号查询" />
        </el-form-item>
        <el-form-item label="环境">
          <el-input v-model="profileForm.environment" placeholder="设备/芯片/固件版本（可选）" />
        </el-form-item>
        <el-form-item label="日志关键词">
          <el-input v-model="profileForm.log_keywords" type="textarea" :rows="2" placeholder="每行一个，如：version、版本号、firmware" />
        </el-form-item>
        <el-form-item label="日志正则">
          <el-input v-model="profileForm.log_patterns" type="textarea" :rows="2" placeholder="每行一个正则，如：(?i)(version|版本号)\\s*[:=]\\s*[\\w.\\-]+" />
        </el-form-item>
        <el-form-item label="排除正则">
          <el-input v-model="profileForm.negative_patterns" type="textarea" :rows="2" placeholder="每行一个，用于排除误命中" />
        </el-form-item>
        <el-form-item label="判定说明">
          <el-input v-model="profileForm.expected" type="textarea" :rows="2" placeholder="命中后如何判定，如：提取 x.y.z 版本号" />
        </el-form-item>
        <el-form-item label="根因">
          <el-input v-model="profileForm.root_cause" type="textarea" :rows="2" />
        </el-form-item>
        <el-form-item label="解决方案">
          <el-input v-model="profileForm.solution" type="textarea" :rows="2" />
        </el-form-item>
        <el-form-item label="置信度">
          <el-slider v-model="profileForm.confidence" :min="0" :max="1" :step="0.05" style="width:100%" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showProfile = false">关闭</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount, computed, nextTick, watch, defineComponent, h } from 'vue'
import { Search, UploadFilled } from '@element-plus/icons-vue'
import { knowledgeApi, type KnowledgeTemplateInfo } from '@/api/knowledge'
import { ElMessage, ElMessageBox } from 'element-plus'
import VMdEditor from '@kangc/v-md-editor'

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
const loading = ref(false)
const saving = ref(false)
const uploading = ref(false)
const page = ref(1)
const pageSize = 20
const total = ref(0)
const searchQuery = ref('')
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
const uploadForm = ref({ doc_type: 'manual' })
const uploadFile = ref<File | null>(null)
const form = ref({ title: '', doc_type: 'note', content: '' })

const createLabel = computed(() => {
  const labels: Record<string, string> = { note: '新建文件', faq: '新建FAQ', case: '新建现场问题' }
  return labels[form.value.doc_type] || '新建文件'
})

// ── 诊断剧本（结构化诊断信息）──
const showProfile = ref(false)
const profileForm = ref({
  symptom: '',
  environment: '',
  log_keywords: '',
  log_patterns: '',
  negative_patterns: '',
  expected: '',
  root_cause: '',
  solution: '',
  confidence: 0.8,
})

function _splitLines(s: string): string[] {
  return s.split('\n').map(x => x.trim()).filter(Boolean)
}

function resetProfile() {
  profileForm.value = {
    symptom: '', environment: '',
    log_keywords: '', log_patterns: '', negative_patterns: '',
    expected: '', root_cause: '', solution: '',
    confidence: 0.8,
  }
}

function fillProfile(p: any) {
  profileForm.value = {
    symptom: p?.symptom || '',
    environment: p?.environment || '',
    log_keywords: (p?.log_keywords || []).join('\n'),
    log_patterns: (p?.log_patterns || []).join('\n'),
    negative_patterns: (p?.negative_patterns || []).join('\n'),
    expected: p?.expected || '',
    root_cause: p?.root_cause || '',
    solution: p?.solution || '',
    confidence: typeof p?.confidence === 'number' ? p.confidence : 0.8,
  }
}

async function loadProfileForDoc(id: number) {
  try {
    const { data } = await knowledgeApi.getProfile(id)
    fillProfile(data)
  } catch {
    resetProfile()
  }
}

function buildProfilePayload() {
  const f = profileForm.value
  const hasAny = [f.symptom, f.environment, f.log_keywords, f.log_patterns,
    f.negative_patterns, f.expected, f.root_cause, f.solution].some(v => v && v.trim())
  if (!hasAny) return undefined
  return {
    symptom: f.symptom.trim(),
    environment: f.environment.trim(),
    log_keywords: _splitLines(f.log_keywords),
    log_patterns: _splitLines(f.log_patterns),
    negative_patterns: _splitLines(f.negative_patterns),
    expected: f.expected.trim(),
    root_cause: f.root_cause.trim(),
    solution: f.solution.trim(),
    confidence: f.confidence,
    status: 'active',
    source: 'manual',
  }
}

// ── 编辑模式 / 提交后预览 / AI 润色 / 模板说明 ──
const editMode = ref<'edit' | 'split' | 'preview'>('edit')
const previewResult = ref<any>(null)
const previewLoading = ref(false)
const polishing = ref(false)
const polishSnapshot = ref<string | null>(null)
const templates = ref<KnowledgeTemplateInfo[]>([])
const showGuide = ref(false)
let previewTimer: ReturnType<typeof setTimeout> | null = null

const currentTemplate = computed(
  () => templates.value.find(t => t.doc_type === form.value.doc_type) || null,
)
const guideTitle = computed(
  () => `格式说明${currentTemplate.value ? ' · ' + currentTemplate.value.name : ''}`,
)

function levelLabel(level: string) {
  const labels: Record<string, string> = { required: '必填', recommended: '建议', optional: '可选' }
  return labels[level] || level
}

function sectionHint(row: { key: string }) {
  const hints: Record<string, string> = {
    symptom: '描述现场现象', analysis: '说明原因与分析过程', root_cause: '说明根因/判断依据',
    solution: '处理步骤与最终结果', features: '适用环境/设备型号等', log_signature: '日志关键词/正则',
    keywords: '用于检索的关键字', keyword_explain: '解释关键字含义', related: '关联条目',
    images: '截图或示意', examples: '示例', author: '作者', log_keywords: '日志关键词',
    log_patterns: '日志正则', negative_patterns: '排除正则', expected: '判定说明', body: '正文',
  }
  return hints[row.key] || '—'
}

async function loadTemplates() {
  try {
    const { data } = await knowledgeApi.templates()
    templates.value = data.templates || []
  } catch (e: any) {
    console.warn('[KnowledgeBase] load templates failed:', e?.message)
  }
}

/** 新建时的预填骨架；笔记等自由文档给最小正文骨架 */
function skeletonFor(docType: string): string {
  const template = templates.value.find(t => t.doc_type === docType)
  if (template && template.skeleton) return template.skeleton
  return docType === 'note' ? '## 正文\n\n（在此填写内容）\n' : ''
}

async function insertSkeleton() {
  const skeleton = skeletonFor(form.value.doc_type)
  if (!skeleton) {
    ElMessage.info('该类型为自由格式，没有固定模板')
    return
  }
  if (form.value.content.trim()) {
    try {
      await ElMessageBox.confirm('插入模板会覆盖当前编辑内容，确定继续？', '确认', { type: 'warning' })
    } catch { return }
  }
  form.value.content = skeleton
  polishSnapshot.value = null
  showGuide.value = false
  nextTick(() => refreshPreview())
  ElMessage.success('已插入模板骨架')
}

function defaultEditMode(_docType: string): 'edit' | 'split' {
  // 新建/编辑文件默认分屏（左侧编辑、右侧提交后预览）
  return 'split'
}

function schedulePreview() {
  if (previewTimer) clearTimeout(previewTimer)
  previewTimer = setTimeout(() => refreshPreview(), 500)
}

async function refreshPreview() {
  if (viewState.value !== 'edit') return
  previewLoading.value = true
  try {
    const { data } = await knowledgeApi.formatPreview({
      content: form.value.content,
      doc_type: form.value.doc_type,
      title: form.value.title,
    })
    previewResult.value = data
  } catch (e: any) {
    console.warn('[KnowledgeBase] format preview failed:', e?.response?.data?.detail || e?.message || e)
  } finally {
    previewLoading.value = false
  }
}

watch(
  () => [form.value.content, form.value.doc_type],
  () => schedulePreview(),
)

/** AI 润色：用户写大致内容 → LLM 按模板规范化（不可用时自动回退规则整理） */
async function aiPolish() {
  if (!form.value.content.trim()) {
    ElMessage.warning('请先输入内容，再使用 AI 润色')
    return
  }
  polishing.value = true
  try {
    const before = form.value.content
    const { data } = await knowledgeApi.polish({
      content: before,
      doc_type: form.value.doc_type,
      title: form.value.title,
    })
    const polished = data.polished_content || data.normalized_content || before
    if (polished === before) {
      ElMessage.info('内容已符合模板格式，无需润色')
      return
    }
    polishSnapshot.value = before
    form.value.content = polished
    previewResult.value = data
    if (data.source === 'llm') {
      ElMessage.success('AI 润色完成，已按模板规范化')
    } else {
      ElMessage.warning('AI 服务暂不可用（请检查 系统配置 → LLM 配置 的 API Key），已按模板规则完成结构化整理')
    }
    nextTick(() => refreshPreview())
  } catch (e: any) {
    ElMessage.error('AI 润色失败: ' + (e?.response?.data?.detail || e?.message))
  } finally {
    polishing.value = false
  }
}

function undoPolish() {
  if (polishSnapshot.value === null) return
  form.value.content = polishSnapshot.value
  polishSnapshot.value = null
  ElMessage.info('已撤销 AI 润色')
  nextTick(() => refreshPreview())
}

function onDocTypeChange() {
  // 切换类型时，若内容为空或仍是某个模板骨架，则自动套用新类型骨架
  const content = form.value.content.trim()
  const isSkeleton = templates.value.some(t => t.skeleton.trim() === content)
  if (!content || isSkeleton) {
    form.value.content = skeletonFor(form.value.doc_type)
  }
  polishSnapshot.value = null
  refreshPreview()
}

function showSaveResult(resp: any) {
  if (!resp) return
  const quality = resp.quality_score
  const issues: any[] = Array.isArray(resp.issues) ? resp.issues : []
  if (resp.status === 'draft') {
    const errors = issues.filter((i: any) => i.level === 'error')
    const msg = errors.length ? errors.map((i: any) => i.message).join('；') : '存在待完善项'
    ElMessage.warning(`已保存为草稿（质量分 ${quality != null ? Math.round(quality) : '—'}）：${msg}`)
  } else if (issues.length) {
    ElMessage.success(`已保存（质量分 ${quality != null ? Math.round(quality) : '—'}，${issues.length} 条提示）`)
  } else {
    ElMessage.success('已保存')
  }
}

const viewState = ref<'list' | 'preview' | 'edit'>('list')
const currentFolder = ref<any>(null)
const folderPath = ref<any[]>([])  // 从根到当前文件夹的完整路径链
const editorRef = ref<any>(null)
const folderTree = ref<any[]>([])   // 知识库文件夹树

// 路径深度限制（Windows MAX_PATH = 260）
const MAX_PATH_LENGTH = 200
const folderDepth = ref(0)

// ============================================================
const _kTimeFmt = new Intl.DateTimeFormat('zh-CN', { year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false })
function formatTime(ts: string) { if (!ts) return ''; try { return _kTimeFmt.format(new Date(ts)) } catch { return ts } }
function formatSize(row: any) { if (row.doc_type === 'folder') return '—'; if (!row.content) return '—'; const bytes = new Blob([row.content]).size; return bytes < 1024 ? bytes + ' B' : (bytes / 1024).toFixed(1) + ' KB' }
function typeLabel(docType: string) { const map: Record<string, string> = { note: '笔记', folder: '文件夹', manual: '手册', faq: 'FAQ', case: '现场问题示例', code_logic: '代码逻辑', knowledge: '基础知识', bug_report: 'Bug', datasheet: '数据手册' }; return map[docType] || docType || '—' }

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

// 右侧悬浮目录交互状态
const tocHovered = ref(false)
const activeTocId = ref('')
const tocProgress = ref(0)  // 0~100，用于右侧进度圆点定位

function scrollToTocAnchor(anchorId: string) {
  const el = document.getElementById(anchorId)
  if (el) {
    el.scrollIntoView({ behavior: 'smooth', block: 'start' })
    activeTocId.value = anchorId
  }
}

// Scrollspy：滚动时高亮当前章节 + 更新进度圆点
let scrollObserver: IntersectionObserver | null = null

function onPreviewScroll() {
  // 节流在 IntersectionObserver 回调里处理，这里仅用于进度计算兜底
  updateTocProgress()
}

function updateTocProgress() {
  const body = document.querySelector('.preview-body') as HTMLElement | null
  if (!body) return
  const max = body.scrollHeight - body.clientHeight
  if (max <= 0) { tocProgress.value = 0; return }
  tocProgress.value = Math.min(100, Math.max(0, (body.scrollTop / max) * 100))
}

function setupScrollSpy() {
  const body = document.querySelector('.preview-body') as HTMLElement | null
  if (!body) return

  // 断开旧的观察器（切换文档时重建，观察新的标题元素）
  if (scrollObserver) {
    scrollObserver.disconnect()
    scrollObserver = null
  }
  activeTocId.value = ''
  tocProgress.value = 0

  scrollObserver = new IntersectionObserver(
    (entries) => {
      // 取当前视口中「最靠上且仍可见」的标题
      const visible = entries
        .filter(e => e.isIntersecting)
        .sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top)
      if (visible.length > 0) {
        activeTocId.value = visible[0].target.id
      }
      updateTocProgress()
    },
    { root: body, rootMargin: '-10% 0px -70% 0px', threshold: 0 },
  )

  body.querySelectorAll('h1, h2, h3').forEach(el => scrollObserver!.observe(el))
}

// 预览渲染后统一处理：注入标题锚点 + 替换图片短引用 + 建立 Scrollspy
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

    // 2. 建立滚动监听（Scrollspy）
    setupScrollSpy()
    updateTocProgress()
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
    const params: any = { page: page.value, page_size: pageSize, sort: sortOrder.value }
    if (currentFolder.value) params.parent_id = currentFolder.value.id
    const { data } = await knowledgeApi.list(params)
    items.value = data.items; total.value = data.total
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
  polishSnapshot.value = null
  if (row.doc_type === 'folder') { enterFolder(row) }
  else {
    editingId.value = row.id
    viewState.value = 'preview'
    // 优先使用列表中的 content；如果为空则从后端获取完整内容
    if (row.content) {
      form.value = { title: row.title, doc_type: row.doc_type || 'note', content: row.content }
      nextTick(afterPreviewRender)
    } else {
      form.value = { title: row.title, doc_type: row.doc_type || 'note', content: '' }
      loadDocumentContent(row.id)
    }
    loadProfileForDoc(row.id)
  }
}
function enterEdit() {
  if (editingId.value) loadProfileForDoc(editingId.value)
  polishSnapshot.value = null
  editMode.value = defaultEditMode(form.value.doc_type)
  viewState.value = 'edit'
  nextTick(() => refreshPreview())
}

// ============================================================
// 更多菜单操作
// ============================================================
async function handleRowAction(cmd: string, row: any) {
  if (cmd === 'edit') { form.value = { title: row.title, doc_type: row.doc_type || 'note', content: row.content || '' }; editingId.value = row.id; polishSnapshot.value = null; editMode.value = defaultEditMode(form.value.doc_type); viewState.value = 'edit'; loadProfileForDoc(row.id); nextTick(() => refreshPreview()) }
  else if (cmd === 'rename') { renameId.value = row.id; renameName.value = row.title; showRename.value = true }
  else if (cmd === 'pin') {
    try {
      const newPinned = !row.is_pinned
      await knowledgeApi.update(row.id, { is_pinned: newPinned })
      ElMessage.success(newPinned ? '已置顶' : '已取消置顶')
      await fetch()
    } catch { ElMessage.error('操作失败') }
  }
  else if (cmd === 'delete') { remove(row.id) }
}
async function doRename() { if (!renameName.value.trim() || !renameId.value) return; try { await knowledgeApi.update(renameId.value, { title: renameName.value }); ElMessage.success('已重命名'); showRename.value = false; await fetch() } catch { ElMessage.error('重命名失败') } }

// ============================================================
// 创建
// ============================================================
async function handleCreateCommand(cmd: string) {
  if (cmd === 'upload') { showUpload.value = true; return }
  if (cmd === 'folder') { showFolder.value = true; return }
  // note = 新建文件（默认笔记）；faq / case 为对应类型的新建入口
  const docType = cmd === 'faq' ? 'faq' : cmd === 'case' ? 'case' : 'note'
  if (!templates.value.length) await loadTemplates()
  editingId.value = null
  form.value = { title: '', doc_type: docType, content: skeletonFor(docType) }
  resetProfile()
  polishSnapshot.value = null
  editMode.value = 'split'
  viewState.value = 'edit'
  nextTick(() => refreshPreview())
}
function handleFileSelect(f: any) { uploadFile.value = f.raw }
async function doUpload() { if (!uploadFile.value) return; uploading.value = true; try { const fd = new FormData(); fd.append('file', uploadFile.value); fd.append('doc_type', uploadForm.value.doc_type); if (currentFolder.value) fd.append('parent_id', currentFolder.value.id.toString()); await knowledgeApi.upload(fd); ElMessage.success('上传成功'); showUpload.value = false; await fetch() } catch (e: any) { ElMessage.error(e?.response?.data?.detail || '上传失败') } finally { uploading.value = false } }
function createFolder() { if (!folderName.value.trim()) return; if (!checkPathDepth()) { showFolder.value = false; return } const data: any = { title: folderName.value, content: '', doc_type: 'folder' }; if (currentFolder.value) data.parent_id = currentFolder.value.id; knowledgeApi.create(data).then(() => { ElMessage.success('文件夹已创建'); showFolder.value = false; folderName.value = ''; fetch() }).catch(() => ElMessage.error('创建失败')) }

async function save() {
  saving.value = true
  try {
    const data: any = { ...form.value }
    if (currentFolder.value) data.parent_id = currentFolder.value.id
    const profile = buildProfilePayload()
    if (profile) data.profile = profile
    let resp: any = null
    if (editingId.value) {
      resp = (await knowledgeApi.update(editingId.value, data)).data
    } else {
      resp = (await knowledgeApi.create(data)).data
    }
    viewState.value = 'list'
    editingId.value = null
    polishSnapshot.value = null
    await fetch()
    showSaveResult(resp)
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail || '保存失败')
  } finally {
    saving.value = false
  }
}
// ============================================================
// 剪贴板处理 — 在 textarea 上绑定捕获阶段 paste 事件
// ============================================================
let pasteHandler: ((e: ClipboardEvent) => void) | null = null

onMounted(() => {
  fetch()
  loadTree()
  loadTemplates()

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

    textarea.addEventListener('paste', pasteHandler as EventListener, true) // 捕获阶段
  })
})

onBeforeUnmount(() => {
  if (pasteHandler) {
    const textarea = document.querySelector('.v-md-textarea-editor textarea')
    if (textarea) {
      textarea.removeEventListener('paste', pasteHandler as EventListener, true)
    }
    pasteHandler = null
  }
  if (scrollObserver) {
    scrollObserver.disconnect()
    scrollObserver = null
  }
})

// ============================================================
// 图片上传处理（截图粘贴 / 拖拽 / 工具栏上传）
// ============================================================
async function handleUploadImage(event: any, insertImage: Function, files: File[]) {
  if (!files || files.length === 0) return
  const file = files[0]

  const fd = new FormData()
  fd.append('file', file)
  try {
    const { data } = await knowledgeApi.uploadImage(fd)
    // 插入指向后端图片端点的 URL，图片持久化到服务端（对象存储 / 本地目录）
    insertImage({ url: data.url, desc: file.name || 'image' })
  } catch (e: any) {
    ElMessage.error('图片上传失败: ' + (e?.response?.data?.detail || e.message))
  }
}

async function remove(id: number) {
  try { await ElMessageBox.confirm('确定删除？文件夹内所有内容也将被删除。', '确认', { type: 'warning' }) } catch { return }
  try { await knowledgeApi.delete(id); ElMessage.success('已删除'); await fetch() } catch (e: any) { ElMessage.error(e.response?.data?.detail || '删除失败') }
}
function handleSelection(rows: any[]) { selectedRows.value = rows }
function toggleSort() {
  sortOrder.value = sortOrder.value === 'updated_desc' ? 'updated_asc' : 'updated_desc'
  fetch()
}
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
/* 预览页 — 正文全宽 + 右侧悬浮目录 */
.preview-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 16px; flex-shrink: 0; }
.preview-header-left { display: flex; align-items: center; gap: 8px; }
.preview-header-right { display: flex; gap: 8px; }
.format-hint {
  display: flex; align-items: center; justify-content: space-between; gap: 12px;
  margin: 0 0 10px; padding: 8px 12px; border-radius: 8px;
  background: #f8fafc; border: 1px solid #e5e7eb; color: #4b5563; font-size: 13px;
}
.format-hint-text { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.guide-body h4 { margin: 14px 0 8px; font-size: 14px; color: #1f2937; }
.guide-body h4:first-child { margin-top: 0; }
.guide-text { margin: 0; color: #4b5563; font-size: 13px; line-height: 1.8; }
.guide-example {
  max-height: 320px; overflow-y: auto; padding: 12px 16px;
  background: #f9fafb; border: 1px solid #e5e7eb; border-radius: 8px;
  font-size: 13px; line-height: 1.7;
}
.profile-tip {
  margin-bottom: 14px; padding: 10px 12px; border-radius: 8px;
  background: #f0f7ff; border: 1px solid #d6e8ff;
  color: #4b5563; font-size: 13px; line-height: 1.7;
}
.preview-header-title { font-size: 18px; font-weight: 600; color: #1f2937; }
.preview-layout { position: relative; display: flex; gap: 0; height: calc(100vh - 180px); }

.preview-body {
  flex: 1; overflow-y: auto; padding: 24px 48px 24px 24px;
  background: #fff; border: 1px solid #e5e7eb; border-radius: 10px;
  scroll-behavior: smooth;
}
.preview-body :deep(.v-md-editor-preview img),
.preview-body :deep(img) {
  max-width: 100%;
  height: auto;
  border-radius: 6px;
  margin: 8px 0;
}

/* ============================================================
   右侧悬浮目录（docsify 风格）
   - 收起时仅显示一条竖向进度条 + 圆点
   - 悬停展开为完整目录面板
   ============================================================ */
.toc-float {
  position: absolute;
  right: 12px; top: 50%;
  transform: translateY(-50%);
  z-index: 10;
  display: flex;
  align-items: center;
}

/* 收起态的竖向进度条 */
.toc-float-toggle {
  position: relative;
  width: 3px; height: 120px;
  background: #e5e7eb;
  border: none; border-radius: 2px;
  cursor: pointer; padding: 0;
  transition: width 0.15s;
}
.toc-float-toggle:hover { width: 5px; background: #d1d5db; }

/* 当前阅读位置圆点 */
.toc-float-dot {
  position: absolute;
  left: 50%; top: 0;
  width: 9px; height: 9px;
  background: #2563eb;
  border-radius: 50%;
  transform: translate(-50%, -50%);
  box-shadow: 0 0 0 2px #fff, 0 0 0 3px #2563eb;
  transition: top 0.2s ease;
  pointer-events: none;
}

/* 悬停展开的目录面板 */
.toc-float-panel {
  position: absolute;
  right: 16px; top: 50%;
  transform: translateY(-50%);
  width: 220px; max-height: 70vh;
  overflow-y: auto;
  background: #fff;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.08);
  padding: 8px 0;
  opacity: 0; visibility: hidden;
  transition: opacity 0.15s ease, visibility 0.15s;
}
.toc-float-expanded .toc-float-panel { opacity: 1; visibility: visible; }

.toc-float-title {
  padding: 4px 14px 8px;
  font-size: 12px; font-weight: 600; color: #9ca3af;
  border-bottom: 1px solid #f3f4f6; margin-bottom: 4px;
  letter-spacing: 0.5px;
}

.toc-item {
  padding: 5px 14px; font-size: 12px; color: #6b7280;
  cursor: pointer; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
  transition: background 0.1s, color 0.1s;
  line-height: 1.5;
}
.toc-item:hover { background: #f3f4f6; color: #374151; }

/* 层级视觉：h1/h2/h3 不同缩进与字重 */
.toc-level-1 { font-weight: 600; color: #374151; padding-left: 14px; }
.toc-level-2 { padding-left: 26px; }
.toc-level-3 { padding-left: 38px; color: #9ca3af; font-size: 11px; }

/* 当前阅读章节高亮 */
.toc-active {
  color: #2563eb;
  background: #eff6ff;
  border-left: 2px solid #2563eb;
  font-weight: 600;
}
.toc-level-1.toc-active { padding-left: 12px; }
.toc-level-2.toc-active { padding-left: 24px; }
.toc-level-3.toc-active { padding-left: 36px; }

/* 移动端：隐藏悬浮目录，改为全宽阅读 */
@media (max-width: 768px) {
  .toc-float { display: none; }
  .preview-body { padding: 16px; }
}
.kb-editor-page { display: flex; flex-direction: column; height: calc(100vh - 140px); }
.editor-body { flex: 1; min-height: 0; display: flex; gap: 12px; }
.editor-pane { flex: 1; min-width: 0; height: 100%; border: 1px solid #e5e7eb; border-radius: 8px; overflow: hidden; }
.preview-pane { flex: 1; min-width: 0; display: flex; flex-direction: column; border: 1px solid #e5e7eb; border-radius: 8px; overflow: hidden; background: #fff; }
.preview-pane-header { display: flex; align-items: center; justify-content: space-between; padding: 8px 12px; border-bottom: 1px solid #f0f0f0; font-size: 13px; color: #374151; }
.preview-quality { display: flex; align-items: center; gap: 8px; font-size: 12px; color: #6b7280; }
.preview-pane-body { flex: 1; overflow: auto; padding: 12px 16px; }
.preview-loading { color: #9ca3af; font-size: 13px; padding: 12px; }
.preview-issues { margin-bottom: 8px; }
.preview-issue { font-size: 12px; line-height: 1.7; }
.preview-issue.error { color: #dc2626; }
.preview-issue.warn { color: #d97706; }
.preview-suggest { font-size: 12px; color: #6b7280; margin-bottom: 8px; }
.preview-notes {
  margin-bottom: 8px; padding: 8px 10px; border-radius: 6px;
  background: #f0f9ff; border: 1px solid #dbeafe;
  color: #2563eb; font-size: 12px; line-height: 1.8;
}
.preview-rendered { font-size: 14px; line-height: 1.7; color: #374151; }
.mode-toggle .el-button { padding: 6px 10px; }
.card-quality { font-size: 11px; color: #2563eb; margin-top: 4px; }
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
