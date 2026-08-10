<template>
  <teleport to="body">
    <div v-if="visible" class="menu-overlay" @click="$emit('close')"></div>
    <transition name="download-modal">
      <div v-if="visible" class="download-dialog">
        <div class="download-header">
          <h3>下载客户端</h3>
          <button class="download-close" @click="$emit('close')">&times;</button>
        </div>
        <div class="download-content">
          <p class="download-subtitle">选择适合您的平台，随时随地使用 AI Diagnostic Platform</p>

          <!-- 桌面端 -->
          <div class="platform-section">
            <div class="platform-header">
              <span class="platform-icon">💻</span>
              <div>
                <h4>桌面客户端</h4>
                <p>适用于 Windows、macOS、Linux</p>
              </div>
            </div>
            <div class="platform-cards">
              <div class="platform-card">
                <div class="card-icon">
                  <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                    <rect x="2" y="3" width="20" height="14" rx="2"/>
                    <line x1="8" y1="21" x2="16" y2="21"/>
                    <line x1="12" y1="17" x2="12" y2="21"/>
                  </svg>
                </div>
                <div class="card-title">Windows</div>
                <div class="card-version">v1.0.0</div>
                <div class="card-size">~85 MB</div>
                <button class="card-dl-btn" disabled>
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/>
                  </svg>
                  即将推出
                </button>
              </div>
              <div class="platform-card">
                <div class="card-icon">
                  <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                    <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2z"/>
                    <path d="M12 2c2.5 2.5 4 6 4 10s-1.5 7.5-4 10"/>
                    <path d="M12 2C9.5 4.5 8 8 8 12s1.5 7.5 4 10"/>
                    <line x1="2" y1="12" x2="22" y2="12"/>
                  </svg>
                </div>
                <div class="card-title">macOS</div>
                <div class="card-version">v1.0.0</div>
                <div class="card-size">~92 MB</div>
                <button class="card-dl-btn" disabled>
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/>
                  </svg>
                  即将推出
                </button>
              </div>
              <div class="platform-card">
                <div class="card-icon">
                  <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                    <circle cx="12" cy="12" r="10"/>
                    <line x1="2" y1="12" x2="22" y2="12"/>
                    <path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/>
                  </svg>
                </div>
                <div class="card-title">Linux</div>
                <div class="card-version">v1.0.0</div>
                <div class="card-size">~78 MB</div>
                <button class="card-dl-btn" disabled>
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/>
                  </svg>
                  即将推出
                </button>
              </div>
            </div>
          </div>

          <!-- 移动端 -->
          <div class="platform-section">
            <div class="platform-header">
              <span class="platform-icon">📱</span>
              <div>
                <h4>移动客户端</h4>
                <p>适用于 iOS、Android</p>
              </div>
            </div>
            <div class="platform-cards">
              <div class="platform-card">
                <div class="card-icon">
                  <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                    <rect x="5" y="2" width="14" height="20" rx="3"/>
                    <line x1="12" y1="18" x2="12.01" y2="18"/>
                  </svg>
                </div>
                <div class="card-title">iOS</div>
                <div class="card-version">v1.0.0</div>
                <div class="card-size">~45 MB</div>
                <button class="card-dl-btn" disabled>
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/>
                  </svg>
                  即将推出
                </button>
              </div>
              <div class="platform-card">
                <div class="card-icon">
                  <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                    <rect x="5" y="2" width="14" height="20" rx="3"/>
                    <circle cx="12" cy="19" r="1"/>
                  </svg>
                </div>
                <div class="card-title">Android</div>
                <div class="card-version">v1.0.0</div>
                <div class="card-size">~42 MB</div>
                <button class="card-dl-btn" disabled>
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/>
                  </svg>
                  即将推出
                </button>
              </div>
            </div>
          </div>

          <!-- 网页版 -->
          <div class="web-hint">
            <span>💡 您也可以直接使用</span>
            <a href="/" @click.prevent="$emit('close')">网页版</a>
            <span>，无需下载安装。</span>
          </div>
        </div>
      </div>
    </transition>
  </teleport>
</template>

<script setup lang="ts">
defineProps<{ visible: boolean }>()
defineEmits<{ (e: 'close'): void }>()
</script>

<style scoped>
.menu-overlay {
  position: fixed;
  inset: 0;
  z-index: 99;
  background: rgba(0, 0, 0, 0.3);
}

.download-dialog {
  position: fixed;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  z-index: 100;
  background: #fff;
  border-radius: 14px;
  box-shadow: 0 16px 48px rgba(0, 0, 0, 0.18);
  width: 640px;
  max-height: 85vh;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.download-modal-enter-active { transition: all 0.2s cubic-bezier(0.22, 0.61, 0.36, 1); }
.download-modal-leave-active { transition: all 0.15s cubic-bezier(0.55, 0, 1, 0.45); }
.download-modal-enter-from,
.download-modal-leave-to { opacity: 0; transform: translate(-50%, -50%) scale(0.92); }

.download-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 18px 24px;
  border-bottom: 1px solid #f3f4f6;
  flex-shrink: 0;
}

.download-header h3 { font-size: 17px; font-weight: 600; color: #1f2937; margin: 0; }

.download-close {
  background: none; border: none; font-size: 22px; color: #9ca3af;
  cursor: pointer; padding: 0 4px; line-height: 1; border-radius: 6px; transition: all 0.12s;
}
.download-close:hover { color: #374151; background: #f3f4f6; }

.download-content {
  padding: 24px;
  overflow-y: auto;
}

.download-subtitle {
  font-size: 13px; color: #6b7280; margin: 0 0 24px; text-align: center;
}

.platform-section {
  margin-bottom: 24px;
  padding: 20px;
  background: #f9fafb;
  border: 1px solid #e5e7eb;
  border-radius: 12px;
}

.platform-header {
  display: flex; align-items: center; gap: 12px; margin-bottom: 16px;
}

.platform-icon { font-size: 28px; }
.platform-header h4 { font-size: 15px; font-weight: 600; color: #1f2937; margin: 0 0 2px; }
.platform-header p { font-size: 12px; color: #9ca3af; margin: 0; }

.platform-cards {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(140px, 1fr));
  gap: 10px;
}

.platform-card {
  padding: 16px 12px;
  background: #fff;
  border: 1px solid #e5e7eb;
  border-radius: 10px;
  text-align: center;
  transition: all 0.15s;
}

.platform-card:hover { border-color: #2563eb; box-shadow: 0 2px 8px rgba(37,99,235,0.08); }

.card-icon { margin-bottom: 8px; color: #374151; display: flex; justify-content: center; }
.card-title { font-size: 14px; font-weight: 600; color: #1f2937; margin-bottom: 2px; }
.card-version { font-size: 11px; color: #9ca3af; margin-bottom: 2px; }
.card-size { font-size: 11px; color: #9ca3af; margin-bottom: 10px; }

.card-dl-btn {
  display: inline-flex; align-items: center; gap: 4px;
  padding: 6px 14px; border-radius: 6px;
  border: 1px solid #d1d5db;
  background: #f3f4f6; color: #9ca3af;
  font-size: 12px; cursor: not-allowed; transition: all 0.12s;
}

.web-hint {
  text-align: center; padding: 12px; font-size: 13px; color: #6b7280;
}

.web-hint a { color: #2563eb; text-decoration: none; font-weight: 500; }
.web-hint a:hover { text-decoration: underline; }
</style>
