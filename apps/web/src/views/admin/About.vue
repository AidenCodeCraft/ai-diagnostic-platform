<template>
  <div class="about-page">
    <h2 class="page-title">关于系统</h2>

    <div class="about-card">
      <div class="about-head">
        <div class="about-logo">AI</div>
        <div class="about-head-text">
          <h3>AI Diagnostic Platform</h3>
          <p>设备日志智能诊断平台 · v1.0.0</p>
        </div>
      </div>

      <div class="about-grid">
        <div v-for="item in facts" :key="item.key" class="about-item">
          <span class="about-key">{{ item.key }}</span>
          <span class="about-val">{{ item.value }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
/** 关于系统：原「系统配置 → 关于」tab 拆分而来，属于只读信息展示 */
const facts = [
  { key: '产品名称', value: 'AI Diagnostic Platform' },
  { key: '当前版本', value: 'v1.0.0' },
  { key: '后端框架', value: 'FastAPI + SQLAlchemy' },
  { key: '前端框架', value: 'Vue 3 + Element Plus' },
  { key: '数据库', value: 'PostgreSQL' },
  { key: 'AI 引擎', value: 'DeepSeek / OpenAI Compatible' },
  { key: '向量数据库', value: 'Milvus (可选)' },
  { key: '部署方式', value: 'Docker Compose / Kubernetes' },
  { key: '许可证', value: 'MIT' },
]
</script>

<style scoped>
.page-title { font-size: 20px; font-weight: 600; color: var(--chat-layout-text); margin: 0 0 20px; }

.about-card {
  background: var(--chat-popup-bg);
  border: 1px solid var(--chat-popup-border);
  border-radius: 10px;
  padding: 24px;
}

.about-head {
  display: flex;
  align-items: center;
  gap: 14px;
  padding-bottom: 20px;
  margin-bottom: 20px;
  border-bottom: 1px solid var(--chat-popup-border);
}

.about-logo {
  width: 44px;
  height: 44px;
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--chat-sidebar-history-active-bg);
  color: var(--chat-sidebar-history-active-text);
  font-size: 15px;
  font-weight: 700;
  flex-shrink: 0;
}

.about-head-text h3 {
  margin: 0 0 4px;
  font-size: 16px;
  font-weight: 600;
  color: var(--chat-layout-text);
}

.about-head-text p {
  margin: 0;
  font-size: 12px;
  color: var(--chat-source-muted);
}

.about-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}

.about-item {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  padding: 10px 14px;
  background: var(--chat-source-bg);
  border-radius: 8px;
}

.about-key { font-size: 13px; color: var(--chat-source-muted); }
.about-val { font-size: 13px; color: var(--chat-layout-text); font-weight: 500; text-align: right; }

@media (max-width: 768px) {
  .about-grid { grid-template-columns: 1fr; }
}
</style>
