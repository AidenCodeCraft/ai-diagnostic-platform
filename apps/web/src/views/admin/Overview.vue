<template>
  <div class="overview-page">
    <h2 class="page-title">系统概览</h2>

    <!-- 指标卡片 -->
    <div class="stat-cards">
      <div class="stat-card">
        <div class="stat-icon users">👥</div>
        <div class="stat-info"><div class="stat-value">{{ stats.total_users }}</div><div class="stat-label">用户总数</div></div>
      </div>
      <div class="stat-card">
        <div class="stat-icon projects">📁</div>
        <div class="stat-info"><div class="stat-value">{{ stats.total_projects }}</div><div class="stat-label">项目数</div></div>
      </div>
      <div class="stat-card">
        <div class="stat-icon logs">📋</div>
        <div class="stat-info"><div class="stat-value">{{ stats.total_logs }}</div><div class="stat-label">日志总数</div></div>
      </div>
      <div class="stat-card">
        <div class="stat-icon analyses">🔬</div>
        <div class="stat-info"><div class="stat-value">{{ stats.total_analyses }}</div><div class="stat-label">分析任务</div></div>
      </div>
      <div class="stat-card">
        <div class="stat-icon knowledge">📚</div>
        <div class="stat-info"><div class="stat-value">{{ stats.total_knowledge }}</div><div class="stat-label">知识文档</div></div>
      </div>
    </div>

    <!-- 分析成功率 + 存储用量 -->
    <div class="overview-row">
      <div class="overview-panel">
        <h3 class="panel-title">分析任务统计</h3>
        <div class="analysis-stats">
          <div class="analysis-stat success">
            <span class="as-value">{{ stats.analysis_completed }}</span>
            <span class="as-label">已完成</span>
          </div>
          <div class="analysis-divider"></div>
          <div class="analysis-stat failed">
            <span class="as-value">{{ stats.analysis_failed }}</span>
            <span class="as-label">失败</span>
          </div>
          <div class="analysis-divider"></div>
          <div class="analysis-stat rate">
            <span class="as-value">{{ successRate }}%</span>
            <span class="as-label">成功率</span>
          </div>
        </div>
      </div>
      <div class="overview-panel">
        <h3 class="panel-title">存储用量</h3>
        <div class="storage-info">
          <div class="storage-value">{{ formatBytes(stats.total_log_size_bytes) }}</div>
          <div class="storage-label">日志总存储量</div>
          <div class="storage-bar"><div class="storage-bar-fill" :style="{ width: '42%' }"></div></div>
        </div>
      </div>
    </div>

    <!-- 分析趋势 -->
    <div class="overview-panel" style="margin-top:16px">
      <h3 class="panel-title">近 7 天分析趋势</h3>
      <div class="trend-chart" v-if="stats.analysis_trend && stats.analysis_trend.length">
        <div class="trend-bars">
          <div v-for="(item, i) in stats.analysis_trend" :key="i" class="trend-bar-wrap">
            <div class="trend-bar" :style="{ height: Math.max(4, (item.count / maxTrendCount) * 120) + 'px' }" :title="`${item.date}: ${item.count}`"></div>
            <div class="trend-label">{{ formatDate(item.date) }}</div>
          </div>
        </div>
      </div>
      <div v-else class="panel-empty">暂无数据</div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { adminApi, AdminStats } from '@/api/admin'

const stats = ref<AdminStats>({
  total_users: 0, total_projects: 0, total_logs: 0,
  total_analyses: 0, total_knowledge: 0,
  analysis_completed: 0, analysis_failed: 0,
  analysis_trend: [], total_log_size_bytes: 0, active_plugins: 0,
})

const successRate = computed(() => {
  const total = stats.value.analysis_completed + stats.value.analysis_failed
  return total > 0 ? Math.round((stats.value.analysis_completed / total) * 100) : 0
})

const maxTrendCount = computed(() => {
  if (!stats.value.analysis_trend.length) return 1
  return Math.max(...stats.value.analysis_trend.map(i => i.count), 1)
})

function formatBytes(bytes: number) {
  if (!bytes) return '0 B'
  if (bytes < 1024) return bytes + ' B'
  if (bytes < 1048576) return (bytes / 1024).toFixed(1) + ' KB'
  return (bytes / 1048576).toFixed(1) + ' MB'
}

function formatDate(d: string) {
  const parts = d.split('-')
  return parts.length === 3 ? `${parts[1]}/${parts[2]}` : d
}

onMounted(async () => {
  try {
    const { data } = await adminApi.getStats()
    stats.value = data
  } catch { /* ignore */ }
})
</script>

<style scoped>
.page-title { font-size: 20px; font-weight: 600; color: #1f2937; margin: 0 0 20px; }

.stat-cards { display: grid; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)); gap: 12px; margin-bottom: 16px; }
.stat-card {
  display: flex; align-items: center; gap: 14px; padding: 18px 16px;
  background: #fff; border: 1px solid #e5e7eb; border-radius: 10px;
}
.stat-icon { width: 44px; height: 44px; border-radius: 10px; display: flex; align-items: center; justify-content: center; font-size: 22px; flex-shrink: 0; }
.stat-icon.users { background: #edf3fe; } .stat-icon.projects { background: #fef3c7; }
.stat-icon.logs { background: #f3e8ff; } .stat-icon.analyses { background: #dcfce7; }
.stat-icon.knowledge { background: #fce7f3; }
.stat-info { display: flex; flex-direction: column; }
.stat-value { font-size: 24px; font-weight: 700; color: #1f2937; line-height: 1.2; }
.stat-label { font-size: 13px; color: #6b7280; margin-top: 2px; }

.overview-row { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
.overview-panel { background: #fff; border: 1px solid #e5e7eb; border-radius: 10px; padding: 18px 20px; }
.panel-title { font-size: 14px; font-weight: 600; color: #374151; margin: 0 0 14px; }
.panel-empty { font-size: 13px; color: #9ca3af; text-align: center; padding: 20px 0; }

.analysis-stats { display: flex; align-items: center; gap: 0; }
.analysis-stat { flex: 1; text-align: center; }
.as-value { display: block; font-size: 28px; font-weight: 700; }
.as-label { display: block; font-size: 12px; color: #6b7280; margin-top: 4px; }
.analysis-stat.success .as-value { color: #16a34a; }
.analysis-stat.failed .as-value { color: #dc2626; }
.analysis-stat.rate .as-value { color: #2563eb; }
.analysis-divider { width: 1px; height: 48px; background: #e5e7eb; }

.storage-info { text-align: center; }
.storage-value { font-size: 28px; font-weight: 700; color: #1f2937; }
.storage-label { font-size: 12px; color: #6b7280; margin-top: 4px; }
.storage-bar { height: 8px; background: #e5e7eb; border-radius: 4px; margin-top: 12px; overflow: hidden; }
.storage-bar-fill { height: 100%; background: #2563eb; border-radius: 4px; transition: width 0.6s; }

.trend-chart { padding-top: 8px; }
.trend-bars { display: flex; align-items: flex-end; gap: 12px; height: 140px; }
.trend-bar-wrap { flex: 1; display: flex; flex-direction: column; align-items: center; justify-content: flex-end; height: 100%; }
.trend-bar { width: 100%; max-width: 48px; background: #93c5fd; border-radius: 4px 4px 0 0; transition: height 0.4s; min-height: 4px; }
.trend-bar:hover { background: #2563eb; }
.trend-label { font-size: 11px; color: #6b7280; margin-top: 6px; }

@media (max-width: 768px) {
  .overview-row { grid-template-columns: 1fr; }
}
</style>
