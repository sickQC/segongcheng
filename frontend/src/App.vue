<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { request } from './api'
const health = ref('正在连接')
onMounted(async () => {
  try { const value = await request<{database: string}>('/health'); health.value = `${value.database.toUpperCase()} · 已连接` }
  catch { health.value = '后端未连接' }
})
</script>

<template>
  <div class="app-shell">
    <aside class="sidebar">
      <a class="brand" href="#/"><span class="brand-mark">知</span><span>知序<small>软件工程学习实验室</small></span></a>
      <div class="nav-label">学习工作台</div>
      <nav><RouterLink to="/" :class="{active: $route.path === '/'}"><span>01</span> 模拟作答</RouterLink><RouterLink to="/diagnoses" :class="{active: $route.path.startsWith('/diagnoses')}"><span>02</span> 诊断记录</RouterLink></nav>
      <div class="scope-note"><span class="eyebrow">SPRINT 0</span><h3>从一次作答开始</h3><p>记录学习过程，检查诊断证据，让每一步都有迹可循。</p><div class="scope-chip">本地课堂演示</div></div>
      <div class="sidebar-footer"><span class="connection-dot"></span>{{ health }}</div>
    </aside>
    <div class="workspace"><header class="topbar"><span>软件工程课程 <span class="slash">/</span> 验证与确认</span><el-tag type="info" effect="plain">模拟学生 · 001</el-tag></header><main><RouterView /></main><footer class="page-footer">Sprint 0 · 未接入课程检索与正式学情评测 · 仅使用模拟学生数据</footer></div>
  </div>
</template>
