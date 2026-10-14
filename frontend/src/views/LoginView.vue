<script setup lang="ts">
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { login } from '../composables/useSession'
import { errorMessage } from '../api/client'
const route = useRoute(), router = useRouter()
const username = ref(''), password = ref(''), busy = ref(false), error = ref('')
async function submit() {
  if (!username.value.trim() || !password.value) { error.value = '请输入用户名和密码'; return }
  busy.value = true; error.value = ''
  try {
    await login(username.value.trim(), password.value)
    const target = String(route.query.redirect ?? '/courses')
    await router.replace(target.startsWith('/') && !target.startsWith('//') ? target : '/courses')
  } catch (e) { error.value = errorMessage(e) }
  finally { busy.value = false }
}
</script>
<template>
  <div class="login-page">
    <section class="login-story"><div class="brand"><span class="brand-mark">知</span><span>知序<small>软件工程学习平台</small></span></div><div class="login-intro"><span class="eyebrow">SOFTWARE ENGINEERING</span><h1>把零散的知识，<br>连成清晰的理解。</h1><p>从课程章节出发，认识每个知识点的学习目标。<br>让教与学，在同一份课程结构中展开。</p><div class="learning-map"><span>课程</span><i>→</i><span>章节</span><i>→</i><span>知识点</span></div></div><small class="muted">课程实践 · 使用模拟账号体验</small></section>
    <section class="login-card panel"><span class="eyebrow">欢迎回来</span><h2>登录学习平台</h2><p class="muted">使用教师或学生账号进入对应工作台。</p>
      <el-alert v-if="error" :title="error" type="error" :closable="false" show-icon class="alert-space" />
      <el-alert v-else-if="route.query.expired" title="登录已失效，请重新登录" type="info" :closable="false" class="alert-space" />
      <el-alert v-else-if="route.query.unavailable" title="暂时无法连接服务，请确认后端已启动后重试" type="warning" :closable="false" class="alert-space" />
      <el-form label-position="top" @submit.prevent="submit">
        <el-form-item label="用户名"><el-input v-model="username" autocomplete="username" placeholder="请输入用户名" size="large" :disabled="busy" /></el-form-item>
        <el-form-item label="密码"><el-input v-model="password" type="password" show-password autocomplete="current-password" placeholder="请输入密码" size="large" :disabled="busy" /></el-form-item>
        <el-button type="primary" size="large" native-type="submit" :loading="busy" class="wide-button">登录 →</el-button>
      </el-form>
      <div class="login-hint">演示账号：teacher / student01 / student02<br>初始密码见项目本地配置或启动说明。</div>
    </section>
  </div>
</template>
