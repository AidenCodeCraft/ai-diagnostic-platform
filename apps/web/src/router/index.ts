import { createRouter, createWebHistory } from 'vue-router'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/',
      component: () => import('@/layouts/ChatLayout.vue'),
      redirect: '/chat',
      children: [
        { path: '/chat', name: 'Chat', component: () => import('@/views/ChatView.vue'), meta: { title: 'AI 诊断' } },
      ],
    },
    {
      path: '/knowledge',
      component: () => import('@/layouts/ChatLayout.vue'),
      children: [
        { path: '', name: 'Knowledge', component: () => import('@/views/KnowledgeBase.vue'), meta: { title: '知识库' } },
      ],
    },
    {
      path: '/plugins',
      component: () => import('@/layouts/ChatLayout.vue'),
      children: [
        { path: '', name: 'Plugins', component: () => import('@/views/PluginManager.vue'), meta: { title: '插件管理' } },
      ],
    },
    {
      path: '/reports',
      component: () => import('@/layouts/ChatLayout.vue'),
      children: [
        { path: '', name: 'Reports', component: () => import('@/views/ReportList.vue'), meta: { title: '诊断报告' } },
      ],
    },
  ],
})

export default router
