<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { loadPublicConfig, logout, session } from './composables/useSession'
import { errorMessage } from './api/client'
const router = useRouter()
const health = ref('正在连接'), leaving = ref(false)
onMounted(async () => {
  void loadPublicConfig()
  try { const r = await fetch('/health'); const data = await r.json(); health.value = r.ok ? `${data.database.toUpperCase()} · 已连接` : '数据库待检查' }
  catch { health.value = '后端未连接' }
})
async function signOut() {
  leaving.value = true
  try { await logout(); await router.push('/login') } catch (e) { ElMessage.error(errorMessage(e)) }
  finally { leaving.value = false }
}
</script>
<template>
  <RouterView v-if="$route.path === '/login'" />
  <div v-else class="app-shell">
    <aside class="sidebar">
      <RouterLink class="brand" to="/courses"><span class="brand-mark">知</span><span>知序<small>软件工程学习平台</small></span></RouterLink>
      <div class="nav-label">{{ session.user?.role === 'teacher' ? '教师工作台' : '学习工作台' }}</div>
      <nav>
        <RouterLink to="/courses" :class="{ active: $route.path.includes('courses') }"><span>01</span>我的课程</RouterLink>
        <RouterLink v-if="session.devEnabled && session.user?.role === 'student'" to="/dev/submit" :class="{ active: $route.path === '/dev/submit' }"><span>02</span>单题诊断演示</RouterLink>
        <RouterLink v-if="session.devEnabled && session.user?.role === 'student'" to="/diagnoses" :class="{ active: $route.path.startsWith('/diagnoses') }"><span>03</span>演示诊断记录</RouterLink>
      </nav>
      <div class="scope-note"><span class="eyebrow">一步一步，建立理解</span><h3>从课程结构开始</h3><p>浏览章节与知识点，让学习目标清晰可见。</p><div class="scope-chip">软件工程课程</div></div>
      <div class="sidebar-footer"><span class="connection-dot"></span>{{ health }}</div>
    </aside>
    <div class="workspace">
      <header class="topbar"><span>知序 <span class="slash">/</span>{{ $route.meta.dev ? '课堂演示' : '课程中心' }}</span><div class="user-actions"><el-tag v-if="session.user" effect="plain">{{ session.user.role === 'teacher' ? '教师' : '学生' }} · {{ session.user.display_name }}</el-tag><el-button v-if="session.user" text :loading="leaving" @click="signOut">退出登录</el-button><RouterLink v-else to="/login">登录</RouterLink></div></header>
      <main><RouterView :key="$route.path" /></main>
      <footer class="page-footer">知序 · 软件工程课程智能学习辅助系统</footer>
    </div>
  </div>
</template>
