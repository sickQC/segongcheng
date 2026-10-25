<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { loadPublicConfig, logout, session } from './composables/useSession'
import { api, errorMessage } from './api/client'
import type { Course, Outline, Page } from './types/foundation'
const router = useRouter(), route = useRoute()
const health = ref('正在连接'), leaving = ref(false)
const sidebarCourses = ref<Course[]>([]), selectedCourseId = ref(''), courseLoading = ref(false), courseError = ref('')
const isTeacher = computed(() => session.user?.role === 'teacher')
const routeCourseId = computed(() => /^\/(?:teacher\/)?courses\//.test(route.path) ? String(route.params.id ?? '') : '')
const activeCourseId = computed(() => routeCourseId.value || selectedCourseId.value)
const courseLinks = computed(() => {
  if (!activeCourseId.value) return []
  const base = `/courses/${encodeURIComponent(activeCourseId.value)}`
  const links = [
    { label: isTeacher.value ? '课程管理' : '课程目录', path: isTeacher.value ? `/teacher${base}` : base, detail: '章节、知识点与小练习' },
    { label: isTeacher.value ? '课程讲义' : '资源学习', path: `${base}/learn`, detail: isTeacher.value ? '阅读讲义与查看章节' : '课程答疑与 5E 引导' },
    { label: isTeacher.value ? '测验管理' : '课程测验', path: `${base}/quiz`, detail: isTeacher.value ? '发布测验与题目设置' : '作答、成绩与错题诊断' },
  ]
  if (isTeacher.value) links.push({ label: '教师看板', path: `/teacher${base}/dashboard`, detail: '班级学情与学生原始作答' })
  else links.push({ label: '学习报告', path: `${base}/report`, detail: '学习记录与综合诊断' }, { label: '知识图谱（演示）', path: `${base}/graph-demo`, detail: '示例知识结构与学习路径' })
  return links
})
let sidebarGeneration = 0
watch(() => [session.user?.id, route.path] as const, async ([userId, path], previous) => {
  const run = ++sidebarGeneration
  if (!userId) { sidebarCourses.value = []; selectedCourseId.value = ''; courseError.value = ''; courseLoading.value = false; return }
  if (userId !== previous?.[0]) { sidebarCourses.value = []; selectedCourseId.value = '' }
  const targetId = routeCourseId.value
  if (path !== '/courses' && sidebarCourses.value.some(course => course.id === targetId)) { selectedCourseId.value = targetId; courseLoading.value = false; return }
  courseLoading.value = true; courseError.value = ''
  try {
    const result = await api<Page<Course>>('/courses?page_size=100')
    if (run !== sidebarGeneration) return
    const courses = result.items
    if (targetId && !courses.some(course => course.id === targetId)) {
      const outline = await api<Outline>(`/courses/${encodeURIComponent(targetId)}/outline`)
      if (run !== sidebarGeneration) return
      courses.push(outline.course)
    }
    sidebarCourses.value = courses
    selectedCourseId.value = targetId || (courses.some(course => course.id === selectedCourseId.value) ? selectedCourseId.value : courses[0]?.id ?? '')
  } catch (e) { if (run === sidebarGeneration) { sidebarCourses.value = []; selectedCourseId.value = ''; courseError.value = errorMessage(e) } }
  finally { if (run === sidebarGeneration) courseLoading.value = false }
}, { immediate: true })
function switchCourse(value: unknown) {
  const id = String(value)
  if (!sidebarCourses.value.some(course => course.id === id)) return
  selectedCourseId.value = id
  const base = `/courses/${encodeURIComponent(id)}`
  const section = routeCourseId.value ? route.path.split('/').at(-1) : ''
  const target = section === 'dashboard' && isTeacher.value ? `/teacher${base}/dashboard`
    : ['learn', 'quiz', 'report', 'graph-demo'].includes(section ?? '') ? `${base}/${section}`
      : isTeacher.value ? `/teacher${base}` : base
  void router.push(target)
}
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
      <nav class="sidebar-nav" aria-label="工作台导航">
        <RouterLink to="/courses" :class="{ active: $route.path === '/courses' }" :aria-current="$route.path === '/courses' ? 'page' : undefined"><span>01</span>我的课程</RouterLink>
      </nav>
      <div v-if="session.user" class="sidebar-course-context">
        <label for="sidebar-course">当前课程</label>
        <el-select id="sidebar-course" :model-value="activeCourseId || undefined" :loading="courseLoading" :disabled="courseLoading || !sidebarCourses.length" placeholder="选择课程" aria-label="切换当前课程" @change="switchCourse">
          <el-option v-for="course in sidebarCourses" :key="course.id" :label="course.title" :value="course.id" />
        </el-select>
        <p v-if="courseError" class="sidebar-course-message">{{ courseError }}</p>
        <p v-else-if="!courseLoading && !sidebarCourses.length" class="sidebar-course-message">{{ isTeacher ? '创建课程后即可使用课程工作台。' : '加入课程后即可查看学习入口。' }}</p>
      </div>
      <nav v-if="courseLinks.length" class="sidebar-nav course-shortcuts" aria-label="当前课程导航">
        <RouterLink v-for="(item, index) in courseLinks" :key="item.path" :to="item.path" :class="{ active: $route.path === item.path }" :aria-current="$route.path === item.path ? 'page' : undefined"><span>{{ String(index + 2).padStart(2, '0') }}</span><div>{{ item.label }}<small>{{ item.detail }}</small></div></RouterLink>
      </nav>
      <nav v-if="session.devEnabled && session.user?.role === 'student'" class="sidebar-nav dev-shortcuts" aria-label="开发演示导航">
        <RouterLink to="/dev/submit" :class="{ active: $route.path === '/dev/submit' }">单题诊断演示</RouterLink>
        <RouterLink to="/diagnoses" :class="{ active: $route.path.startsWith('/diagnoses') }">演示诊断记录</RouterLink>
      </nav>
      <div class="scope-note"><span class="eyebrow">{{ isTeacher ? '围绕课程，组织教学' : '一步一步，建立理解' }}</span><h3>{{ isTeacher ? '从教学安排到学情反馈' : '从课程结构开始' }}</h3><p>{{ isTeacher ? '维护课程与测验，结合学生作答查看班级学情。' : '浏览章节与知识点，让学习目标清晰可见。' }}</p><div class="scope-chip">软件工程课程</div></div>
      <div class="sidebar-footer"><span class="connection-dot"></span>{{ health }}</div>
    </aside>
    <div class="workspace">
      <header class="topbar"><span>知序 <span class="slash">/</span>{{ $route.meta.dev ? '课堂演示' : '课程中心' }}</span><div class="user-actions"><el-tag v-if="session.user" effect="plain">{{ session.user.role === 'teacher' ? '教师' : '学生' }} · {{ session.user.display_name }}</el-tag><el-button v-if="session.user" text :loading="leaving" @click="signOut">退出登录</el-button><RouterLink v-else to="/login">登录</RouterLink></div></header>
      <main><RouterView :key="$route.path" /></main>
      <footer class="page-footer">知序 · 软件工程课程智能学习辅助系统</footer>
    </div>
  </div>
</template>
