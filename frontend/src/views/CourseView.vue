<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { api, errorMessage } from '../api/client'
import { session } from '../composables/useSession'
import type { Course, Page } from '../types/foundation'
const router = useRouter(), courses = ref<Course[]>([]), loading = ref(false), error = ref('')
const dialog = ref(false), saving = ref(false), total = ref(0), page = ref(1)
const form = reactive({ title: '', description: '' })
const isTeacher = computed(() => session.user?.role === 'teacher')
async function load() {
  loading.value = true; error.value = ''
  try { const result = await api<Page<Course>>(`/courses?page=${page.value}&page_size=12`); courses.value = result.items; total.value = result.total }
  catch (e) { error.value = errorMessage(e) }
  finally { loading.value = false }
}
function create() { form.title = ''; form.description = ''; dialog.value = true }
async function save() {
  if (!form.title.trim()) { ElMessage.warning('请填写课程名称'); return }
  saving.value = true
  try { const c = await api<Course>('/courses', { method: 'POST', body: form }); dialog.value = false; await router.push(`/teacher/courses/${c.id}`) }
  catch (e) { ElMessage.error(errorMessage(e)) }
  finally { saving.value = false }
}
onMounted(load)
function closeDialog(done: () => void) { if (!saving.value) done() }
</script>
<template>
  <section class="page-heading heading-row"><div><div class="eyebrow">COURSE CENTER / 01</div><h1>{{ isTeacher ? '组织课程，让知识有序展开。' : '从一门课程，开始今天的学习。' }}</h1><p>{{ isTeacher ? '维护章节、知识点和课程成员，建立清晰的教学结构。' : '浏览已加入的课程，了解章节结构与学习目标。' }}</p></div><el-button v-if="isTeacher" type="primary" size="large" @click="create">＋ 创建课程</el-button></section>
  <el-alert v-if="error" :title="error" type="error" show-icon :closable="false" class="alert-space" />
  <div class="section-bar"><h2>我的课程 <span class="count-badge">{{ total }}</span></h2><el-button @click="load">刷新列表</el-button></div>
  <div v-loading="loading" class="course-grid">
    <article v-for="(course, index) in courses" :key="course.id" class="panel course-card"><div class="panel-meta"><span class="course-icon">{{ String(index + 1 + (page - 1) * 12).padStart(2, '0') }}</span><el-tag type="info" effect="plain">{{ isTeacher ? '教学课程' : '已加入' }}</el-tag></div><h2>{{ course.title }}</h2><p>{{ course.description || '课程简介尚未填写。' }}</p><div class="course-card-footer"><span>章节 · 知识点 · 学习目标</span><el-button type="primary" plain @click="router.push(isTeacher ? `/teacher/courses/${course.id}` : `/courses/${course.id}`)">{{ isTeacher ? '管理课程' : '查看课程' }} →</el-button></div></article>
  </div>
  <el-empty v-if="!loading && !error && !courses.length" :description="isTeacher ? '还没有课程，创建第一门课程吧' : '暂无课程，请联系教师加入课程'" />
  <el-pagination v-if="total > 12" v-model:current-page="page" :page-size="12" :total="total" layout="prev, pager, next" class="pagination" @current-change="load" />
  <el-dialog v-model="dialog" title="创建课程" width="min(540px, 94vw)" :close-on-click-modal="!saving" :before-close="closeDialog">
    <el-form label-position="top" @submit.prevent="save"><el-form-item label="课程名称"><el-input v-model="form.title" maxlength="200" placeholder="例如：软件工程基础" /></el-form-item><el-form-item label="课程简介"><el-input v-model="form.description" type="textarea" :rows="4" maxlength="4000" show-word-limit /></el-form-item></el-form>
    <template #footer><el-button :disabled="saving" @click="dialog = false">取消</el-button><el-button type="primary" :loading="saving" @click="save">创建课程</el-button></template>
  </el-dialog>
</template>
