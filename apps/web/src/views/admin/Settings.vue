<template>
  <div class="settings-page">
    <h2 class="page-title">系统配置</h2>

    <el-tabs v-model="activeTab" class="settings-tabs">
      <!-- LLM 配置 -->
      <el-tab-pane label="LLM 配置" name="llm">
        <div class="config-section">
          <div class="config-item">
            <label class="config-label">默认 Provider</label>
            <el-select v-model="llmConfig.provider" style="width:240px">
              <el-option label="DeepSeek" value="deepseek" />
              <el-option label="OpenAI Compatible" value="openai_compatible" />
              <el-option label="Mock" value="mock" />
            </el-select>
          </div>
          <div class="config-item">
            <label class="config-label">API Key</label>
            <el-input v-model="llmConfig.api_key" type="password" show-password style="width:360px" placeholder="sk-..." />
          </div>
          <div class="config-item">
            <label class="config-label">Base URL</label>
            <el-input v-model="llmConfig.base_url" style="width:360px" placeholder="https://api.deepseek.com" />
          </div>
          <div class="config-item">
            <label class="config-label">默认模型</label>
            <el-input v-model="llmConfig.model" style="width:240px" placeholder="deepseek-chat" />
          </div>
          <el-button type="primary" style="margin-top:12px" :loading="saving" @click="saveLLMConfig">保存配置</el-button>
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
              <h4>清理分析任务</h4>
              <p>删除指定日期之前的分析任务及关联结果</p>
            </div>
            <div class="cleanup-action">
              <el-date-picker v-model="cleanupDate" type="date" placeholder="选择日期" style="width:160px" />
              <el-button type="danger" plain style="margin-left:8px">执行清理</el-button>
            </div>
          </div>
          <div class="cleanup-card" style="margin-top:12px">
            <div class="cleanup-info">
              <h4>清理日志文件</h4>
              <p>删除指定日期之前的日志文件及解析数据</p>
            </div>
            <div class="cleanup-action">
              <el-date-picker v-model="cleanupLogDate" type="date" placeholder="选择日期" style="width:160px" />
              <el-button type="danger" plain style="margin-left:8px">执行清理</el-button>
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
import { ElMessage } from 'element-plus'
import client from '@/api/client'

const activeTab = ref('llm')
const saving = ref(false)

const llmConfig = ref({
  provider: 'deepseek',
  api_key: '',
  base_url: 'https://api.deepseek.com',
  model: 'deepseek-chat',
})

const sysConfig = ref({
  max_upload_mb: 100,
  timeout_seconds: 300,
  log_retention_days: 90,
})

const cleanupDate = ref('')
const cleanupLogDate = ref('')

async function loadLLMConfig() {
  try {
    const { data } = await client.get('/admin/config/llm')
    if (data) llmConfig.value = data
  } catch { /* use defaults */ }
}

async function saveLLMConfig() {
  saving.value = true
  try {
    await client.put('/admin/config/llm', llmConfig.value)
    ElMessage.success('LLM 配置已保存，即时生效')
  } catch { ElMessage.error('保存失败') }
  finally { saving.value = false }
}

function saveSysConfig() {
  localStorage.setItem('sys_config', JSON.stringify(sysConfig.value))
  ElMessage.success('系统参数已保存')
}

onMounted(loadLLMConfig)
</script>

<style scoped>
.page-title { font-size: 20px; font-weight: 600; color: #1f2937; margin: 0 0 20px; }
.settings-tabs { background: #fff; border: 1px solid #e5e7eb; border-radius: 10px; padding: 0 16px 16px; }
.config-section { padding-top: 8px; }
.config-item { display: flex; align-items: center; gap: 16px; margin-bottom: 14px; }
.config-label { width: 130px; font-size: 14px; color: #374151; text-align: right; flex-shrink: 0; }

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
}
</style>
