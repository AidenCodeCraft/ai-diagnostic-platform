<template>
  <div class="settings-page">
    <h2 class="page-title">系统配置</h2>

    <el-tabs v-model="activeTab" class="settings-tabs">
      <!-- LLM 配置 -->
      <el-tab-pane label="LLM 配置" name="llm">
        <div class="llm-config-section">
          <div class="llm-header">
            <h3>模型配置</h3>
            <el-button type="primary" size="small" @click="addModel">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="margin-right:4px">
                <line x1="12" y1="5" x2="12" y2="19"/>
                <line x1="5" y1="12" x2="19" y2="12"/>
              </svg>
              添加模型
            </el-button>
          </div>

          <div class="models-list">
            <div v-for="(model, index) in llmModels" :key="index" class="model-card" :class="{ default: model.isDefault }">
              <div class="model-header">
                <div class="model-title-row">
                  <el-input v-model="model.name" placeholder="模型名称" style="width:200px" size="small" />
                  <el-tag v-if="model.isDefault" type="success" size="small">默认</el-tag>
                  <el-button v-else text type="primary" size="small" @click="setDefault(index)">设为默认</el-button>
                </div>
                <el-button text type="danger" size="small" :disabled="llmModels.length === 1" @click="removeModel(index)">删除</el-button>
              </div>

              <div class="model-config-grid">
                <div class="config-field">
                  <label>Provider</label>
                  <el-select v-model="model.provider" size="small" style="width:100%">
                    <el-option label="DeepSeek" value="deepseek" />
                    <el-option label="OpenAI Compatible" value="openai_compatible" />
                  </el-select>
                </div>

                <div class="config-field">
                  <label>模型标识</label>
                  <el-select v-model="model.model" size="small" style="width:100%" :placeholder="model.provider === 'deepseek' ? '选择模型' : '输入模型名称'" allow-create filterable>
                    <template v-if="model.provider === 'deepseek'">
                      <el-option label="deepseek-v4-flash (推荐)" value="deepseek-v4-flash">
                        <span>deepseek-v4-flash</span>
                        <el-tag size="small" type="success" style="margin-left:8px">推荐</el-tag>
                      </el-option>
                      <el-option label="deepseek-v4-pro" value="deepseek-v4-pro" />
                    </template>
                  </el-select>
                </div>

                <div class="config-field full-width">
                  <label>Base URL</label>
                  <el-input v-model="model.base_url" size="small" :placeholder="model.provider === 'deepseek' ? 'https://api.deepseek.com' : 'https://api.openai.com/v1'" />
                </div>

                <div class="config-field full-width">
                  <label>API Key</label>
                  <el-input v-model="model.api_key" type="password" show-password size="small" placeholder="sk-..." />
                </div>

                <div class="config-field">
                  <label>Temperature</label>
                  <el-input-number v-model="model.temperature" :min="0" :max="2" :step="0.1" :precision="1" size="small" style="width:100%" />
                </div>

                <div class="config-field">
                  <label>Max Tokens</label>
                  <el-input-number v-model="model.max_tokens" :min="100" :max="32000" :step="100" size="small" style="width:100%" />
                </div>
              </div>
            </div>
          </div>

          <div class="config-actions">
            <el-button type="primary" :loading="saving" @click="saveLLMConfig">保存全部配置</el-button>
            <el-button @click="loadLLMConfig">重置</el-button>
          </div>
        </div>
      </el-tab-pane>

      <!-- 系统参数 -->
      <el-tab-pane label="系统参数" name="system">
        <div class="config-section">
          <div class="config-item">
            <label class="config-label">最大上传大小 (MB)</label>
            <el-input-number v-model="sysConfig.max_upload_mb" :min="1" :max="500" style="width:160px" />
          </div>
          <div class="config-item">
            <label class="config-label">分析超时 (秒)</label>
            <el-input-number v-model="sysConfig.timeout_seconds" :min="30" :max="3600" style="width:160px" />
          </div>
          <div class="config-item">
            <label class="config-label">日志保留天数</label>
            <el-input-number v-model="sysConfig.log_retention_days" :min="7" :max="365" style="width:160px" />
          </div>
          <el-button type="primary" style="margin-top:12px" @click="saveSysConfig">保存配置</el-button>
        </div>
      </el-tab-pane>

      <!-- 数据清理 -->
      <el-tab-pane label="数据清理" name="cleanup">
        <div class="config-section">
          <div class="cleanup-card">
            <div class="cleanup-info">
              <h4>清除所有对话数据</h4>
              <p>清除当前用户的所有聊天对话记录，此操作不可恢复</p>
            </div>
            <div class="cleanup-action">
              <el-button type="danger" plain :loading="clearingData" @click="clearAllChatData">清除所有对话数据</el-button>
            </div>
          </div>
        </div>
      </el-tab-pane>

      <!-- 关于 -->
      <el-tab-pane label="关于系统" name="about">
        <div class="config-section">
          <div class="about-grid">
            <div class="about-item"><span class="about-key">产品名称</span><span class="about-val">AI Diagnostic Platform</span></div>
            <div class="about-item"><span class="about-key">当前版本</span><span class="about-val">v1.0.0</span></div>
            <div class="about-item"><span class="about-key">后端框架</span><span class="about-val">FastAPI + SQLAlchemy</span></div>
            <div class="about-item"><span class="about-key">前端框架</span><span class="about-val">Vue 3 + Element Plus</span></div>
            <div class="about-item"><span class="about-key">数据库</span><span class="about-val">PostgreSQL</span></div>
            <div class="about-item"><span class="about-key">AI 引擎</span><span class="about-val">DeepSeek / OpenAI Compatible</span></div>
            <div class="about-item"><span class="about-key">向量数据库</span><span class="about-val">Milvus (可选)</span></div>
            <div class="about-item"><span class="about-key">部署方式</span><span class="about-val">Docker Compose / Kubernetes</span></div>
            <div class="about-item"><span class="about-key">许可证</span><span class="about-val">MIT</span></div>
          </div>
        </div>
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { adminApi } from '@/api/admin'
import { chatApi } from '@/api/chat'
import { useUserStore } from '@/stores/user'

interface LLMModel {
  name: string
  provider: string
  model: string
  api_key: string
  base_url: string
  temperature: number
  max_tokens: number
  isDefault: boolean
}

const activeTab = ref('llm')
const saving = ref(false)

const llmModels = ref<LLMModel[]>([
  {
    name: 'DeepSeek V4 Flash',
    provider: 'deepseek',
    model: 'deepseek-v4-flash',
    api_key: '',
    base_url: 'https://api.deepseek.com',
    temperature: 1.0,
    max_tokens: 8000,
    isDefault: true
  }
])

const sysConfig = ref({
  max_upload_mb: 100,
  timeout_seconds: 300,
  log_retention_days: 90,
})

const cleanupDate = ref('')
const cleanupLogDate = ref('')
const clearingData = ref(false)

const userStore = useUserStore()

async function clearAllChatData() {
  try {
    await ElMessageBox.confirm(
      '确定要清除当前用户的所有对话数据吗？此操作不可恢复。',
      '确认清除',
      { type: 'warning', confirmButtonText: '确认清除', cancelButtonText: '取消' }
    )
  } catch { return }

  clearingData.value = true
  try {
    // 获取当前用户的所有会话
    const { data } = await chatApi.listSessions()
    const sessions = data?.items || []
    if (sessions.length === 0) {
      ElMessage.info('没有需要清除的对话数据')
      return
    }
    // 逐个删除
    let deleted = 0
    await Promise.all(
      sessions.map(async (s: any) => {
        try {
          await chatApi.deleteSession(s.id)
          deleted++
        } catch { /* 单个删除失败继续 */ }
      })
    )
    ElMessage.success(`已清除 ${deleted} 个对话记录`)
  } catch (err: any) {
    ElMessage.error('清除失败: ' + (err.response?.data?.detail || err.message))
  } finally {
    clearingData.value = false
  }
}

function addModel() {
  llmModels.value.push({
    name: '新模型',
    provider: 'deepseek',
    model: 'deepseek-v4-flash',
    api_key: '',
    base_url: 'https://api.deepseek.com',
    temperature: 1.0,
    max_tokens: 8000,
    isDefault: false
  })
}

async function removeModel(index: number) {
  if (llmModels.value.length === 1) {
    ElMessage.warning('至少需要保留一个模型配置')
    return
  }

  try {
    await ElMessageBox.confirm('确定删除此模型配置？', '确认', {
      confirmButtonText: '删除',
      cancelButtonText: '取消',
      type: 'warning'
    })
    
    const wasDefault = llmModels.value[index].isDefault
    llmModels.value.splice(index, 1)
    
    if (wasDefault && llmModels.value.length > 0) {
      llmModels.value[0].isDefault = true
    }
  } catch {
    // 取消删除
  }
}

function setDefault(index: number) {
  llmModels.value.forEach((m, i) => {
    m.isDefault = i === index
  })
}

async function loadLLMConfig() {
  try {
    const { data } = await adminApi.getLLMConfig()
    if (data && Array.isArray(data.models) && data.models.length > 0) {
      llmModels.value = data.models
    }
  } catch (err) {
    console.error('[Settings] Failed to load LLM config:', err)
    // 使用默认配置
  }
}

async function saveLLMConfig() {
  // 验证必填字段
  const hasEmptyKey = llmModels.value.some(m => !m.api_key.trim())
  if (hasEmptyKey) {
    ElMessage.warning('请填写所有模型的 API Key')
    return
  }

  const hasEmptyName = llmModels.value.some(m => !m.name.trim())
  if (hasEmptyName) {
    ElMessage.warning('请填写所有模型的名称')
    return
  }

  const hasEmptyModel = llmModels.value.some(m => !m.model.trim())
  if (hasEmptyModel) {
    ElMessage.warning('请选择或填写所有模型的标识')
    return
  }

  saving.value = true
  try {
    await adminApi.saveLLMConfig({ models: llmModels.value })
    ElMessage.success('LLM 配置已保存，即时生效')
    
    // 触发全局事件通知其他组件更新模型列表
    window.dispatchEvent(new CustomEvent('llm-config-updated'))
  } catch (err: any) {
    console.error('[Settings] Failed to save LLM config:', err)
    ElMessage.error('保存失败: ' + (err.response?.data?.detail || err.message))
  } finally {
    saving.value = false
  }
}

async function saveSysConfig() {
  saving.value = true
  try {
    await adminApi.saveSystemConfig(sysConfig.value)
    ElMessage.success('系统参数已保存')
  } catch (err: any) {
    ElMessage.error('保存失败: ' + (err.response?.data?.detail || err.message))
  } finally {
    saving.value = false
  }
}

async function loadSysConfig() {
  try {
    const { data } = await adminApi.getSystemConfig()
    if (data) {
      sysConfig.value = {
        maxUploadMb: data.maxUploadMb ?? 100,
        timeoutSeconds: data.timeoutSeconds ?? 300,
        logRetentionDays: data.logRetentionDays ?? 90,
      }
    }
  } catch (err) {
    console.error('[Settings] Failed to load system config:', err)
  }
}

onMounted(() => {
  loadLLMConfig()
  loadSysConfig()
})
</script>

<style scoped>
.page-title { font-size: 20px; font-weight: 600; color: #1f2937; margin: 0 0 20px; }
.settings-tabs { background: #fff; border: 1px solid #e5e7eb; border-radius: 10px; padding: 0 16px 16px; }
.config-section { padding-top: 8px; }
.config-item { display: flex; align-items: center; gap: 16px; margin-bottom: 14px; }
.config-label { width: 130px; font-size: 14px; color: #374151; text-align: right; flex-shrink: 0; }

.llm-config-section { padding-top: 16px; }
.llm-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; }
.llm-header h3 { margin: 0; font-size: 16px; font-weight: 600; color: #1f2937; }

.models-list { display: flex; flex-direction: column; gap: 16px; margin-bottom: 24px; }
.model-card { padding: 20px; border: 2px solid #e5e7eb; border-radius: 12px; background: #f9fafb; transition: all 0.2s; }
.model-card.default { border-color: #10b981; background: #f0fdf4; }
.model-card:hover { box-shadow: 0 2px 8px rgba(0,0,0,0.06); }

.model-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; }
.model-title-row { display: flex; align-items: center; gap: 12px; }

.model-config-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
.config-field { display: flex; flex-direction: column; gap: 6px; }
.config-field.full-width { grid-column: 1 / -1; }
.config-field label { font-size: 13px; font-weight: 500; color: #6b7280; }

.config-actions { display: flex; gap: 12px; padding-top: 8px; border-top: 1px solid #e5e7eb; }

.cleanup-card { display: flex; align-items: center; justify-content: space-between; padding: 16px; background: #f9fafb; border: 1px solid #e5e7eb; border-radius: 8px; }
.cleanup-info h4 { margin: 0 0 4px; font-size: 14px; color: #1f2937; }
.cleanup-info p { margin: 0; font-size: 12px; color: #6b7280; }
.cleanup-action { display: flex; align-items: center; flex-shrink: 0; }

.about-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
.about-item { display: flex; justify-content: space-between; padding: 10px 14px; background: #f9fafb; border-radius: 8px; }
.about-key { font-size: 13px; color: #6b7280; }
.about-val { font-size: 13px; color: #1f2937; font-weight: 500; }

@media (max-width: 768px) {
  .about-grid { grid-template-columns: 1fr; }
  .config-item { flex-direction: column; align-items: flex-start; gap: 6px; }
  .config-label { text-align: left; }
  .cleanup-card { flex-direction: column; align-items: flex-start; gap: 12px; }
  .model-config-grid { grid-template-columns: 1fr; }
  .config-field.full-width { grid-column: 1; }
}
</style>
