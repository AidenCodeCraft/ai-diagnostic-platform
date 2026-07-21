<template>
  <div class="login-page">
    <div class="login-card">
      <div class="login-header">
        <h1 class="login-title">AI Diagnostic Platform</h1>
        <p class="login-subtitle">设备日志智能诊断平台</p>
      </div>

      <el-tabs v-model="mode" class="login-tabs" stretch>
        <el-tab-pane label="登录" name="login">
          <el-form @submit.prevent="handleLogin">
            <el-form-item><el-input v-model="loginForm.username" placeholder="用户名" prefix-icon="User" size="large" /></el-form-item>
            <el-form-item><el-input v-model="loginForm.password" type="password" placeholder="密码" prefix-icon="Lock" show-password size="large" @keyup.enter="handleLogin" /></el-form-item>
            <el-button type="primary" size="large" :loading="loading" @click="handleLogin" style="width:100%">登 录</el-button>
          </el-form>
        </el-tab-pane>
        <el-tab-pane label="注册" name="register">
          <el-form @submit.prevent="handleRegister">
            <el-form-item><el-input v-model="registerForm.username" placeholder="用户名" size="large" /></el-form-item>
            <el-form-item><el-input v-model="registerForm.email" placeholder="邮箱（选填）" size="large" /></el-form-item>
            <el-form-item><el-input v-model="registerForm.password" type="password" placeholder="密码（至少6位）" show-password size="large" /></el-form-item>
            <el-button type="primary" size="large" :loading="loading" @click="handleRegister" style="width:100%">注 册</el-button>
          </el-form>
        </el-tab-pane>
      </el-tabs>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { useUserStore } from '@/stores/user'

const router = useRouter()
const userStore = useUserStore()
const mode = ref('login')
const loading = ref(false)

const loginForm = reactive({ username: '', password: '' })
const registerForm = reactive({ username: '', email: '', password: '' })

async function handleLogin() {
  if (!loginForm.username || !loginForm.password) { ElMessage.warning('请输入用户名和密码'); return }
  loading.value = true
  try {
    await userStore.login(loginForm.username, loginForm.password)
    ElMessage.success('登录成功')
    router.push('/chat')
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail || '登录失败')
  } finally { loading.value = false }
}

async function handleRegister() {
  if (!registerForm.username || !registerForm.password) { ElMessage.warning('请输入用户名和密码'); return }
  if (registerForm.password.length < 6) { ElMessage.warning('密码至少6位'); return }
  loading.value = true
  try {
    await userStore.register(registerForm.username, registerForm.password, registerForm.email || undefined)
    ElMessage.success('注册成功，请登录')
    mode.value = 'login'
    loginForm.username = registerForm.username
    registerForm.username = ''; registerForm.email = ''; registerForm.password = ''
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail || '注册失败')
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
.login-tabs { margin-bottom: 4px; }
</style>
