<template>
  <!-- ChatView: 对话视图占位组件，实际对话内容由父组件 ChatLayout 的 chat-content 区域渲染。
       当路由逻辑需要在此渲染内容时（如扩展为嵌套路由），本组件提供基本容器。 -->
  <div class="chat-view">
    <slot />
  </div>
</template>

<script setup lang="ts">
// ChatView 作为路由占位组件，实际对话界面由 ChatLayout 通过条件渲染管理。
// 保留此组件以保证路由配置完整性，并为未来扩展（如嵌套子路由）预留容器。
</script>

<style scoped>
.chat-view {
  /* 保持透明容器，不干扰父组件布局 */
  width: 100%;
  height: 100%;
}
</style>
