<template>
  <el-dialog
    v-model="visible"
    title="标注为回归样本"
    width="620px"
    :close-on-click-modal="false"
    @open="onOpen"
  >
    <div class="dialog-hint">
      标注后需按角色审核才进入 CI 回归：管理员提交直接生效，开发需管理员终审，
      测试需开发复审 + 管理员终审，用户（售后/产品）需测试初审 + 开发复审 + 管理员终审。
    </div>

    <el-form :model="form" label-width="96px" size="default">
      <el-form-item label="问题">
        <el-input v-model="form.question" type="textarea" :rows="2" readonly />
      </el-form-item>

      <el-form-item label="期望结论">
        <el-select v-model="form.expectedConclusion" style="width: 180px">
          <el-option label="应作答" value="answered" />
          <el-option label="应拒答（知识库无相关内容）" value="refused" />
          <el-option label="应追问（槽位缺失）" value="ask_slot" />
          <el-option label="时间不符（应走候选时段）" value="time_mismatch" />
        </el-select>
      </el-form-item>

      <el-form-item label="现象类别">
        <el-input v-model="form.category" placeholder="如：定位异常 / 黑屏 / 断网" style="width: 220px" />
      </el-form-item>

      <el-form-item label="设备型号">
        <el-input v-model="form.deviceModel" placeholder="如：L10" style="width: 220px" />
      </el-form-item>

      <el-form-item label="城市">
        <el-input v-model="form.city" placeholder="如：深圳" style="width: 220px" />
      </el-form-item>

      <el-form-item label="现象描述">
        <el-input v-model="form.phenomenon" placeholder="用户描述的核心现象" />
      </el-form-item>

      <el-form-item label="时间点">
        <el-input v-model="form.timeBeijing" placeholder="北京时间，如 2026-08-02 14:22" style="width: 240px" />
      </el-form-item>

      <el-form-item label="期望章节">
        <div class="candidates">
          <div v-if="loadingTrace" class="candidate-empty">正在读取当时的检索轨迹…</div>
          <template v-else>
            <label
              v-for="(cand, idx) in candidates" :key="idx"
              class="candidate-row"
            >
              <el-checkbox v-model="cand.selected" />
              <span class="candidate-title">{{ cand.title || ('文档 ' + cand.doc_id) }}</span>
              <span v-if="cand.section" class="candidate-section">· {{ cand.section }}</span>
              <span v-if="cand.score != null" class="candidate-score">{{ Number(cand.score).toFixed(2) }}</span>
            </label>
            <div v-if="candidates.length === 0" class="candidate-empty">
              未找到当时的召回记录；可手动填写期望文档 ID（下方）。
            </div>
          </template>
          <div class="candidate-manual">
            <span class="manual-label">补充文档 ID：</span>
            <el-input v-model="form.manualDocId" placeholder="可选，多个用逗号分隔" style="width: 200px" />
          </div>
        </div>
      </el-form-item>

      <el-form-item label="备注">
        <el-input v-model="form.note" type="textarea" :rows="2" placeholder="为什么这条值得作为回归样本" />
      </el-form-item>
    </el-form>

    <template #footer>
      <el-button @click="visible = false">取消</el-button>
      <el-button type="primary" :loading="submitting" @click="submit">提交标注</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import client from '@/api/client'

interface Candidate {
  doc_id?: number
  title?: string
  section?: string
  score?: number
  selected?: boolean
}

const props = defineProps<{
  modelValue: boolean
  question: string
  sessionId?: number | null
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', value: boolean): void
  (e: 'submitted'): void
}>()

const visible = computed({
  get: () => props.modelValue,
  set: (value: boolean) => emit('update:modelValue', value),
})

const loadingTrace = ref(false)
const submitting = ref(false)
const traceId = ref<number | null>(null)
const candidates = ref<Candidate[]>([])

const form = reactive({
  question: '',
  expectedConclusion: 'answered',
  category: '',
  deviceModel: '',
  city: '',
  phenomenon: '',
  timeBeijing: '',
  manualDocId: '',
  note: '',
})

watch(() => props.question, (value) => { form.question = value || '' }, { immediate: true })

async function loadTrace() {
  candidates.value = []
  traceId.value = null
  if (!props.sessionId || !props.question) return
  loadingTrace.value = true
  try {
    const { data } = await client.get('/quality/traces', {
      params: { session_id: props.sessionId, question: props.question, limit: 1 },
    })
    const trace = data?.items?.[0]
    if (!trace) return
    traceId.value = trace.id
    const raw: Candidate[] = trace.kb_candidates?.candidates || []
    candidates.value = raw.slice(0, 5).map((item) => ({ ...item, selected: false }))
  } catch {
    /* 轨迹缺失不阻断标注 */
  } finally {
    loadingTrace.value = false
  }
}

function onOpen() {
  form.question = props.question || ''
  form.expectedConclusion = 'answered'
  form.category = ''
  form.deviceModel = ''
  form.city = ''
  form.phenomenon = ''
  form.timeBeijing = ''
  form.manualDocId = ''
  form.note = ''
  loadTrace()
}

async function submit() {
  if (!form.question.trim()) {
    ElMessage.warning('问题不能为空')
    return
  }

  const kbExpected = candidates.value
    .filter((cand) => cand.selected && cand.doc_id != null)
    .map((cand) => ({
      doc_id: cand.doc_id,
      section: cand.section || '',
      pk: `${cand.doc_id}:${cand.section || ''}`,
    }))

  const manualIds = form.manualDocId
    .split(/[,，\s]+/)
    .map((item) => Number(item.trim()))
    .filter((value) => Number.isFinite(value) && value > 0)
  for (const docId of manualIds) {
    if (!kbExpected.some((item) => item.doc_id === docId)) {
      kbExpected.push({ doc_id: docId, section: '', pk: `${docId}:` })
    }
  }

  submitting.value = true
  try {
    const { data } = await client.post('/quality/golden-samples', {
      question: form.question,
      slots: {
        city: form.city || null,
        device: form.deviceModel || null,
        phenomenon: form.phenomenon || null,
        time_beijing: form.timeBeijing || null,
        has_attachment: false,
      },
      kb_expected: kbExpected,
      expected_conclusion: form.expectedConclusion,
      category: form.category || null,
      device_model: form.deviceModel || null,
      note: form.note || null,
      trace_id: traceId.value,
    })
    const status = data?.status
    const next = data?.next_reviewer
    if (status === 'approved') {
      ElMessage.success('已提交并直接生效（管理员标注）')
    } else if (next) {
      ElMessage.success(`已提交，待 ${roleLabel(next)} 审核`)
    } else {
      ElMessage.success('已提交')
    }
    emit('submitted')
    visible.value = false
  } catch (error: any) {
    ElMessage.error(error?.response?.data?.detail || '提交失败')
  } finally {
    submitting.value = false
  }
}

function roleLabel(role: string): string {
  switch (role) {
    case 'admin': return '管理员'
    case 'developer': return '开发'
    case 'engineer': return '测试'
    case 'user': return '用户'
    default: return role
  }
}
</script>

<style scoped>
.dialog-hint {
  margin-bottom: 14px; padding: 8px 12px; font-size: 12px; line-height: 1.6;
  background: var(--el-fill-color-light, #f5f7fa); border-radius: 4px;
  color: var(--el-text-color-secondary, #909399);
}
.candidates { width: 100%; }
.candidate-row {
  display: flex; align-items: center; gap: 6px;
  padding: 2px 0; font-size: 13px; cursor: pointer;
}
.candidate-title { color: var(--el-text-color-primary, #303133); }
.candidate-section { color: var(--el-text-color-secondary, #909399); }
.candidate-score { margin-left: auto; font-size: 12px; color: #909399; }
.candidate-empty { font-size: 12px; color: #909399; padding: 4px 0; }
.candidate-manual { display: flex; align-items: center; gap: 6px; margin-top: 6px; }
.manual-label { font-size: 12px; color: #909399; }
</style>
