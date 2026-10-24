<script setup lang="ts">
import { computed, nextTick, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import WorkspaceHeader from '../components/WorkspaceHeader.vue'
import LearningSessionPanel from '../components/LearningSessionPanel.vue'
import MarkdownReader from '../components/MarkdownReader.vue'
import ResourceManager from '../components/ResourceManager.vue'
import { useWorkspace } from '../composables/useWorkspace'
import { session } from '../composables/useSession'
import { workspaceApi } from '../api/workspace'
import * as sample from '../api/preview'
import { api, errorMessage } from '../api/client'
import type { LearningTopic, LectureLink } from '../types/learning'
import { renderMarkdown } from '../utils/markdown'
import type { Resource, ResourceContent, ChatReply, Citation } from '../types/workspace'

const { courseId, preview, loading, error, run } = useWorkspace(), route = useRoute()
const router = useRouter()
function selectSession(id: string) { if (route.query.session !== id) void router.replace({ query: { ...route.query, knowledge_point: undefined, mode: '5e', session: id } }) }
const isTeacher = computed(() => session.user?.role === 'teacher')
const resources = ref<Resource[]>([]), selected = ref(''), mode = ref<'rag' | '5e'>('rag'), message = ref(''), busy = ref(false), chatError = ref('')
const turns = ref<{ role: string; reply: ChatReply }[]>([]), media = ref<HTMLVideoElement>(), page = ref(1)
const content = ref<ResourceContent>(), contentLoading = ref(false), contentError = ref(''), citationSection = ref(''), citationJump = ref(0)
const resource = computed(() => resources.value.find(r => r.id === selected.value))
const lectures = computed(() => resources.value.filter(r => r.format === 'markdown'))
const videos = computed(() => resources.value.filter(r => r.type === 'video'))
const videoError = ref('')
const completingVideos = new Set<string>()
async function completeVideo() {
  const item = resource.value, id = courseId.value
  if (preview.value || session.user?.role !== 'student' || item?.type !== 'video' || item.completed) return
  const pendingKey = `${id}/${item.id}/${item.version}`
  if (completingVideos.has(pendingKey)) return
  completingVideos.add(pendingKey); videoError.value = ''
  try {
    const result = await api<Resource>(`/courses/${encodeURIComponent(id)}/resources/${encodeURIComponent(item.id)}/complete`, { method: 'POST' })
    if (id === courseId.value) resources.value = resources.value.map(r => r.id === item.id && r.version === result.version ? { ...r, completed: true } : r)
  } catch (e) { if (id === courseId.value && selected.value === item.id) videoError.value = errorMessage(e) }
  finally { completingVideos.delete(pendingKey) }
}
const learningTopics = ref<LearningTopic[]>([])
const lectureTopics = computed(() => learningTopics.value.filter(p => p.lectures.some(l => l.resource_id === selected.value)))
let topicsGeneration = 0
watch([courseId, preview, isTeacher], async () => {
  const generation = ++topicsGeneration; learningTopics.value = []
  if (preview.value || isTeacher.value) return
  try { const topics = await api<LearningTopic[]>(`/courses/${courseId.value}/learning-templates`); if (generation === topicsGeneration) learningTopics.value = topics }
  catch (e) { if (generation === topicsGeneration) chatError.value = errorMessage(e) }
}, { immediate: true })
function consult(lecture?: LectureLink, pointId?: string) {
  mode.value = 'rag'
  if (lecture) { selected.value = lecture.resource_id; citationSection.value = lecture.section; citationJump.value++ }
  void router.replace({ query: { ...route.query, mode: 'rag', resource: lecture?.resource_id ?? selected.value,
    section: lecture?.section, knowledge_point: pointId ?? route.query.knowledge_point, session: pointId ? undefined : route.query.session } })
}
function switchMode(value: unknown) { void router.replace({ query: { ...route.query, mode: String(value) } }) }
function study(topic: LearningTopic) { void router.push({ query: { mode: '5e', knowledge_point: topic.knowledge_point_id, resource: selected.value } }) }
const isCollection = computed(() => !preview.value && resource.value?.id === 'kb:all')
const resourceTitle = (item: Resource) => isTeacher.value && item.id === 'kb:all' ? '全部课程资料' : item.title
function safeUrl(value: string | null | undefined) { if (!value) return ''; try { const u = new URL(value, location.origin); return ['http:', 'https:'].includes(u.protocol) ? u.href : '' } catch { return '' } }
const url = computed(() => safeUrl(resource.value?.url))
let resourceGeneration = 0
async function refreshResources() {
  const generation = ++resourceGeneration, id = courseId.value
  try {
    const data = await workspaceApi.resources(id)
    if (generation !== resourceGeneration || id !== courseId.value || preview.value) return
    resources.value = data
    if (!data.some(r => r.id === selected.value)) selected.value = data[0]?.id ?? ''
  } catch (e) { if (id === courseId.value) chatError.value = errorMessage(e) }
}
const resourceTimer = setInterval(() => {
  if (!preview.value && resources.value.some(r => ['pending', 'parsing'].includes(r.status ?? ''))) void refreshResources()
}, 2000)
onUnmounted(() => { clearInterval(resourceTimer); resourceGeneration++ })
function load() {
  resourceGeneration++
  resources.value = []; selected.value = ''; turns.value = []; message.value = ''; chatError.value = ''; citationSection.value = ''
  void run(() => preview.value ? Promise.resolve(sample.resources) : workspaceApi.resources(courseId.value), data => {
    resources.value = data
    selected.value = data.find(r => r.id === route.query.resource)?.id ?? data[0]?.id ?? ''
  })
}
watch([preview, courseId], load, { immediate: true })
watch(mode, () => { turns.value = []; chatError.value = '' })
watch(() => [route.query.mode, route.query.session], () => { if (route.query.mode === '5e' || route.query.mode === 'rag') mode.value = route.query.mode }, { immediate: true })
watch(() => [route.query.resource, route.query.section, resources.value], () => {
  if (typeof route.query.resource === 'string' && resources.value.some(r => r.id === route.query.resource)) {
    selected.value = route.query.resource; citationSection.value = typeof route.query.section === 'string' ? route.query.section : ''; citationJump.value++
  }
})
let contentGeneration = 0
async function loadContent() {
  const generation = ++contentGeneration
  content.value = undefined; contentError.value = ''; contentLoading.value = false
  if (preview.value || resource.value?.format !== 'markdown' || (resource.value.status && resource.value.status !== 'ready')) return
  contentLoading.value = true
  try {
    const result = await workspaceApi.resourceContent(courseId.value, selected.value)
    if (generation === contentGeneration) content.value = result
  } catch (e) { if (generation === contentGeneration) contentError.value = errorMessage(e) }
  finally { if (generation === contentGeneration) contentLoading.value = false }
}
watch([selected, preview, () => resource.value?.version, () => resource.value?.status], () => void loadContent())
watch([selected, preview, () => resource.value?.version], () => { videoError.value = ''; void completeVideo() })
function openResource(value: unknown) { citationSection.value = ''; selected.value = String(value); page.value = 1; void router.replace({ query: { mode: 'rag', resource: selected.value } }) }
async function cite(citation: Citation) {
  selected.value = citation.resource_id
  citationSection.value = citation.section ?? citation.title.split(' · ').slice(1).join(' · ')
  citationJump.value++
  page.value = citation.page ?? 1
  await nextTick()
  if (media.value && citation.seconds !== null) media.value.currentTime = citation.seconds
}
async function send() {
  if (!message.value.trim() || !resource.value || busy.value) return
  const text = message.value.trim(); busy.value = true; chatError.value = ''
  turns.value.push({ role: '我', reply: { message: text, citations: [], phase: null } }); message.value = ''
  try {
    const reply = preview.value
      ? { message: '这是界面样例回复。请尝试解释功能需求与质量要求的区别。', citations: [{ resource_id: 'preview-doc', title: '需求规格说明（样例）', page: 2, seconds: null }], phase: mode.value === '5e' ? 'engage · 引入（示例）' : null }
      : await workspaceApi.chat(courseId.value, { resource_id: selected.value, message: text, mode: mode.value })
    turns.value.push({ role: '学习助手', reply })
  } catch (e) { chatError.value = errorMessage(e); message.value = text }
  finally { busy.value = false }
}
</script>
<template>
  <WorkspaceHeader :course-id="courseId" :title="isTeacher ? '课程资料' : '资源学习'" v-model:preview="preview" :loading="loading || busy" :error="error" @reload="load" />
  <ResourceManager v-if="isTeacher && !preview" :course-id="courseId" :resources="resources" @changed="refreshResources" />
  <div v-loading="loading" class="learning-grid" :class="{ 'teacher-resources': isTeacher || mode === '5e' || resource?.type === 'video' }">
    <section v-if="isTeacher || mode !== '5e'" class="panel">
      <h2>课程资源</h2>
      <el-empty v-if="!resources.length" description="暂无可用资源" />
      <el-select v-else :model-value="selected" aria-label="选择学习资源" :disabled="busy" style="width:100%" @change="openResource"><el-option v-for="item in resources" :key="item.id" :value="item.id" :label="resourceTitle(item)" /></el-select>
      <template v-if="resource">
        <h3>{{ resourceTitle(resource) }}</h3><p>{{ resource.description }}</p>
        <div v-if="resource.id !== 'kb:all' && !preview" class="toolbar"><el-tag>{{ resource.origin === 'builtin' ? '系统导入' : '教师上传' }}</el-tag><span>版本 {{ resource.version }}</span><a v-if="resource.download_url" :href="resource.download_url">下载原文件</a></div>
        <el-alert v-if="resource.status && resource.status !== 'ready'" :title="resource.error || '资料正在解析，完成后会自动更新。'" :type="resource.status === 'failed' ? 'warning' : 'info'" :closable="false" />
        <div v-if="!isTeacher && !preview && resource.format === 'markdown'" class="practice-result" aria-label="本讲义对应的课程知识点">
          <strong>本讲义对应的课程知识点</strong>
          <p v-for="topic in lectureTopics" :key="topic.knowledge_point_id">{{ topic.chapter_title }} → {{ topic.name }} <el-button text type="primary" @click="study(topic)">学习这个知识点（5E）</el-button></p>
          <p v-if="!lectureTopics.length" class="muted">这份讲义尚未配置对应的 5E 知识点，可阅读原文或在课程答疑中提问。</p>
        </div>
        <div v-if="isCollection" class="lecture-library">
          <p class="muted">共 {{ lectures.length }} 份讲义、{{ videos.length }} 个视频。已解析的讲义可用于答疑，视频点击即完成。</p>
          <article v-for="video in videos" :key="video.id" class="lecture-library-item"><div><h3>{{ video.title }}</h3><p>课程视频 <el-tag v-if="!isTeacher" :type="video.completed ? 'success' : 'info'">{{ video.completed ? '已完成' : '未完成' }}</el-tag></p></div><el-button @click="openResource(video.id)">观看视频</el-button></article>
          <article v-for="lecture in lectures" :key="lecture.id" class="lecture-library-item"><div><h3>{{ lecture.title }}</h3><p>{{ lecture.origin === 'builtin' ? '系统导入的项目自编讲义' : '教师上传的课程资料' }} · {{ lecture.status === 'failed' ? '解析失败' : ['pending', 'parsing'].includes(lecture.status ?? '') ? '解析中' : '可阅读与答疑' }}</p></div><el-button @click="openResource(lecture.id)">阅读原文</el-button></article>
        </div>
        <div v-else-if="resource.format === 'markdown' && !preview" v-loading="contentLoading" class="lecture-content-container">
          <iframe v-if="resource.file_type === 'pdf' && url" :key="url + resource.version + page" :src="url + '#page=' + page" title="课程 PDF 原文预览" class="resource-document" />
          <p v-if="resource.file_type === 'docx' || resource.file_type === 'pptx'" class="muted">以下为提取的文字预览，原始排版请下载原文件查看。</p>
          <el-alert v-if="contentError" :title="contentError" type="error" :closable="false"><el-button text @click="loadContent">重新加载原文</el-button></el-alert>
          <MarkdownReader v-if="content" :markdown="content.markdown" :title="content.title" :section="citationSection" :jump="citationJump" />
          <p v-else-if="contentLoading" class="muted" role="status">正在加载讲义原文…</p>
        </div>
        <div v-else-if="resource.type === 'video' && url">
          <p v-if="!isTeacher" class="muted"><el-tag :type="resource.completed ? 'success' : 'info'">{{ resource.completed ? '已完成（点击即完成）' : '正在标记完成' }}</el-tag> 打开视频即算完成，不统计观看时长或进度。</p>
          <el-alert v-if="videoError" :title="videoError" type="warning" :closable="false"><el-button text @click="completeVideo">重试标记完成</el-button></el-alert>
          <video :key="url" ref="media" :src="url" controls preload="metadata" class="resource-video" @play="completeVideo" @error="videoError = '视频暂时无法播放，请刷新重试；教师可换用浏览器支持的 MP4 或 WebM 文件。'" />
        </div>
        <iframe v-else-if="url" :key="url + page" :src="url + '#page=' + page" title="课程文档预览" sandbox="allow-same-origin" class="resource-document" />
        <el-empty v-else :description="preview ? '媒体预览区域 · 未加载样例文件' : '当前资源暂不支持原文预览'" />
        <div v-if="url" class="toolbar"><el-input-number v-if="resource.type === 'doc'" v-model="page" :min="1" aria-label="文档页码" /><a :href="url" target="_blank" rel="noopener noreferrer">打开原始资源</a></div>
        <p v-if="!isTeacher && (isCollection || content)" class="muted">回答中的讲义引用可以定位到原文章节。阅读时长暂不计入学习报告。</p>
      </template>
    </section>
    <section v-if="!isTeacher && resource?.type !== 'video'" class="panel">
      <h2>学习助手</h2>
      <el-radio-group v-model="mode" :disabled="busy" @change="switchMode"><el-radio-button value="rag">课程答疑</el-radio-button><el-radio-button value="5e">5E 引导</el-radio-button></el-radio-group>
      <p v-if="mode === 'rag' && !preview" class="muted">答疑只使用当前课程资料，默认不引用模拟学生历史。</p>
      <LearningSessionPanel v-if="mode === '5e' && !preview" :course-id="courseId" :session-id="typeof route.query.session === 'string' ? route.query.session : undefined" :knowledge-point-id="typeof route.query.knowledge_point === 'string' ? route.query.knowledge_point : undefined" :resource-id="selected" @consult="consult" @selected="selectSession" />
      <template v-else>
        <p class="muted">选择具体讲义可限定答疑范围。从错题或小练习进入 5E，可围绕原题继续学习；查完讲义后切回 5E 即可继续。</p>
        <div class="chat-log" aria-live="polite">
          <el-empty v-if="!turns.length" description="选择讲义后开始提问" :image-size="60" />
          <article v-for="(turn, i) in turns" :key="i" class="chat-turn"><strong>{{ turn.role }}</strong><el-tag v-if="turn.reply.phase">{{ turn.reply.phase }}</el-tag><el-tag v-if="turn.reply.personalization" type="warning">参考模拟历史：{{ turn.reply.personalization.matched_knowledge_points.join('、') }}</el-tag><p v-if="turn.role === '我'">{{ turn.reply.message }}</p><div v-else class="markdown-content chat-markdown" v-html="renderMarkdown(turn.reply.message)" /><el-button v-for="(citation, j) in turn.reply.citations" :key="j" text type="primary" @click="cite(citation)">{{ citation.title }}{{ citation.page !== null ? ` · 第 ${citation.page} 页` : citation.seconds !== null ? ` · ${citation.seconds} 秒` : '' }}</el-button></article>
        </div>
        <el-alert v-if="chatError" :title="chatError" type="error" :closable="false" />
        <el-input v-model="message" type="textarea" :rows="3" maxlength="2000" placeholder="输入你的问题" aria-label="提问内容" />
        <el-button type="primary" :loading="busy" :disabled="!resource || !message.trim()" @click="send">发送问题</el-button>
      </template>
    </section>
  </div>
</template>
