<template>
  <div class="login-page">
    <div class="login-card">
      <div class="login-header">
        <h1 class="login-title">AI Diagnostic Platform</h1>
        <p class="login-subtitle">设备日志智能诊断平台</p>
      </div>

      <el-form @submit.prevent="handleLogin">
        <el-form-item><el-input v-model="loginForm.username" placeholder="用户名" prefix-icon="User" size="large" /></el-form-item>
        <el-form-item><el-input v-model="loginForm.password" type="password" placeholder="密码" prefix-icon="Lock" show-password size="large" @keyup.enter="handleLogin" /></el-form-item>
        <el-button type="primary" size="large" :loading="loading" @click="handleLogin" style="width:100%">登 录</el-button>
      </el-form>

      <p class="login-hint">账号由管理员统一分配与管理</p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { useUserStore } from '@/stores/user'
import { useLogger } from '@/logger'

const router = useRouter()
const userStore = useUserStore()
const { info, warn, error: logError } = useLogger()
const loading = ref(false)
const loginForm = reactive({ username: '', password: '' })

async function handleLogin() {
  if (!loginForm.username || !loginForm.password) { ElMessage.warning('请输入用户名和密码'); return }
  loading.value = true
  try {
    await userStore.login(loginForm.username, loginForm.password)
    info('Login successful', 'user', { action: 'login', extra: { username: loginForm.username } })
    ElMessage.success('登录成功')
    router.push('/chat')
  } catch (e: any) {
    warn('Login failed', 'user', { action: 'login', extra: { username: loginForm.username, error: e.response?.data?.detail } })
    ElMessage.error(e.response?.data?.detail || '登录失败')
  } finally { loading.value = false }
}
</script>

<style scoped>
.login-page {
  display: flex; align-items: center; justify-content: center;
  min-height: 100vh; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
}
.login-card {
  width: 400px; padding: 40px 36px;
  background: #fff; border-radius: 16px; box-shadow: 0 20px 60px rgba(0,0,0,0.15);
}
.login-header { text-align: center; margin-bottom: 28px; }
.login-title { font-size: 22px; font-weight: 700; color: #1f2937; margin: 0; }
.login-subtitle { font-size: 13px; color: #9ca3af; margin: 6px 0 0; }
.login-hint { text-align: center; font-size: 12px; color: #9ca3af; margin: 16px 0 0; }
</style>
