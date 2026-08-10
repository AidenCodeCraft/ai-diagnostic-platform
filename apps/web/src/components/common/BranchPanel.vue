<template>
  <div class="branch-panel">
    <div class="branch-label">
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <line x1="6" y1="3" x2="6" y2="15"/><circle cx="18" cy="6" r="3"/><circle cx="6" cy="18" r="3"/><path d="M18 9a9 9 0 0 1-9 9"/>
      </svg>
      <span>分支 ({{ branches.length }})</span>
    </div>
    <div class="branch-list">
      <div
        v-for="branch in branches"
        :key="branch.branchId"
        class="branch-item"
        :class="{ active: branch.branchId === currentBranchId }"
        @click="$emit('switch', branch.branchId)"
      >
        <span class="branch-name">{{ branch.name }}</span>
        <span class="branch-time">{{ formatTime(branch.createdAt) }}</span>
        <button
          v-if="branch.branchId !== currentBranchId"
          class="branch-delete"
          @click.stop="$emit('delete', branch.branchId)"
          title="删除分支"
        >&times;</button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { BranchNode } from '@/composables/useChatBranch'

defineProps<{
  branches: BranchNode[]
  currentBranchId: string | null
}>()

defineEmits<{
  (e: 'switch', branchId: string): void
  (e: 'delete', branchId: string): void
}>()

function formatTime(ts: number) {
  const d = new Date(ts)
  return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}:${String(d.getSeconds()).padStart(2, '0')}`
}
</script>

<style scoped>
.branch-panel {
  margin: 0 24px 8px;
  padding: 8px 12px;
  background: #f9fafb;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  max-width: var(--chat-content-width);
  width: 100%;
  align-self: center;
}

.branch-label {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: #6b7280;
  margin-bottom: 6px;
}

.branch-list {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}

.branch-item {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px 10px;
  border-radius: 6px;
  border: 1px solid #d1d5db;
  background: #fff;
  font-size: 12px;
  cursor: pointer;
  transition: all 0.12s;
}

.branch-item:hover { border-color: #93c5fd; background: #eff6ff; }
.branch-item.active { border-color: #2563eb; background: #eff6ff; color: #2563eb; font-weight: 500; }

.branch-name { max-width: 100px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.branch-time { color: #9ca3af; white-space: nowrap; }

.branch-delete {
  background: none; border: none; font-size: 16px; color: #9ca3af;
  cursor: pointer; padding: 0 2px; line-height: 1; border-radius: 4px;
}
.branch-delete:hover { color: #ef4444; background: #fef2f2; }
</style>
