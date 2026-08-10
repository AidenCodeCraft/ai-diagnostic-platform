<template>
  <teleport to="body">
    <div v-if="visible" class="menu-overlay" @click="$emit('close')"></div>
    <transition name="help-modal">
      <div v-if="visible" class="help-dialog">
        <div class="help-header">
          <h3>帮助与反馈</h3>
          <button class="help-close" @click="$emit('close')">&times;</button>
        </div>
        <div class="help-layout">
          <!-- 左侧导航 -->
          <nav class="help-nav">
            <div
              v-for="tab in tabs"
              :key="tab.key"
              class="help-nav-item"
              :class="{ active: activeTab === tab.key }"
              @click="activeTab = tab.key"
            >
              <span v-html="tab.icon"></span>
              <span>{{ tab.label }}</span>
            </div>
          </nav>
          <!-- 右侧内容 -->
          <div class="help-content">
            <!-- 常见问题 -->
            <div v-show="activeTab === 'faq'" class="help-section">
              <div class="faq-list">
                <div v-for="(item, i) in faqs" :key="i" class="faq-item">
                  <div class="faq-q" @click="item.open = !item.open">
                    <span>{{ item.q }}</span>
                    <svg :class="{ rotated: item.open }" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="6 9 12 15 18 9"/></svg>
                  </div>
                  <div v-show="item.open" class="faq-a">{{ item.a }}</div>
                </div>
              </div>
            </div>

            <!-- 意见反馈 -->
            <div v-show="activeTab === 'feedback'" class="help-section">
              <h4>意见反馈</h4>
              <p class="help-desc">我们非常重视您的反馈。如有任何建议、问题或功能需求，请通过以下方式联系我们：</p>
              <div class="contact-methods">
                <div class="contact-card">
                  <div class="contact-icon">📧</div>
                  <div class="contact-label">邮箱</div>
                  <div class="contact-value">support@ai-diagnostic.com</div>
                </div>
                <div class="contact-card">
                  <div class="contact-icon">💬</div>
                  <div class="contact-label">反馈社区</div>
                  <div class="contact-value">GitHub Issues</div>
                </div>
              </div>
            </div>

            <!-- 关于 -->
            <div v-show="activeTab === 'about'" class="help-section">
              <h4>AI Diagnostic Platform</h4>
              <p class="help-desc">一款面向嵌入式开发、测试验证和技术支持团队的 AI 智能故障诊断平台。</p>
              <div class="about-grid">
                <div class="about-row"><span class="about-key">产品名称</span><span class="about-val">AI Diagnostic Platform</span></div>
                <div class="about-row"><span class="about-key">当前版本</span><span class="about-val">v1.0.0</span></div>
                <div class="about-row"><span class="about-key">技术栈</span><span class="about-val">Vue 3 + FastAPI + PostgreSQL</span></div>
                <div class="about-row"><span class="about-key">AI 引擎</span><span class="about-val">DeepSeek / OpenAI Compatible</span></div>
                <div class="about-row"><span class="about-key">许可证</span><span class="about-val">Apache-2.0</span></div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </transition>
  </teleport>
</template>

<script setup lang="ts">
import { ref, reactive, watch } from 'vue'

defineProps<{ visible: boolean }>()
defineEmits<{ (e: 'close'): void }>()

const activeTab = ref('faq')

const tabs = [
  { key: 'faq', label: '常见问题', icon: '❓' },
  { key: 'feedback', label: '意见反馈', icon: '💡' },
  { key: 'about', label: '关于我们', icon: 'ℹ️' },
]

const faqs = reactive([
  {
    q: '如何使用本平台进行日志诊断？',
    a: '在对话界面中，您可以直接拖拽或上传设备日志文件，系统会自动解析日志、匹配诊断规则，并结合 AI 模型给出诊断结果和建议。您也可以直接在输入框中输入问题与 AI 进行多轮对话。',
    open: false,
  },
  {
    q: '支持哪些类型的日志格式？',
    a: '目前支持 Linux syslog（传统格式和 ISO 格式）、Kernel dmesg 格式、USB 日志、蓝牙日志等。对于未知格式的日志，系统会使用通用解析器进行降级处理。',
    open: false,
  },
  {
    q: '如何配置 AI 模型？',
    a: '管理员可以在"管理后台 → 系统配置 → LLM 配置"中添加和管理模型。支持 DeepSeek 系列模型以及 OpenAI 兼容接口的模型（如 Qwen、Llama、GPT、Ollama 等）。',
    open: false,
  },
  {
    q: '如何管理知识库？',
    a: '在左侧边栏点击"知识库"进入知识库管理页面，您可以创建笔记、上传手册/FAQ/数据手册等文档。系统会自动对文档进行分块和向量索引，支持混合搜索。',
    open: false,
  },
  {
    q: '对话历史会保存多久？',
    a: '对话历史会持久化存储在服务器数据库中，您可以随时查看历史对话。在设置中可以选择清除对话数据。',
    open: false,
  },
  {
    q: '如何导出诊断报告？',
    a: '在对话界面中，上传日志并完成分析后，输入区会出现"生成诊断报告"按钮。您可以选择需要包含的对话消息，系统会根据选中的内容生成 Markdown 格式的诊断报告。',
    open: false,
  },
])

watch(() => activeTab.value, () => {
  faqs.forEach(f => f.open = false)
})
</script>

<style scoped>
.menu-overlay {
  position: fixed;
  inset: 0;
  z-index: 99;
  background: rgba(0, 0, 0, 0.3);
}

.help-dialog {
  position: fixed;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  z-index: 100;
  background: #fff;
  border-radius: 14px;
  box-shadow: 0 16px 48px rgba(0, 0, 0, 0.18);
  width: 680px;
  height: 500px;
  max-height: 80vh;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.help-modal-enter-active { transition: all 0.2s cubic-bezier(0.22, 0.61, 0.36, 1); }
.help-modal-leave-active { transition: all 0.15s cubic-bezier(0.55, 0, 1, 0.45); }
.help-modal-enter-from,
.help-modal-leave-to { opacity: 0; transform: translate(-50%, -50%) scale(0.92); }

.help-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 18px 24px;
  border-bottom: 1px solid #f3f4f6;
  flex-shrink: 0;
}

.help-header h3 {
  font-size: 17px;
  font-weight: 600;
  color: #1f2937;
  margin: 0;
}

.help-close {
  background: none;
  border: none;
  font-size: 22px;
  color: #9ca3af;
  cursor: pointer;
  padding: 0 4px;
  line-height: 1;
  border-radius: 6px;
  transition: all 0.12s;
}

.help-close:hover { color: #374151; background: #f3f4f6; }

.help-layout {
  display: flex;
  flex: 1;
  overflow: hidden;
  min-height: 0;
}

.help-nav {
  width: 150px;
  background: #f9fafb;
  padding: 12px 8px;
  display: flex;
  flex-direction: column;
  gap: 2px;
  flex-shrink: 0;
}

.help-nav-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 12px;
  border-radius: 8px;
  cursor: pointer;
  font-size: 13px;
  color: #4b5563;
  transition: all 0.12s;
}

.help-nav-item:hover { background: #e5e7eb; }
.help-nav-item.active { background: #edf3fe; color: #2563eb; font-weight: 500; }

.help-content {
  flex: 1;
  padding: 20px 24px;
  overflow-y: auto;
}

.help-section { min-height: 100%; }

.help-section h4 {
  font-size: 15px;
  font-weight: 600;
  color: #1f2937;
  margin: 0 0 12px;
}

.help-desc {
  font-size: 13px;
  color: #6b7280;
  line-height: 1.7;
  margin-bottom: 16px;
}

/* FAQ */
.faq-list { display: flex; flex-direction: column; gap: 2px; }

.faq-item {
  border: 1px solid #f3f4f6;
  border-radius: 8px;
  overflow: hidden;
  transition: border-color 0.12s;
}

.faq-item:hover { border-color: #e5e7eb; }

.faq-q {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 14px;
  cursor: pointer;
  font-size: 13px;
  color: #374151;
  user-select: none;
}

.faq-q svg { flex-shrink: 0; color: #9ca3af; transition: transform 0.2s; }
.faq-q svg.rotated { transform: rotate(180deg); }

.faq-a {
  padding: 0 14px 12px;
  font-size: 13px;
  color: #6b7280;
  line-height: 1.7;
}

/* Contact */
.contact-methods {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
  margin-top: 8px;
}

.contact-card {
  padding: 16px;
  background: #f9fafb;
  border: 1px solid #e5e7eb;
  border-radius: 10px;
  text-align: center;
}

.contact-icon { font-size: 24px; margin-bottom: 6px; }
.contact-label { font-size: 12px; color: #9ca3af; margin-bottom: 4px; }
.contact-value { font-size: 13px; color: #374151; font-weight: 500; word-break: break-all; }

/* About */
.about-grid {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-top: 12px;
}

.about-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 12px;
  background: #f9fafb;
  border-radius: 8px;
}

.about-key { font-size: 13px; color: #6b7280; }
.about-val { font-size: 13px; color: #1f2937; font-weight: 500; }
</style>
