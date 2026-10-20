<script setup lang="ts">
import { computed, nextTick, reactive, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { api, errorMessage } from '../api/client'
import { session } from '../composables/useSession'
import { bloomLabels, type Bloom, type Chapter, type KnowledgePoint, type Member, type Outline, type Page, type PracticeExercise } from '../types/foundation'
import PracticePanel from '../components/PracticePanel.vue'
const route = useRoute(), outline = ref<Outline>(), loading = ref(false), error = ref('')
const editable = computed(() => session.user?.role === 'teacher' && !!route.meta.teacher)
const courseId = computed(() => String(route.params.id))
const count = computed(() => outline.value?.chapters.reduce((sum, c) => sum + c.knowledge_points.length, 0) ?? 0)
const active = ref<string[]>([]), chapterDialog = ref(false), kpDialog = ref(false), saving = ref(false)
const chapterForm = reactive({ id: '', title: '', sort_order: 0 })
const kpForm = reactive({ id: '', chapter_id: '', code: '', name: '', definition: '', difficulty: 2, bloom_level: 'understand' as Bloom })
const members = ref<Member[]>([]), memberName = ref(''), memberBusy = ref(false), memberError = ref(''), memberPage = ref(1), memberTotal = ref(0)
const practices = ref<PracticeExercise[]>([])
const fiveEPoints = ref<string[]>([])
const practiceFor = (kpId: string) => practices.value.find(p => p.knowledge_point_id === kpId)
async function loadPractices() { practices.value = await api<PracticeExercise[]>(`/courses/${courseId.value}/practices`) }
let generation = 0
async function loadMembers() {
  memberError.value = ''
  try { const data = await api<Page<Member>>(`/courses/${courseId.value}/members?page=${memberPage.value}&page_size=20`); members.value = data.items; memberTotal.value = data.total }
  catch (e) { memberError.value = errorMessage(e) }
}
async function load() {
  const run = ++generation
  loading.value = true; error.value = ''
  try {
    const data = await api<Outline>(`/courses/${courseId.value}/outline`)
    if (run !== generation) return
    outline.value = data; active.value = data.chapters.map(c => c.id)
    await loadPractices()
    const templates = await api<{ knowledge_point_id: string }[]>(`/courses/${courseId.value}/learning-templates`)
    if (run !== generation) return
    fiveEPoints.value = templates.map(point => point.knowledge_point_id)
    await nextTick()
    if (typeof route.query.practice === 'string') document.getElementById(`practice-${route.query.practice}`)?.scrollIntoView({ block: 'center' })
    else if (typeof route.query.knowledge_point === 'string') document.getElementById(`knowledge-${route.query.knowledge_point}`)?.scrollIntoView({ block: 'center' })
    if (editable.value) await loadMembers()
  } catch (e) { if (run === generation) error.value = errorMessage(e) }
  finally { if (run === generation) loading.value = false }
}
function openChapter(chapter?: Chapter) {
  Object.assign(chapterForm, chapter ? { id: chapter.id, title: chapter.title, sort_order: chapter.sort_order } : { id: '', title: '', sort_order: (outline.value?.chapters.length ?? 0) + 1 }); chapterDialog.value = true
}
async function saveChapter() {
  if (!chapterForm.title.trim()) { ElMessage.warning('请填写章节名称'); return }
  saving.value = true
  try {
    await api(chapterForm.id ? `/chapters/${chapterForm.id}` : `/courses/${courseId.value}/chapters`, { method: chapterForm.id ? 'PATCH' : 'POST', body: { title: chapterForm.title, sort_order: chapterForm.sort_order } })
    chapterDialog.value = false; ElMessage.success('章节已保存'); await load()
  } catch (e) { ElMessage.error(errorMessage(e)) }
  finally { saving.value = false }
}
function openKp(chapter: Chapter, kp?: KnowledgePoint) {
  Object.assign(kpForm, kp ? { ...kp, chapter_id: chapter.id } : { id: '', chapter_id: chapter.id, code: '', name: '', definition: '', difficulty: 2, bloom_level: 'understand' }); kpDialog.value = true
}
async function saveKp() {
  if (!kpForm.code.trim() || !kpForm.name.trim() || !kpForm.definition.trim()) { ElMessage.warning('请填写编号、名称和定义'); return }
  saving.value = true
  try {
    const body = { name: kpForm.name, definition: kpForm.definition, difficulty: kpForm.difficulty, bloom_level: kpForm.bloom_level, ...(kpForm.id ? {} : { code: kpForm.code }) }
    await api(kpForm.id ? `/knowledge-points/${kpForm.id}` : `/chapters/${kpForm.chapter_id}/knowledge-points`, { method: kpForm.id ? 'PATCH' : 'POST', body })
    kpDialog.value = false; ElMessage.success('知识点已保存'); await load()
  } catch (e) { ElMessage.error(errorMessage(e)) }
  finally { saving.value = false }
}
async function removeKp(kp: KnowledgePoint) {
  try { await ElMessageBox.confirm(`确定删除“${kp.name}”？`, '删除知识点', { confirmButtonText: '删除', cancelButtonText: '取消', type: 'warning' }) }
  catch { return }
  try { await api(`/knowledge-points/${kp.id}`, { method: 'DELETE' }); ElMessage.success('已删除'); await load() }
  catch (e) { ElMessage.error(errorMessage(e)) }
}
async function addMember() {
  if (!memberName.value.trim()) return
  memberBusy.value = true; memberError.value = ''
  try { await api(`/courses/${courseId.value}/members`, { method: 'POST', body: { username: memberName.value.trim() } }); memberName.value = ''; memberPage.value = 1; await loadMembers(); ElMessage.success('学生已加入课程') }
  catch (e) { memberError.value = errorMessage(e) }
  finally { memberBusy.value = false }
}
watch(() => route.fullPath, () => { outline.value = undefined; members.value = []; memberPage.value = 1; void load() }, { immediate: true })
function closeDialog(done: () => void) { if (!saving.value) done() }
</script>
<template>
  <div class="toolbar"><RouterLink to="/courses"><el-button>← 我的课程</el-button></RouterLink><el-button @click="load">刷新课程</el-button></div>
  <el-alert v-if="error" :title="error" type="error" :closable="false" show-icon class="alert-space" />
  <div v-loading="loading" class="course-detail">
    <template v-if="outline">
      <section class="page-heading heading-row"><div><span class="eyebrow">{{ editable ? 'TEACHING WORKSPACE' : 'COURSE OUTLINE' }}</span><h1>{{ outline.course.title }}</h1><p>{{ outline.course.description || '沿着章节目录，了解课程知识结构。' }}</p></div><el-button v-if="editable" type="primary" size="large" @click="openChapter()">＋ 新建章节</el-button></section>
      <div class="course-summary"><div><strong>{{ outline.chapters.length }}</strong><span>课程章节</span></div><div><strong>{{ count }}</strong><span>知识点</span></div><p>{{ editable ? '编辑完成后，课程成员刷新目录即可看到更新。' : '阅读知识点定义，了解每一章节的学习目标。' }}</p></div>
      <nav class="work-nav"><RouterLink :to="`/courses/${courseId}/learn`">{{ editable ? '课程讲义' : '资源学习' }}</RouterLink><RouterLink :to="`/courses/${courseId}/quiz`">{{ editable ? '测验管理' : '课程测验' }}</RouterLink><RouterLink v-if="session.user?.role === 'student'" :to="`/courses/${courseId}/report`">学习报告</RouterLink><RouterLink v-if="editable" :to="`/teacher/courses/${courseId}/dashboard`">教师看板</RouterLink></nav>
      <div class="section-bar"><h2>章节目录</h2><span class="muted">按教学顺序排列</span></div>
      <el-empty v-if="!outline.chapters.length" :description="editable ? '暂无章节，点击右上角新建章节' : '教师尚未发布章节'" />
      <el-collapse v-model="active" class="chapter-list">
        <el-collapse-item v-for="chapter in outline.chapters" :key="chapter.id" :name="chapter.id">
          <template #title><div class="chapter-title"><span class="chapter-order">{{ String(chapter.sort_order).padStart(2, '0') }}</span><strong>{{ chapter.title }}</strong><span class="muted">{{ chapter.knowledge_points.length }} 个知识点</span></div></template>
          <div v-if="editable" class="chapter-actions"><el-button size="small" @click="openChapter(chapter)">编辑章节</el-button><el-button size="small" type="primary" plain @click="openKp(chapter)">＋ 添加知识点</el-button></div>
          <el-empty v-if="!chapter.knowledge_points.length" description="本章节暂无知识点" :image-size="60" />
          <article v-for="kp in chapter.knowledge_points" :id="`knowledge-${kp.id}`" :key="kp.id" class="knowledge-card"><div class="panel-meta"><span class="eyebrow">{{ kp.code }}</span><div class="tag-row"><el-tag size="small" effect="plain">{{ bloomLabels[kp.bloom_level] }}</el-tag><el-tag size="small" type="info" effect="plain">难度 {{ kp.difficulty }} / 5</el-tag></div></div><h3>{{ kp.name }}</h3><p>{{ kp.definition }}</p><RouterLink v-if="!editable && fiveEPoints.includes(kp.id)" :to="{ path: `/courses/${courseId}/learn`, query: { mode: '5e', knowledge_point: kp.id } }"><el-button text type="primary">学习本知识点（5E）</el-button></RouterLink><PracticePanel :course-id="courseId" :chapter-id="chapter.id" :knowledge-point-id="kp.id" :exercise="practiceFor(kp.id)" :editable="editable" :five-e-available="fiveEPoints.includes(kp.id)" :focus="route.query.practice === kp.id" @created="loadPractices" /><div v-if="editable" class="knowledge-actions"><el-button size="small" text type="primary" @click="openKp(chapter, kp)">编辑</el-button><el-button size="small" text type="danger" @click="removeKp(kp)">删除</el-button></div></article>
        </el-collapse-item>
      </el-collapse>
      <section v-if="editable" class="panel member-panel"><div class="section-bar"><h2>课程成员</h2><span class="muted">{{ memberTotal }} 人</span></div><p class="muted">通过已存在的学生用户名加入课程。演示学生：student01、student02。</p><el-alert v-if="memberError" :title="memberError" type="error" :closable="false" class="alert-space" /><el-form inline @submit.prevent="addMember"><el-form-item label="学生用户名"><el-input v-model="memberName" placeholder="例如 student01" maxlength="100" /></el-form-item><el-form-item><el-button native-type="submit" type="primary" :loading="memberBusy">加入课程</el-button></el-form-item></el-form><el-table :data="members"><el-table-column prop="user.display_name" label="显示名称" /><el-table-column prop="user.username" label="用户名" /><el-table-column label="身份"><template #default="scope">{{ scope.row.role === 'teacher' ? '教师' : '学生' }}</template></el-table-column></el-table><el-pagination v-if="memberTotal > 20" v-model:current-page="memberPage" :page-size="20" :total="memberTotal" layout="prev, pager, next" @current-change="loadMembers" /></section>
    </template>
  </div>
  <el-dialog v-model="chapterDialog" :title="chapterForm.id ? '编辑章节' : '新建章节'" width="min(540px, 94vw)" :close-on-click-modal="!saving" :before-close="closeDialog"><el-form label-position="top" @submit.prevent="saveChapter"><el-form-item label="章节名称"><el-input v-model="chapterForm.title" maxlength="200" /></el-form-item><el-form-item label="显示顺序"><el-input-number v-model="chapterForm.sort_order" :min="0" :max="10000" /></el-form-item></el-form><template #footer><el-button :disabled="saving" @click="chapterDialog = false">取消</el-button><el-button type="primary" :loading="saving" @click="saveChapter">保存章节</el-button></template></el-dialog>
  <el-dialog v-model="kpDialog" :title="kpForm.id ? '编辑知识点' : '添加知识点'" width="min(600px, 94vw)" :close-on-click-modal="!saving" :before-close="closeDialog"><el-form label-position="top" @submit.prevent="saveKp"><el-form-item label="知识点编号"><el-input v-model="kpForm.code" :disabled="!!kpForm.id" maxlength="100" placeholder="例如 KP-REQ-03，同课程内唯一" /></el-form-item><el-form-item label="知识点名称"><el-input v-model="kpForm.name" maxlength="100" /></el-form-item><el-form-item label="定义与说明"><el-input v-model="kpForm.definition" type="textarea" :rows="4" maxlength="8000" show-word-limit /></el-form-item><div class="form-row"><el-form-item label="难度"><el-input-number v-model="kpForm.difficulty" :min="1" :max="5" /></el-form-item><el-form-item label="学习目标"><el-select v-model="kpForm.bloom_level" style="width:160px"><el-option v-for="(label, key) in bloomLabels" :key="key" :label="label" :value="key" /></el-select></el-form-item></div></el-form><template #footer><el-button :disabled="saving" @click="kpDialog = false">取消</el-button><el-button type="primary" :loading="saving" @click="saveKp">保存知识点</el-button></template></el-dialog>
</template>
