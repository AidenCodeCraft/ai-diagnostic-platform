<template>
  <div class="chat-view">
    <!-- 空状态由父组件 ChatLayout 的 welcome 区域处理 -->
    <router-view v-if="false" />
  </div>
</template>

<script setup lang="ts">
// ChatView 作为占位路由组件，实际内容由 ChatLayout 渲染
</script>

<style scoped>
.chat-view { display: none; }
</style>
