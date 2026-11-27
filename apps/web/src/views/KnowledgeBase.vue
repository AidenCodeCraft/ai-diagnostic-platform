<template>
  <div class="kb-container" :class="{ 'kb-full': viewState === 'edit' }">
    <!-- ============================================================ -->
    <!-- 面包屑（所有视图，替代标题） -->
    <!-- ============================================================ -->
    <div class="kb-breadcrumb">
      <el-breadcrumb separator="/">
        <el-breadcrumb-item>
          <a @click="backToList"
            style="cursor:pointer;font-size:20px;font-weight:600;color:var(--kb-text);text-decoration:none">知识库</a>
        </el-breadcrumb-item>
        <!-- 文件夹路径链（所有视图下都可点击跳转） -->
        <el-breadcrumb-item v-for="(f, i) in folderPath" :key="f.id"
          style="font-size:20px;font-weight:600;color:var(--kb-text)">
          <a @click="navigateToFolder(i)" style="cursor:pointer;color:var(--kb-link);text-decoration:none">{{ f.title }}</a>
        </el-breadcrumb-item>
        <!-- 当前文件 -->
        <el-breadcrumb-item v-if="viewState === 'preview'" style="font-size:20px;font-weight:600;color:var(--kb-text)">{{
          form.title }}</el-breadcrumb-item>
        <el-breadcrumb-item v-if="viewState === 'edit'" style="font-size:20px;font-weight:600;color:var(--kb-text)">{{
          editingId ? form.title : createLabel }}</el-breadcrumb-item>
      </el-breadcrumb>
    </div>

    <!-- ============================================================ -->
    <!-- 列表视图 — 无重复标题 -->
    <!-- ============================================================ -->
    <template v-if="viewState === 'list'">
      <div class="kb-header">
        <div></div>
        <div class="kb-header-right">
          <el-input v-model="searchQuery" placeholder="搜索文件..." class="kb-search" clearable
            @keyup.enter="doSearch" :prefix-icon="Search" />
          <el-dropdown v-if="canManage" @command="handleCreateCommand" trigger="click">
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
        <div class="empty-desc">{{ canManage ? (currentFolder ? '点击"新建"添加内容' : '点击"新建"开始创建文档或上传文件') : '这里还没有可查看的内容' }}</div>
      </div>

      <!-- 列表 -->
      <div v-else-if="viewMode === 'list'" class="kb-table-wrap" v-loading="loading">
        <el-table :data="items" stripe @selection-change="handleSelection">
          <el-table-column v-if="canManage" type="selection" width="40" />
          <el-table-column prop="title" label="名称" min-width="220">
            <template #default="{ row }">
              <div class="cell-name">
                <span class="file-icon">{{ row.doc_type === 'note' ? '📝' : row.doc_type === 'folder' ? '📂' : '📄'
                  }}</span>
                <span class="file-title" @click="openItem(row)" style="cursor:pointer;color:var(--kb-link)">{{ row.title
                  }}</span>
              </div>
            </template>
          </el-table-column>
          <el-table-column label="文档类型" width="120"><template #default="{ row }">{{ typeLabel(row.doc_type)
              }}</template></el-table-column>
          <el-table-column label="质量" width="120">
            <template #default="{ row }">
              <template v-if="row.doc_type === 'folder'">—</template>
              <template v-else>
                <el-tag v-if="row.quality_score != null"
                  :type="row.quality_score >= 60 ? 'success' : (row.quality_score >= 40 ? 'warning' : 'info')"
                  size="small">{{ Math.round(row.quality_score) }}</el-tag>
                <el-tag v-if="row.status && row.status !== 'active'" type="info" size="small"
                  style="margin-left:4px">草稿</el-tag>
                <span v-if="row.quality_score == null && (!row.status || row.status === 'active')">—</span>
              </template>
            </template>
          </el-table-column>
          <el-table-column prop="updated_at" label="修改时间" width="180"><template #default="{ row }">{{
            formatTime(row.updated_at || row.created_at) }}</template></el-table-column>
          <el-table-column label="大小" width="100"><template #default="{ row }">{{ formatSize(row)
              }}</template></el-table-column>
          <!-- 更多菜单 -->
          <el-table-column v-if="canManage" label="" width="60" fixed="right">
            <template #default="{ row }">
              <el-dropdown trigger="click" @command="(cmd: string) => handleRowAction(cmd, row)">
                <button class="row-more-btn">
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <circle cx="12" cy="5" r="1" />
                    <circle cx="12" cy="12" r="1" />
                    <circle cx="12" cy="19" r="1" />
                  </svg>
                </button>
                <template #dropdown>
                  <el-dropdown-menu>
                    <el-dropdown-item v-if="row.doc_type !== 'folder'" command="edit">✏️ 编辑</el-dropdown-item>
                    <el-dropdown-item command="rename">✏️ 重命名</el-dropdown-item>
                    <el-dropdown-item command="pin">📌 置顶</el-dropdown-item>
                    <el-dropdown-item v-if="row.doc_type !== 'folder'" command="copy">📄 复制</el-dropdown-item>
                    <el-dropdown-item command="delete" divided style="color:var(--chat-popup-danger-hover-text)">🗑️ 删除</el-dropdown-item>
                  </el-dropdown-menu>
                </template>
              </el-dropdown>
            </template>
          </el-table-column>
        </el-table>
        <el-pagination v-if="total > pageSize" style="margin-top:16px;justify-content:center" background
          layout="prev,pager,next" :total="total" :page-size="pageSize" v-model:current-page="page" @change="reload" />
      </div>

      <!-- 网格 -->
      <div v-else class="kb-grid" v-loading="loading">
        <div v-for="item in items" :key="item.id" class="kb-card" @click="openItem(item)">
          <div class="card-icon">{{ item.doc_type === 'note' ? '📝' : item.doc_type === 'folder' ? '📂' : '📄' }}</div>
          <div class="card-title">{{ item.title }}</div>
          <div class="card-meta">{{ formatTime(item.updated_at || item.created_at) }}</div>
          <div v-if="item.doc_type !== 'folder' && item.quality_score != null" class="card-quality">
            {{ Math.round(item.quality_score) }} 分<template v-if="item.status && item.status !== 'active'"> ·
              草稿</template>
          </div>
        </div>
        <el-pagination v-if="total > pageSize" style="margin-top:16px;justify-content:center;width:100%" background
          layout="prev,pager,next" :total="total" :page-size="pageSize" v-model:current-page="page" @change="reload" />
      </div>
    </template>

    <!-- ============================================================ -->
    <!-- 预览视图 — 左侧目录 + 右侧 v-md-preview -->
    <!-- ============================================================ -->
    <div v-else-if="viewState === 'preview'" class="kb-preview-page">
      <div class="preview-header">
        <div class="preview-header-right">
          <el-tooltip v-if="previewMeta" placement="bottom" effect="light">
            <template #content>
              <div style="max-width:340px;line-height:1.7">
                发布标准：无「错误」级问题即可发布（必填章节齐全、正则可编译）。<br />
                质量分表示完整度：≥60 良好；40–59 可用但建议完善；低于 40 信息不足。
              </div>
            </template>
            <span class="preview-quality">
              质量分
              <b>{{ Math.round(previewMeta.quality_score) }}</b>
              <el-tag :type="previewMeta.status_hint === 'active' ? 'success' : 'warning'" size="small">
                {{ previewMeta.status_hint === 'active' ? '可发布' : '待完善' }}
              </el-tag>
            </span>
          </el-tooltip>
          <el-button @click="closePreview">关闭预览</el-button>
          <el-button v-if="canManage" type="primary" @click="enterEdit">编辑</el-button>
        </div>
      </div>
      <div class="preview-layout">
        <!-- 右侧预览（正文全宽） -->
        <div class="preview-body" @scroll.passive="onPreviewScroll">
          <component :is="VMdEditor.Preview" :text="form.content" />
        </div>
        <!-- 右侧悬浮目录（docsify 风格） -->
        <nav v-if="tocItems.length" class="toc-float" :class="{ 'toc-float-expanded': tocHovered }"
          @mouseenter="tocHovered = true" @mouseleave="tocHovered = false">
          <button class="toc-float-toggle" @click="tocHovered = !tocHovered" title="目录">
            <span class="toc-float-dot" :style="{ top: tocProgress + '%' }" />
          </button>
          <div class="toc-float-panel">
            <div class="toc-float-title">目录</div>
            <div v-for="(item, i) in tocItems" :key="i" class="toc-item" :class="[
              { 'toc-active': activeTocId === item.anchorId },
              `toc-level-${item.level}`,
            ]" @click="scrollToTocAnchor(item.anchorId)">{{ item.text }}</div>
          </div>
        </nav>
      </div>
    </div>

    <!-- ============================================================ -->
    <!-- 编辑视图 -->
    <!-- ============================================================ -->
    <div v-else-if="viewState === 'edit'" class="kb-editor-page">
      <div class="kb-header">
        <div class="title-field">
          <el-input ref="titleInputRef" v-model="form.title" placeholder="标题（必填）"
            style="width:240px;font-size:18px;font-weight:600" @input="titleError = ''" />
          <div v-if="titleError" class="field-error">{{ titleError }}</div>
        </div>
        <el-select v-model="form.doc_type" style="width:170px;margin-left:8px" @change="onDocTypeChange">
          <el-option label="现场问题示例" value="case" />
          <el-option label="FAQ" value="faq" />
          <el-option label="代码逻辑" value="code_logic" />
          <el-option label="基础知识" value="knowledge" />
          <el-option label="笔记" value="note" />
          <el-option label="手册" value="manual" />
        </el-select>
        <div style="margin-left:auto;display:flex;gap:8px;align-items:center">
          <el-button v-if="polishSnapshot === null" @click="aiPolish" :loading="polishing"
            :disabled="polishing">AI润色</el-button>
          <el-button v-else type="warning" plain @click="undoPolish">撤销AI润色</el-button>
          <el-button @click="showGuide = true">格式说明</el-button>
          <el-button @click="cancelEdit">取消</el-button>
          <el-button type="primary" @click="save" :loading="saving">{{ editingId ? '保存' : '创建' }}</el-button>
        </div>
      </div>
      <div class="editor-body">
        <div v-if="polishing" class="polish-overlay">
          <div class="polish-spin" />
          <div class="polish-title">AI 润色中…</div>
          <div class="polish-elapsed">已用时 {{ polishElapsed }} 秒</div>
          <!-- <div class="polish-tip">内容较多时可能需要 1~2 分钟，请耐心等待</div> -->
          <el-button size="small" @click="cancelPolish">取消润色</el-button>
        </div>
        <div class="editor-pane" @contextmenu="onEditorContextMenu">
          <v-md-editor :key="editorKey" ref="editorRef" v-model="form.content" height="100%"
            left-toolbar="undo redo | bold italic strikethrough | h2 h3 h4 | ul ol | link image | code quote | table hr | fullscreen"
            right-toolbar="kb-quality preview toc | sync-scroll fullscreen" :toolbar="editorToolbar"
            :disabled-menus="[]" @upload-image="handleUploadImage" />
        </div>
      </div>
    </div>

    <!-- ============================================================ -->
    <!-- 弹窗 -->
    <!-- ============================================================ -->
    <el-dialog v-model="showUpload" title="上传文件" width="480px">
      <el-upload drag :auto-upload="false" :on-change="handleFileSelect" accept=".md,.txt,.pdf">
        <el-icon :size="40">
          <UploadFilled />
        </el-icon>
        <div style="margin-top:8px">拖拽文件或点击上传</div>
        <template #tip>
          <div style="margin-top:8px;color:var(--el-text-color-secondary)">支持 .md, .txt, .pdf</div>
        </template>
      </el-upload>
      <div style="margin-top:12px">
        <el-select v-model="uploadForm.doc_type" style="width:100%">
          <el-option label="手册" value="manual" /><el-option label="FAQ" value="faq" /><el-option label="数据手册"
            value="datasheet" />
        </el-select>
      </div>
      <template #footer><el-button @click="showUpload = false">取消</el-button><el-button type="primary" @click="doUpload"
          :loading="uploading">上传</el-button></template>
    </el-dialog>

    <el-dialog v-model="showFolder" title="新建文件夹" width="400px">
      <el-input v-model="folderName" placeholder="文件夹名称" />
      <template #footer><el-button @click="showFolder = false">取消</el-button><el-button type="primary"
          @click="createFolder">创建</el-button></template>
    </el-dialog>

    <el-dialog v-model="showRename" title="重命名" width="400px">
      <el-input v-model="renameName" placeholder="新名称" />
      <template #footer><el-button @click="showRename = false">取消</el-button><el-button type="primary"
          @click="doRename">确认</el-button></template>
    </el-dialog>

    <el-dialog v-model="showGuide" :title="guideTitle" width="820px" top="6vh">
      <div v-if="editingTemplate" class="guide-body">
        <el-form label-width="92px" label-position="left">
          <el-form-item label="类型名称">
            <el-input v-model="templateDraft.name" size="small" />
          </el-form-item>
          <el-form-item label="格式说明">
            <el-input v-model="templateDraft.guide" type="textarea" :rows="2" placeholder="给用户的格式填写说明" />
          </el-form-item>
          <el-form-item label="结构项">
            <div class="template-sections">
              <div v-for="(section, index) in templateDraft.sections" :key="index" class="template-section-row">
                <el-input v-model="section.title" placeholder="章节名称" size="small" style="width:170px" />
                <el-input v-model="section.key" placeholder="键（可留空）" size="small" style="width:150px" />
                <el-select v-model="section.level" size="small" style="width:110px">
                  <el-option label="必填" value="required" />
                  <el-option label="建议" value="recommended" />
                  <el-option label="可选" value="optional" />
                </el-select>
                <el-button size="small" type="danger" text :disabled="templateDraft.sections.length <= 1"
                  @click="removeTemplateSection(index)">删除</el-button>
              </div>
              <el-button size="small" @click="addTemplateSection">+ 新增结构项</el-button>
            </div>
          </el-form-item>
          <el-form-item label="模板骨架">
            <el-input v-model="templateDraft.skeleton" type="textarea" :rows="5" placeholder="新建时预填的 Markdown 骨架" />
          </el-form-item>
          <el-form-item label="填写示例">
            <el-input v-model="templateDraft.example" type="textarea" :rows="4" placeholder="示例 Markdown" />
          </el-form-item>
        </el-form>
      </div>
      <div v-else-if="currentTemplate" class="guide-body">
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
      <div v-if="!editingTemplate" class="guide-body">
        <h4>发布标准</h4>
        <p class="guide-text">无「错误」级问题即可发布（必填章节齐全、正则可编译）。质量分表示完整度：≥60 良好，40–59 可用但建议完善，低于 40 信息不足。</p>
      </div>
      <template #footer>
        <template v-if="editingTemplate">
          <el-button @click="editingTemplate = false">取消</el-button>
          <el-button :loading="savingTemplate" @click="resetTemplate">恢复默认</el-button>
          <el-button type="primary" :loading="savingTemplate" @click="saveTemplate">保存格式</el-button>
        </template>
        <template v-else>
          <el-button @click="showGuide = false">关闭</el-button>
          <el-button v-if="currentTemplate" @click="startEditTemplate">编辑格式</el-button>
          <el-button type="primary" @click="insertSkeleton">追加模板骨架</el-button>
        </template>
      </template>
    </el-dialog>

    <!-- 创建前实时校验 -->
    <el-dialog v-model="showValidation" title="创建前检查" width="620px">
      <div class="validation-body">
        <div class="validation-row">
          <span class="validation-label">标题</span>
          <span class="validation-ok">已填写</span>
        </div>
        <div class="validation-row">
          <span class="validation-label">格式要求</span>
          <span class="validation-value">{{ validationGuide?.guide || '自由格式：建议使用小标题分节、条目化表达' }}</span>
        </div>
        <div v-if="requiredSections.length" class="validation-row">
          <span class="validation-label">必填结构项</span>
          <span class="validation-value">{{ requiredSections.join('、') }}</span>
        </div>
        <div class="validation-row">
          <span class="validation-label">检查结果</span>
          <span v-if="!validationIssues.length" class="validation-ok">通过</span>
          <span v-else class="validation-value">{{ validationIssues.length }} 条提示</span>
        </div>
        <ul v-if="validationIssues.length" class="validation-issues">
          <li v-for="(issue, i) in validationIssues" :key="i" :class="issue.level">
            {{ issue.level === 'error' ? '✕' : '⚠' }} {{ issue.message }}
          </li>
        </ul>
      </div>
      <template #footer>
        <el-button @click="showValidation = false">返回修改</el-button>
        <el-button type="primary" :loading="saving" @click="confirmCreate">继续创建</el-button>
      </template>
    </el-dialog>

    <!-- 编辑器选中文本右键菜单 -->
    <div v-if="selectionMenu.visible" class="selection-menu"
      :style="{ left: selectionMenu.x + 'px', top: selectionMenu.y + 'px' }" @mousedown.stop>
      <div class="selection-menu-title">已选中 {{ selectionMenu.text.length }} 字</div>
      <button class="selection-menu-item" :disabled="selectionPolishing" @click="runSelectionPolish('replace')">
        {{ selectionPolishing ? 'AI 润色中…' : 'AI润色（替换）' }}
      </button>
      <button class="selection-menu-item" :disabled="selectionPolishing" @click="runSelectionPolish('append')">
        AI润色（追加）
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount, computed, nextTick, watch, defineComponent, h } from 'vue'
import { Search, UploadFilled } from '@element-plus/icons-vue'
import { knowledgeApi, type KnowledgeTemplateInfo } from '@/api/knowledge'
import { useUserStore } from '@/stores/user'
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

// ── 提交后检查（质量分/可发布状态显示在编辑器工具栏“预览”开关左侧） / AI 润色 / 模板说明 ──
const previewResult = ref<any>(null)
const previewMeta = ref<any>(null)

/** 质量分/可发布状态文本（随编辑内容实时刷新） */
const previewQualityText = computed(() => {
  const r = previewResult.value
  if (!r || r.quality_score == null) return '质量分 —'
  return `质量分 ${Math.round(r.quality_score)} · ${r.status_hint === 'active' ? '可发布' : '待完善'}`
})

/** 状态配色 class：可发布=绿色，待完善=橙色 */
const previewQualityClass = computed(() => {
  const r = previewResult.value
  if (!r || r.quality_score == null) return 'kb-quality-chip'
  return r.status_hint === 'active' ? 'kb-quality-chip kb-quality-ok' : 'kb-quality-chip kb-quality-draft'
})

/** v-md-editor 自定义工具栏项：质量分/可发布状态，显示在“预览”开关左侧（预览与目录导航按钮相邻） */
const editorToolbar = {
  'kb-quality': {
    name: 'kb-quality',
    icon: () => previewQualityClass.value,
    text: () => previewQualityText.value,
  },
}
const titleInputRef = ref<any>(null)
const titleError = ref('')
const showValidation = ref(false)
const validationIssues = ref<any[]>([])
const validationGuide = ref<any>(null)
const selectionMenu = ref({ visible: false, x: 0, y: 0, text: '', start: 0, end: 0 })
const selectionPolishing = ref(false)
const polishing = ref(false)
const polishSnapshot = ref<string | null>(null)
const polishElapsed = ref(0)
let polishTimer: ReturnType<typeof setInterval> | null = null
let polishAbort: AbortController | null = null
const editorKey = ref(0)  // 整体替换编辑内容时重建编辑器，避免内容追加/不同步
const templates = ref<KnowledgeTemplateInfo[]>([])
const showGuide = ref(false)
const editingTemplate = ref(false)
const savingTemplate = ref(false)
const templateDraft = ref<{
  name: string
  guide: string
  skeleton: string
  example: string
  sections: Array<{ title: string; key: string; level: string }>
}>({ name: '', guide: '', skeleton: '', example: '', sections: [] })
let previewTimer: ReturnType<typeof setTimeout> | null = null

const currentTemplate = computed(
  () => templates.value.find(t => t.doc_type === form.value.doc_type) || null,
)
const requiredSections = computed(() =>
  (currentTemplate.value?.sections || [])
    .filter(section => section.level === 'required')
    .map(section => section.title),
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
  // 模板接口仅管理员可读：普通用户走进来会 403，直接跳过
  if (!canManage.value) return
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

/** 整体替换编辑器内容（重建 v-md-editor，避免追加或不同步） */
function replaceEditorContent(text: string) {
  form.value.content = text
  editorKey.value += 1
  selectionMenu.value.visible = false
  nextTick(() => refreshPreview())
}

/** 局部替换编辑器文本：直接写入 textarea（不重建编辑器），保持滚动位置与光标 */
function spliceEditorText(start: number, end: number, insert: string) {
  const textarea = document.querySelector('.v-md-textarea-editor textarea') as HTMLTextAreaElement | null
  const content = form.value.content
  const merged = content.slice(0, start) + insert + content.slice(end)
  if (!textarea) {
    replaceEditorContent(merged) // 兜底：找不到编辑区时整体替换
    return
  }
  const nativeSetter = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value')?.set
  if (nativeSetter) {
    nativeSetter.call(textarea, merged)
  } else {
    textarea.value = merged
  }
  // 触发 input 事件让 v-model 同步
  textarea.dispatchEvent(new Event('input', { bubbles: true }))
  textarea.setSelectionRange(start + insert.length, start + insert.length)
}

/** 预览页质量分/可发布状态（进入预览时实时计算） */
async function loadPreviewMeta() {
  if (!form.value.content) {
    previewMeta.value = null
    return
  }
  try {
    const { data } = await knowledgeApi.formatPreview({
      content: form.value.content,
      doc_type: form.value.doc_type,
      title: form.value.title,
    })
    previewMeta.value = data
  } catch {
    previewMeta.value = null
  }
}

function closePreview() {
  viewState.value = 'list'
  editingId.value = null
  fetch()
}

// ── 编辑器选中文本右键菜单 ──
function onEditorContextMenu(event: MouseEvent) {
  const target = event.target as HTMLElement
  const textarea = target.closest('textarea') as HTMLTextAreaElement | null
  if (!textarea) return
  const start = textarea.selectionStart ?? 0
  const end = textarea.selectionEnd ?? 0
  if (start === end) return  // 无选区时保留浏览器原生菜单
  const text = textarea.value.slice(start, end)
  if (!text.trim()) return
  event.preventDefault()
  selectionMenu.value = {
    visible: true,
    x: Math.min(event.clientX, window.innerWidth - 230),
    y: Math.min(event.clientY, window.innerHeight - 140),
    text,
    start,
    end,
  }
}

function closeSelectionMenu() {
  selectionMenu.value.visible = false
}

function onGlobalMouseDown(event: MouseEvent) {
  if (!selectionMenu.value.visible) return
  const target = event.target as HTMLElement | null
  if (target?.closest('.selection-menu')) return
  closeSelectionMenu()
}

function onGlobalKeyDown(event: KeyboardEvent) {
  if (event.key === 'Escape' && selectionMenu.value.visible) {
    closeSelectionMenu()
  }
}

/** 选中文本所属章节（选区之前的最近一个 Markdown 标题），用于对齐格式说明 */
function sectionHeadingFor(content: string, index: number): string {
  const lines = content.slice(0, Math.max(0, index)).split('\n')
  for (let i = lines.length - 1; i >= 0; i--) {
    const matched = lines[i].match(/^(#{1,6})\s+(.+?)\s*$/)
    if (matched) return `${matched[1]} ${matched[2]}`.trim()
  }
  return ''
}

/** 仅润色选中文本：替换选区或追加到选区之后 */
async function runSelectionPolish(mode: 'replace' | 'append') {
  if (selectionPolishing.value) return
  const selected = selectionMenu.value
  if (!selected.visible || !selected.text.trim()) return
  selectionPolishing.value = true
  try {
    const { data } = await knowledgeApi.polishSelection({
      content: selected.text,
      doc_type: form.value.doc_type,
      title: form.value.title,
      section: sectionHeadingFor(form.value.content, selected.start),
    })
    const polished = (data.polished_content || '').trim()
    const original = selected.text
    closeSelectionMenu()
    if (!polished || polished === original.trim()) {
      const notes: string[] = Array.isArray(data.notes) ? data.notes : []
      ElMessage.info(notes[0] || '选中文本无需调整')
      return
    }
    const content = form.value.content
    const start = Math.min(selected.start, content.length)
    const end = Math.min(selected.end, content.length)
    if (mode === 'replace') {
      spliceEditorText(start, end, polished)
    } else {
      const needsNewline = end > 0 && content[end - 1] !== '\n'
      spliceEditorText(end, end, (needsNewline ? '\n\n' : '') + polished)
    }
    polishSnapshot.value = null
    ElMessage.success(mode === 'replace' ? '已替换为 AI 润色结果' : '已在选中内容后追加 AI 润色结果')
  } catch (e: any) {
    ElMessage.error('选区润色失败: ' + (e?.response?.data?.detail || e?.message))
  } finally {
    selectionPolishing.value = false
  }
}

function startEditTemplate() {
  if (!currentTemplate.value) return
  templateDraft.value = {
    name: currentTemplate.value.name,
    guide: currentTemplate.value.guide,
    skeleton: currentTemplate.value.skeleton,
    example: currentTemplate.value.example,
    sections: currentTemplate.value.sections.map(section => ({
      title: section.title,
      key: section.key,
      level: section.level,
    })),
  }
  editingTemplate.value = true
}

function addTemplateSection() {
  templateDraft.value.sections.push({ title: '', key: '', level: 'optional' })
}

function removeTemplateSection(index: number) {
  templateDraft.value.sections.splice(index, 1)
}

async function saveTemplate() {
  if (!currentTemplate.value) return
  const sections = templateDraft.value.sections.filter(section => section.title.trim())
  if (!sections.length) {
    ElMessage.warning('至少保留一个结构项')
    return
  }
  savingTemplate.value = true
  try {
    await knowledgeApi.updateTemplate(currentTemplate.value.doc_type, {
      name: templateDraft.value.name,
      guide: templateDraft.value.guide,
      skeleton: templateDraft.value.skeleton,
      example: templateDraft.value.example,
      sections,
    })
    await loadTemplates()
    editingTemplate.value = false
    ElMessage.success('格式说明已保存')
  } catch (e: any) {
    ElMessage.error('保存失败: ' + (e?.response?.data?.detail || e?.message))
  } finally {
    savingTemplate.value = false
  }
}

async function resetTemplate() {
  if (!currentTemplate.value) return
  try {
    await ElMessageBox.confirm(
      '恢复默认会清除该类型的自定义格式说明，确定继续？',
      '确认恢复',
      { type: 'warning', confirmButtonText: '恢复默认', cancelButtonText: '取消' },
    )
  } catch { return }
  savingTemplate.value = true
  try {
    await knowledgeApi.resetTemplate(currentTemplate.value.doc_type)
    await loadTemplates()
    editingTemplate.value = false
    ElMessage.success('已恢复默认格式说明')
  } catch (e: any) {
    ElMessage.error('恢复失败: ' + (e?.response?.data?.detail || e?.message))
  } finally {
    savingTemplate.value = false
  }
}

async function insertSkeleton() {
  const skeleton = skeletonFor(form.value.doc_type)
  if (!skeleton) {
    ElMessage.info('该类型为自由格式，没有固定模板')
    return
  }
  const hasContent = !!form.value.content.trim()
  if (hasContent) {
    try {
      await ElMessageBox.confirm(
        '将把模板骨架追加到当前编辑内容末尾（不会替换原有内容），确定继续？',
        '确认追加',
        { type: 'info', confirmButtonText: '追加', cancelButtonText: '取消' },
      )
    } catch { return }
  }
  polishSnapshot.value = null
  showGuide.value = false
  if (hasContent) {
    const merged = `${form.value.content.replace(/\s+$/, '')}\n\n${skeleton}`
    replaceEditorContent(merged)
    ElMessage.success('已将模板骨架追加到内容末尾')
  } else {
    replaceEditorContent(skeleton)
    ElMessage.success('已插入模板骨架')
  }
}

function schedulePreview() {
  if (previewTimer) clearTimeout(previewTimer)
  previewTimer = setTimeout(() => refreshPreview(), 500)
}

async function refreshPreview() {
  if (viewState.value !== 'edit') return
  try {
    const { data } = await knowledgeApi.formatPreview({
      content: form.value.content,
      doc_type: form.value.doc_type,
      title: form.value.title,
    })
    previewResult.value = data
  } catch (e: any) {
    console.warn('[KnowledgeBase] format preview failed:', e?.response?.data?.detail || e?.message || e)
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
  polishElapsed.value = 0
  polishAbort = new AbortController()
  polishTimer = setInterval(() => { polishElapsed.value += 1 }, 1000)
  try {
    const before = form.value.content
    const { data } = await knowledgeApi.polish({
      content: before,
      doc_type: form.value.doc_type,
      title: form.value.title,
    }, polishAbort.signal)
    const polished = data.polished_content || data.normalized_content || before
    if (polished === before) {
      ElMessage.info('内容已符合模板格式，无需润色')
      return
    }
    polishSnapshot.value = before
    replaceEditorContent(polished)
    if (data.source === 'llm') {
      ElMessage.success('AI 润色完成，已按模板规范化')
    } else {
      ElMessage.warning('AI 服务暂不可用（请检查 系统配置 → LLM 配置 的 API Key），已按模板规则完成结构化整理')
    }
  } catch (e: any) {
    if (e?.code === 'ERR_CANCELED' || e?.name === 'CanceledError') {
      ElMessage.info('已取消 AI 润色')
    } else {
      ElMessage.error('AI 润色失败: ' + (e?.response?.data?.detail || e?.message))
    }
  } finally {
    polishing.value = false
    polishAbort = null
    if (polishTimer) { clearInterval(polishTimer); polishTimer = null }
  }
}

function cancelPolish() {
  polishAbort?.abort()
}

function undoPolish() {
  if (polishSnapshot.value === null) return
  const original = polishSnapshot.value
  polishSnapshot.value = null
  replaceEditorContent(original)
  ElMessage.info('已撤销 AI 润色')
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

/** 知识库是「全员可读、管理员可写」：普通用户只做浏览与引用溯源 */
const userStore = useUserStore()
const canManage = computed(() => userStore.isAdmin)

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
    loadPreviewMeta()
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

// ============================================================
// 导航位置持久化 — 切换到对话等其他页面再回来时，恢复到上次浏览的目录
// ============================================================
const KB_NAV_STORAGE_KEY = 'kb:lastNavPath'

function saveNavState() {
  try {
    const path = folderPath.value.map((f: any) => ({ id: f.id, title: f.title, doc_type: f.doc_type }))
    sessionStorage.setItem(KB_NAV_STORAGE_KEY, JSON.stringify(path))
  } catch { /* ignore */ }
}

function restoreNavState() {
  try {
    const raw = sessionStorage.getItem(KB_NAV_STORAGE_KEY)
    if (!raw) return
    const parsed = JSON.parse(raw)
    if (!Array.isArray(parsed) || !parsed.length) return
    folderPath.value = parsed.map((f: any) => ({ id: f.id, title: f.title, doc_type: f.doc_type || 'folder' }))
    currentFolder.value = folderPath.value[folderPath.value.length - 1] || null
  } catch { /* ignore */ }
}

/** 与文件夹树比对：若恢复的路径中有目录已不存在，则截断到最后一个有效目录 */
function validateRestoredPath() {
  if (!folderPath.value.length) return
  const validIds = new Set<number>()
  const walk = (nodes: any[]) => {
    for (const n of nodes) {
      validIds.add(n.id)
      if (n.children && n.children.length) walk(n.children)
    }
  }
  walk(folderTree.value)
  const kept: any[] = []
  for (const f of folderPath.value) {
    if (validIds.has(f.id)) kept.push(f)
    else break
  }
  if (kept.length === folderPath.value.length) return
  folderPath.value = kept
  currentFolder.value = kept.length ? kept[kept.length - 1] : null
  fetch()
}

watch([folderPath, currentFolder], () => saveNavState(), { deep: true })

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
  } catch { } finally { loading.value = false }
}
async function doSearch() {
  if (!searchQuery.value.trim()) { await fetch(); return }
  loading.value = true
  try {
    // 仅按文件名（标题）匹配搜索
    const { data } = await knowledgeApi.search(searchQuery.value, {
      page: page.value,
      page_size: pageSize,
      title_only: true,
    })
    items.value = data.items
    total.value = data.total
  } catch { } finally { loading.value = false }
}

// 输入即自动搜索（防抖 300ms）
let searchTimer: ReturnType<typeof setTimeout> | null = null
watch(searchQuery, () => {
  if (searchTimer) clearTimeout(searchTimer)
  searchTimer = setTimeout(() => { page.value = 1; doSearch() }, 300)
})

/** 列表刷新：有搜索词时按文件名搜索，否则列出当前目录 */
async function reload() {
  if (searchQuery.value.trim()) { await doSearch() } else { await fetch() }
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
      loadPreviewMeta()
    } else {
      form.value = { title: row.title, doc_type: row.doc_type || 'note', content: '' }
      loadDocumentContent(row.id)
    }
  }
}
function enterEdit() {
  polishSnapshot.value = null
  viewState.value = 'edit'
  nextTick(() => refreshPreview())
}

// ============================================================
// 更多菜单操作
// ============================================================
async function handleRowAction(cmd: string, row: any) {
  if (cmd === 'edit') { form.value = { title: row.title, doc_type: row.doc_type || 'note', content: row.content || '' }; editingId.value = row.id; polishSnapshot.value = null; viewState.value = 'edit'; nextTick(() => refreshPreview()) }
  else if (cmd === 'rename') { renameId.value = row.id; renameName.value = row.title; showRename.value = true }
  else if (cmd === 'pin') {
    try {
      const newPinned = !row.is_pinned
      await knowledgeApi.update(row.id, { is_pinned: newPinned })
      ElMessage.success(newPinned ? '已置顶' : '已取消置顶')
      await fetch()
    } catch { ElMessage.error('操作失败') }
  }
  else if (cmd === 'copy') { await copyDocument(row) }
  else if (cmd === 'delete') { remove(row.id) }
}

/** 复制文档：内容一致，标题按「原名 (n)」递增编号，生成到当前目录 */
async function copyDocument(row: any) {
  try {
    const { data: doc } = await knowledgeApi.get(row.id)
    const baseTitle = String(doc.title || row.title || '').replace(/\s*\(\d+\)$/, '').trim()
    if (!baseTitle) { ElMessage.error('文档标题为空，无法复制'); return }

    // 扫描目录树中同名副本，取最大序号 +1
    let maxIndex = 0
    try {
      const { data: treeData } = await knowledgeApi.tree()
      const escaped = baseTitle.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
      const pattern = new RegExp(`^${escaped}\\s*\\((\\d+)\\)$`)
      const walk = (nodes: any[]) => {
        for (const node of nodes || []) {
          const matched = pattern.exec(String(node.title || ''))
          if (matched) maxIndex = Math.max(maxIndex, Number(matched[1]))
          if (node.children?.length) walk(node.children)
        }
      }
      walk(treeData?.tree || [])
    } catch { /* 树接口不可用时按首份副本处理 */ }

    const suffix = ` (${maxIndex + 1})`
    const title = baseTitle.slice(0, Math.max(1, 200 - suffix.length)) + suffix
    await knowledgeApi.create({
      title,
      content: doc.content || '',
      doc_type: doc.doc_type || 'note',
      category: doc.category ?? undefined,
      project_id: doc.project_id ?? undefined,
      parent_id: currentFolder.value?.id ?? undefined,
    })
    ElMessage.success(`已复制为「${title}」`)
    await fetch()
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '复制失败')
  }
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
  polishSnapshot.value = null
  viewState.value = 'edit'
  nextTick(() => refreshPreview())
}
function handleFileSelect(f: any) { uploadFile.value = f.raw }
async function doUpload() { if (!uploadFile.value) return; uploading.value = true; try { const fd = new FormData(); fd.append('file', uploadFile.value); fd.append('doc_type', uploadForm.value.doc_type); if (currentFolder.value) fd.append('parent_id', currentFolder.value.id.toString()); await knowledgeApi.upload(fd); ElMessage.success('上传成功'); showUpload.value = false; await fetch() } catch (e: any) { ElMessage.error(e?.response?.data?.detail || '上传失败') } finally { uploading.value = false } }
function createFolder() { if (!folderName.value.trim()) return; if (!checkPathDepth()) { showFolder.value = false; return } const data: any = { title: folderName.value, content: '', doc_type: 'folder' }; if (currentFolder.value) data.parent_id = currentFolder.value.id; knowledgeApi.create(data).then(() => { ElMessage.success('文件夹已创建'); showFolder.value = false; folderName.value = ''; fetch() }).catch(() => ElMessage.error('创建失败')) }

async function save() {
  if (!editingId.value) {
    // 新建：先做实时校验（标题必填 + 格式提示），通过后再弹确认
    await validateBeforeCreate()
    return
  }
  await doSave()
}

/** 创建前实时校验：标题必填 + 当前格式校验结果 */
async function validateBeforeCreate() {
  titleError.value = ''
  if (!form.value.title.trim()) {
    titleError.value = '标题为必填项，请填写标题后再创建'
    ElMessage.warning(titleError.value)
    titleInputRef.value?.focus?.()
    return
  }
  if (!form.value.content.trim()) {
    ElMessage.warning('内容不能为空')
    return
  }
  await refreshPreview()
  validationIssues.value = previewResult.value?.issues || []
  validationGuide.value = currentTemplate.value
  showValidation.value = true
}

async function confirmCreate() {
  showValidation.value = false
  await doSave()
}

async function doSave() {
  saving.value = true
  try {
    const data: any = { ...form.value }
    if (currentFolder.value) data.parent_id = currentFolder.value.id
    let resp: any = null
    if (editingId.value) {
      resp = (await knowledgeApi.update(editingId.value, data)).data
    } else {
      resp = (await knowledgeApi.create(data)).data
    }
    viewState.value = 'list'
    editingId.value = null
    polishSnapshot.value = null
    selectionMenu.value.visible = false
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
  restoreNavState()
  fetch()
  loadTree().then(validateRestoredPath)
  loadTemplates()
  document.addEventListener('mousedown', onGlobalMouseDown)
  document.addEventListener('keydown', onGlobalKeyDown)

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
  document.removeEventListener('mousedown', onGlobalMouseDown)
  document.removeEventListener('keydown', onGlobalKeyDown)
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
.kb-container {
  padding: 24px;
  margin: 0 auto;
  width: 100%;
  max-width: 1100px;
}

.kb-container.kb-full {
  max-width: none;
  padding: 24px 24px 0;
}

.kb-breadcrumb {
  margin-bottom: 16px;
}

.kb-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
}

.kb-header h2 {
  font-size: 20px;
  font-weight: 600;
  color: var(--kb-text);
  margin: 0;
}

.kb-header-right {
  display: flex;
  align-items: center;
  gap: 12px;
}

.kb-search {
  width: 280px;
}

.kb-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
  height: 36px;
}

.toolbar-left,
.toolbar-right {
  display: flex;
  align-items: center;
  gap: 8px;
}

.view-toggle .el-button {
  padding: 6px 12px;
}

.cell-name {
  display: flex;
  align-items: center;
  gap: 8px;
}

.file-icon {
  font-size: 18px;
  flex-shrink: 0;
}

.file-title {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.file-title:hover {
  text-decoration: underline;
}

.kb-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
  gap: 12px;
}

.kb-card {
  padding: 20px 16px;
  background: var(--kb-surface);
  border: 1px solid var(--kb-border);
  border-radius: 10px;
  cursor: pointer;
  transition: all 0.12s;
  text-align: center;
}

.kb-card:hover {
  border-color: var(--kb-link);
  box-shadow: 0 2px 12px var(--kb-shadow-accent);
}

.card-icon {
  font-size: 36px;
  margin-bottom: 8px;
}

.card-title {
  font-size: 13px;
  color: var(--kb-text);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  margin-bottom: 4px;
}

.card-meta {
  font-size: 11px;
  color: var(--kb-text-muted);
}

.kb-empty {
  text-align: center;
  padding: 80px 20px;
}

.empty-icon {
  font-size: 56px;
  margin-bottom: 16px;
  opacity: 0.5;
}

.empty-title {
  font-size: 18px;
  font-weight: 500;
  color: var(--kb-text-3);
  margin-bottom: 8px;
}

.empty-desc {
  font-size: 14px;
  color: var(--kb-text-muted);
}

/* 预览页 — 正文全宽 + 右侧悬浮目录 */
.preview-header {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  margin-bottom: 16px;
  flex-shrink: 0;
}

.preview-header-right {
  display: flex;
  align-items: center;
  gap: 8px;
}

.title-field {
  position: relative;
}

.field-error {
  position: absolute;
  top: 100%;
  left: 0;
  margin-top: 4px;
  font-size: 12px;
  color: var(--kb-danger);
  white-space: nowrap;
  z-index: 2;
}

.validation-body {
  display: flex;
  flex-direction: column;
  gap: 10px;
  font-size: 13px;
  color: var(--kb-text-2);
}

.validation-row {
  display: flex;
  gap: 10px;
  line-height: 1.7;
}

.validation-label {
  width: 84px;
  flex-shrink: 0;
  color: var(--kb-text-dim);
}

.validation-value {
  flex: 1;
  word-break: break-word;
}

.validation-ok {
  color: var(--kb-success);
  font-weight: 600;
}

.validation-issues {
  margin: 4px 0 0;
  padding-left: 18px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.validation-issues .error {
  color: var(--kb-danger);
}

.validation-issues .warn {
  color: var(--kb-warning);
}

.selection-menu {
  position: fixed;
  z-index: 3000;
  min-width: 210px;
  padding: 6px;
  background: var(--kb-surface);
  border: 1px solid var(--kb-border);
  border-radius: 8px;
  box-shadow: 0 8px 24px var(--kb-shadow-menu);
}

.selection-menu-title {
  padding: 4px 8px 6px;
  font-size: 12px;
  color: var(--kb-text-muted);
  border-bottom: 1px solid var(--kb-border-soft);
  margin-bottom: 4px;
}

.selection-menu-item {
  display: block;
  width: 100%;
  text-align: left;
  padding: 8px 10px;
  border: none;
  background: none;
  border-radius: 6px;
  font-size: 13px;
  color: var(--kb-text-2);
  cursor: pointer;
}

.selection-menu-item:hover:not(:disabled) {
  background: var(--kb-active-bg);
  color: var(--kb-active-text);
}

.selection-menu-item:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.template-sections {
  width: 100%;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.template-section-row {
  display: flex;
  align-items: center;
  gap: 8px;
}

.guide-body h4 {
  margin: 14px 0 8px;
  font-size: 14px;
  color: var(--kb-text);
}

.guide-body h4:first-child {
  margin-top: 0;
}

.guide-text {
  margin: 0;
  color: var(--kb-text-3);
  font-size: 13px;
  line-height: 1.8;
}

.guide-example {
  max-height: 320px;
  overflow-y: auto;
  padding: 12px 16px;
  background: var(--kb-surface-2);
  border: 1px solid var(--kb-border);
  border-radius: 8px;
  font-size: 13px;
  line-height: 1.7;
}

.preview-layout {
  position: relative;
  display: flex;
  gap: 0;
  height: calc(100vh - 180px);
}

.preview-body {
  flex: 1;
  overflow-y: auto;
  padding: 24px 48px 24px 24px;
  background: var(--kb-surface);
  border: 1px solid var(--kb-border);
  border-radius: 10px;
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
  /* 与 preview-body 右侧滚动条保持间距，避免遮挡滚动条影响操作 */
  right: 30px;
  top: 50%;
  transform: translateY(-50%);
  z-index: 10;
  display: flex;
  align-items: center;
}

/* 收起态的竖向进度条 */
.toc-float-toggle {
  position: relative;
  width: 3px;
  height: 120px;
  background: var(--kb-border);
  border: none;
  border-radius: 2px;
  cursor: pointer;
  padding: 0;
  transition: width 0.15s;
}

.toc-float-toggle:hover {
  width: 5px;
  background: var(--kb-border-2);
}

/* 当前阅读位置圆点 */
.toc-float-dot {
  position: absolute;
  left: 50%;
  top: 0;
  width: 9px;
  height: 9px;
  background: var(--kb-link);
  border-radius: 50%;
  transform: translate(-50%, -50%);
  box-shadow: 0 0 0 2px var(--kb-surface), 0 0 0 3px var(--kb-link);
  transition: top 0.2s ease;
  pointer-events: none;
}

/* 悬停展开的目录面板 */
.toc-float-panel {
  position: absolute;
  right: 16px;
  top: 50%;
  transform: translateY(-50%);
  width: 220px;
  max-height: 70vh;
  overflow-y: auto;
  background: var(--kb-surface);
  border: 1px solid var(--kb-border);
  border-radius: 8px;
  box-shadow: 0 8px 24px var(--kb-shadow-panel);
  padding: 8px 0;
  opacity: 0;
  visibility: hidden;
  transition: opacity 0.15s ease, visibility 0.15s;
}

.toc-float-expanded .toc-float-panel {
  opacity: 1;
  visibility: visible;
}

.toc-float-title {
  padding: 4px 14px 8px;
  font-size: 12px;
  font-weight: 600;
  color: var(--kb-text-muted);
  border-bottom: 1px solid var(--kb-border-soft);
  margin-bottom: 4px;
  letter-spacing: 0.5px;
}

.toc-item {
  padding: 5px 14px;
  font-size: 12px;
  color: var(--kb-text-dim);
  cursor: pointer;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  transition: background 0.1s, color 0.1s;
  line-height: 1.5;
}

.toc-item:hover {
  background: var(--kb-hover-bg);
  color: var(--kb-text-2);
}

/* 层级视觉：h1/h2/h3 不同缩进与字重 */
.toc-level-1 {
  font-weight: 600;
  color: var(--kb-text-2);
  padding-left: 14px;
}

.toc-level-2 {
  padding-left: 26px;
}

.toc-level-3 {
  padding-left: 38px;
  color: var(--kb-text-muted);
  font-size: 11px;
}

/* 当前阅读章节高亮 */
.toc-active {
  color: var(--kb-active-text);
  background: var(--kb-active-bg);
  border-left: 2px solid var(--kb-active-text);
  font-weight: 600;
}

.toc-level-1.toc-active {
  padding-left: 12px;
}

.toc-level-2.toc-active {
  padding-left: 24px;
}

.toc-level-3.toc-active {
  padding-left: 36px;
}

/* 移动端：隐藏悬浮目录，改为全宽阅读 */
@media (max-width: 768px) {
  .toc-float {
    display: none;
  }

  .preview-body {
    padding: 16px;
  }
}

.kb-editor-page {
  display: flex;
  flex-direction: column;
  height: calc(100vh - 140px);
}

.editor-body {
  flex: 1;
  min-height: 0;
  display: flex;
  gap: 12px;
  position: relative;
}

.polish-overlay {
  position: absolute;
  inset: 0;
  z-index: 20;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 10px;
  background: var(--kb-overlay-bg);
  border-radius: 8px;
}

.polish-spin {
  width: 36px;
  height: 36px;
  border: 3px solid var(--kb-border);
  border-top-color: var(--kb-spinner-head);
  border-radius: 50%;
  animation: polish-rotate 0.9s linear infinite;
}

@keyframes polish-rotate {
  to {
    transform: rotate(360deg);
  }
}

.polish-title {
  font-size: 15px;
  font-weight: 600;
  color: var(--el-text-color-primary);
}

.polish-elapsed {
  font-size: 13px;
  color: var(--el-text-color-regular);
}

.polish-tip {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.editor-pane {
  flex: 1;
  min-width: 0;
  height: 100%;
  border: 1px solid var(--kb-border);
  border-radius: 8px;
  overflow: hidden;
}

.preview-quality {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  color: var(--kb-text-dim);
}

/* 编辑器工具栏中的质量分/可发布状态（“预览”开关左侧） */
.editor-pane :deep(.v-md-editor__toolbar-item-kb-quality) {
  cursor: default;
  font-size: 12px;
  color: var(--kb-text-dim);
  max-width: none;
}

.editor-pane :deep(.v-md-editor__toolbar-item-kb-quality:hover) {
  background: transparent;
}

/* 质量分项不显示悬浮提示 */
.editor-pane :deep(.v-md-editor__toolbar-item-kb-quality .v-md-editor__tooltip) {
  display: none !important;
}

.editor-pane :deep(.kb-quality-ok) {
  color: var(--kb-success);
  font-weight: 600;
}

.editor-pane :deep(.kb-quality-draft) {
  color: var(--kb-warning);
  font-weight: 600;
}

.card-quality {
  font-size: 11px;
  color: var(--kb-link);
  margin-top: 4px;
}

.md-preview {
  padding: 16px 20px;
  font-size: 14px;
  line-height: 1.8;
}

.md-preview :deep(h2) {
  font-size: 18px;
  margin: 16px 0 8px;
}

.md-preview :deep(h3) {
  font-size: 15px;
  margin: 12px 0 6px;
}

.md-preview :deep(p) {
  margin: 6px 0;
}

.md-preview :deep(code) {
  background: var(--kb-surface-3);
  padding: 2px 6px;
  border-radius: 4px;
  font-size: 13px;
}

.md-preview :deep(pre) {
  background: var(--kb-code-block-bg);
  color: var(--kb-code-block-text);
  padding: 12px 16px;
  border-radius: 8px;
  overflow-x: auto;
}

.md-preview :deep(pre code) {
  background: none;
  padding: 0;
  color: inherit;
}

.md-preview :deep(blockquote) {
  border-left: 3px solid var(--kb-border-2);
  padding-left: 12px;
  color: var(--kb-text-dim);
  margin: 8px 0;
}

.md-preview :deep(table) {
  border-collapse: collapse;
  width: 100%;
  margin: 12px 0;
}

.md-preview :deep(th),
.md-preview :deep(td) {
  border: 1px solid var(--kb-border-2);
  padding: 8px 12px;
  text-align: left;
  font-size: 13px;
}

.md-preview :deep(th) {
  background: var(--kb-surface-3);
  font-weight: 600;
}

.md-preview :deep(tr:nth-child(even)) {
  background: var(--kb-zebra);
}

/* 更多按钮 */
.row-more-btn {
  width: 28px;
  height: 28px;
  border-radius: 6px;
  border: none;
  background: transparent;
  color: var(--kb-text-muted);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: background 0.12s;
}

.row-more-btn:hover {
  background: var(--kb-hover-bg-strong);
  color: var(--kb-text-2);
}
</style>

<style>
/* ==========================================================================
   知识库本地主题 token（浅色为默认值，深色随 html[data-theme='dark'] 切换）
   弹窗内容经 el-dialog teleport 到 body，无法继承 .kb-container 上的变量，
   因此 token 同时定义在弹窗内容根节点（.guide-body / .validation-body）上。
   ========================================================================== */
.kb-container,
.guide-body,
.validation-body {
  --kb-text: #1f2937;
  --kb-text-2: #374151;
  --kb-text-3: #4b5563;
  --kb-text-muted: #9ca3af;
  --kb-text-dim: #6b7280;
  --kb-surface: #fff;
  --kb-surface-2: #f9fafb;
  --kb-surface-3: #f3f4f6;
  --kb-border: #e5e7eb;
  --kb-border-2: #d1d5db;
  --kb-border-soft: #f3f4f6;
  --kb-hover-bg: #f3f4f6;
  --kb-hover-bg-strong: #e5e7eb;
  --kb-link: #2563eb;
  --kb-active-text: #2563eb;
  --kb-active-bg: #eff6ff;
  --kb-danger: #dc2626;
  --kb-warning: #d97706;
  --kb-success: #059669;
  --kb-zebra: #fafafa;
  --kb-code-block-bg: #1f2937;
  --kb-code-block-text: #f9fafb;
  --kb-overlay-bg: rgba(255, 255, 255, 0.85);
  --kb-spinner-head: #409eff;
  --kb-shadow-accent: rgba(37, 99, 235, 0.08);
  --kb-shadow-menu: rgba(0, 0, 0, 0.12);
  --kb-shadow-panel: rgba(0, 0, 0, 0.08);
}

html[data-theme='dark'] .kb-container,
html[data-theme='dark'] .guide-body,
html[data-theme='dark'] .validation-body {
  --kb-text: #e7e9ee;
  --kb-text-2: #dfe2e8;
  --kb-text-3: #c2c7d0;
  --kb-text-muted: #9298a5;
  --kb-text-dim: #aeb4c0;
  --kb-surface: #222326;
  --kb-surface-2: #292a2e;
  --kb-surface-3: #2c2d31;
  --kb-border: #35363b;
  --kb-border-2: #4a4c52;
  --kb-border-soft: #34353a;
  --kb-hover-bg: #393a40;
  --kb-hover-bg-strong: #3a3b40;
  --kb-link: #9fb3ff;
  --kb-active-text: #aebfff;
  --kb-active-bg: #303a5b;
  --kb-danger: #f87171;
  --kb-warning: #fbbf24;
  --kb-success: #34d399;
  --kb-zebra: #26272a;
  --kb-code-block-bg: #242528;
  --kb-code-block-text: #f3f4f6;
  --kb-overlay-bg: rgba(23, 23, 25, 0.88);
  --kb-spinner-head: #6688fa;
  --kb-shadow-accent: rgba(0, 0, 0, 0.4);
  --kb-shadow-menu: rgba(0, 0, 0, 0.45);
  --kb-shadow-panel: rgba(0, 0, 0, 0.45);
}

/* ==========================================================================
   深色主题 — v-md-editor（vuepress 主题）正文内容
   主题自带浅色背景/文字（#fff / #2c3e50），在深色面板上需覆盖
   ========================================================================== */
html[data-theme='dark'] .kb-container .vuepress-markdown-body,
html[data-theme='dark'] .guide-body .vuepress-markdown-body {
  color: var(--kb-text-2);
  background-color: transparent;
}

html[data-theme='dark'] .kb-container .vuepress-markdown-body :is(h1, h2, h3, h4, h5, h6),
html[data-theme='dark'] .guide-body .vuepress-markdown-body :is(h1, h2, h3, h4, h5, h6) {
  color: var(--kb-text);
}

html[data-theme='dark'] .kb-container .vuepress-markdown-body :is(h1, h2),
html[data-theme='dark'] .guide-body .vuepress-markdown-body :is(h1, h2) {
  border-bottom-color: var(--kb-border-soft);
}

html[data-theme='dark'] .kb-container .vuepress-markdown-body blockquote,
html[data-theme='dark'] .guide-body .vuepress-markdown-body blockquote {
  color: var(--kb-text-dim);
  border-left-color: var(--kb-border-2);
}

html[data-theme='dark'] .kb-container .vuepress-markdown-body hr,
html[data-theme='dark'] .guide-body .vuepress-markdown-body hr {
  border-top-color: var(--kb-border-soft);
}

html[data-theme='dark'] .kb-container .vuepress-markdown-body :is(th, td),
html[data-theme='dark'] .guide-body .vuepress-markdown-body :is(th, td) {
  border-color: var(--kb-border-2);
}

html[data-theme='dark'] .kb-container .vuepress-markdown-body th,
html[data-theme='dark'] .guide-body .vuepress-markdown-body th {
  background-color: var(--kb-surface-3);
}

html[data-theme='dark'] .kb-container .vuepress-markdown-body img,
html[data-theme='dark'] .guide-body .vuepress-markdown-body img {
  border-color: var(--kb-border);
}

/* ==========================================================================
   深色主题 — v-md-editor 编辑器外壳（工具栏 / 菜单 / CodeMirror）
   ========================================================================== */
html[data-theme='dark'] .kb-container .v-md-editor,
html[data-theme='dark'] .kb-container .v-md-editor__editor-wrapper,
html[data-theme='dark'] .kb-container .CodeMirror {
  background: var(--kb-surface);
  color: var(--kb-text-2);
}

html[data-theme='dark'] .kb-container .v-md-editor__toolbar {
  background: var(--kb-surface);
  border-bottom-color: var(--kb-border);
}

html[data-theme='dark'] .kb-container .v-md-editor__toolbar-item {
  color: var(--kb-text-dim);
}

html[data-theme='dark'] .kb-container .v-md-editor__toolbar-item:hover {
  background: var(--kb-hover-bg);
}

html[data-theme='dark'] .kb-container .v-md-editor__toolbar-item--active,
html[data-theme='dark'] .kb-container .v-md-editor__toolbar-item--active:hover {
  background: var(--kb-hover-bg-strong);
}

html[data-theme='dark'] .kb-container .v-md-editor__menu {
  background: var(--kb-surface);
}

html[data-theme='dark'] .kb-container .v-md-editor__menu-item {
  color: var(--kb-text-2);
}

html[data-theme='dark'] .kb-container .v-md-editor__menu-item:hover {
  background: var(--kb-hover-bg);
}

html[data-theme='dark'] .kb-container .v-md-editor__left-area {
  background: var(--kb-surface-2);
}

html[data-theme='dark'] .kb-container .v-md-editor__left-area-title {
  color: var(--kb-text-dim);
}

html[data-theme='dark'] .kb-container .CodeMirror-gutters {
  background: var(--kb-surface);
  border-right-color: var(--kb-border);
}

html[data-theme='dark'] .kb-container .CodeMirror-cursor {
  border-left-color: var(--kb-text-2);
}

html[data-theme='dark'] .kb-container .CodeMirror-selected {
  background: var(--kb-active-bg);
}

html[data-theme='dark'] .kb-container .CodeMirror-empty {
  color: var(--kb-text-dim);
}

/* ==========================================================================
   深色主题 — 编辑器输入区
   textarea 模式默认使用 #2c3e50 深色字，深色底上几乎不可读
   ========================================================================== */
html[data-theme='dark'] .kb-container .v-md-textarea-editor,
html[data-theme='dark'] .kb-container .v-md-textarea-editor pre,
html[data-theme='dark'] .kb-container .v-md-textarea-editor textarea {
  background-color: var(--kb-surface);
  color: var(--kb-text);
  caret-color: #ffffff;
}

html[data-theme='dark'] .kb-container .v-md-textarea-editor textarea::placeholder {
  color: var(--kb-text-muted);
}

/* ==========================================================================
   深色主题 — Markdown 目录导航（悬浮目录 + 编辑器内置目录面板）
   ========================================================================== */
html[data-theme='dark'] .kb-container .toc-float-title {
  color: #b9bec8;
}

html[data-theme='dark'] .kb-container .toc-item {
  color: #dfe2e8;
}

html[data-theme='dark'] .kb-container .toc-level-1 {
  color: #eef0f4;
}

html[data-theme='dark'] .kb-container .toc-level-3 {
  color: #c9ced8;
}

html[data-theme='dark'] .kb-container .toc-item:hover {
  background: var(--kb-hover-bg);
  color: #ffffff;
}

html[data-theme='dark'] .kb-container .toc-active,
html[data-theme='dark'] .kb-container .toc-active:hover {
  color: #cdd7ff;
}

html[data-theme='dark'] .kb-container .v-md-editor__toc-nav {
  background-color: var(--kb-surface);
}

html[data-theme='dark'] .kb-container .v-md-editor__toc-nav-item {
  color: var(--kb-text-2);
}

html[data-theme='dark'] .kb-container .v-md-editor__toc-nav-item:hover {
  color: #ffffff;
}

/* ==========================================================================
   深色主题 — 预览表格
   覆盖 vuepress 主题的浅色边框、浅色斑马纹（#f6f8fa）与表头
   ========================================================================== */
html[data-theme='dark'] .kb-container .vuepress-markdown-body table,
html[data-theme='dark'] .guide-body .vuepress-markdown-body table {
  background-color: transparent;
}

html[data-theme='dark'] .kb-container .vuepress-markdown-body tr,
html[data-theme='dark'] .guide-body .vuepress-markdown-body tr {
  border-top-color: var(--kb-border-2);
  background-color: transparent;
}

html[data-theme='dark'] .kb-container .vuepress-markdown-body tr:nth-child(2n),
html[data-theme='dark'] .guide-body .vuepress-markdown-body tr:nth-child(2n) {
  background-color: var(--kb-zebra);
}

html[data-theme='dark'] .kb-container .vuepress-markdown-body :is(th, td),
html[data-theme='dark'] .guide-body .vuepress-markdown-body :is(th, td) {
  border-color: var(--kb-border-2);
  color: var(--kb-text-2);
}

html[data-theme='dark'] .kb-container .vuepress-markdown-body th,
html[data-theme='dark'] .guide-body .vuepress-markdown-body th {
  background-color: var(--kb-surface-3);
  color: var(--kb-text);
}

/* ==========================================================================
   深色主题 — 代码块（提升文字对比度）
   ========================================================================== */
html[data-theme='dark'] .kb-container .vuepress-markdown-body pre,
html[data-theme='dark'] .guide-body .vuepress-markdown-body pre,
html[data-theme='dark'] .kb-container .vuepress-markdown-body pre[class*='v-md-prism-'],
html[data-theme='dark'] .guide-body .vuepress-markdown-body pre[class*='v-md-prism-'] {
  background-color: var(--kb-code-block-bg);
  color: var(--kb-code-block-text);
}

html[data-theme='dark'] .kb-container .vuepress-markdown-body pre code,
html[data-theme='dark'] .guide-body .vuepress-markdown-body pre code,
html[data-theme='dark'] .kb-container .vuepress-markdown-body pre[class*='v-md-prism-'] code,
html[data-theme='dark'] .guide-body .vuepress-markdown-body pre[class*='v-md-prism-'] code {
  background-color: transparent;
  color: var(--kb-code-block-text);
}

html[data-theme='dark'] .kb-container .vuepress-markdown-body :not(pre) > code,
html[data-theme='dark'] .guide-body .vuepress-markdown-body :not(pre) > code {
  background-color: #3a3b40;
  color: var(--kb-code-block-text);
}
</style>
