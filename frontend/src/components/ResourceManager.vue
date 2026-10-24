<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { api, errorMessage } from '../api/client'
import type { Outline } from '../types/foundation'
import type { Resource, ResourceVersion } from '../types/workspace'

const props = defineProps<{ courseId: string; resources: Resource[] }>()
const emit = defineEmits<{ changed: [] }>()
const outline = ref<Outline>(), busy = ref(false), error = ref(''), dialog = ref(false)
const editing = ref<Resource>(), title = ref(''), description = ref(''), chapter = ref(''), points = ref<string[]>([])
const chosen = ref<File>(), versionTarget = ref<Resource>(), versions = ref<ResourceVersion[]>([]), history = ref<Resource>()
const fileInput = ref<HTMLInputElement>(), replacementInput = ref<HTMLInputElement>()
const documents = computed(() => props.resources.filter(r => r.id !== 'kb:all'))
const knowledgePoints = computed(() => outline.value?.chapters.filter(c => !chapter.value || c.id === chapter.value).flatMap(c => c.knowledge_points) ?? [])
const base = computed(() => `/courses/${encodeURIComponent(props.courseId)}/resources`)
const key = (r: Resource) => `${base.value}/${encodeURIComponent(r.id)}`
const statusNames: Record<string, string> = { pending: '等待解析', parsing: '解析中', ready: '可学习', failed: '解析失败' }
const statusLabel = (s?: string) => statusNames[s ?? 'ready'] ?? s
let generation = 0
watch(() => props.courseId, async () => {
  const current = ++generation; outline.value = undefined; dialog.value = false; history.value = undefined
  try { const data = await api<Outline>(`/courses/${encodeURIComponent(props.courseId)}/outline`); if (current === generation) outline.value = data }
  catch (e) { if (current === generation) error.value = errorMessage(e) }
}, { immediate: true })

function open(resource?: Resource) {
  editing.value = resource; title.value = resource?.title ?? ''; description.value = resource?.description ?? ''
  chapter.value = resource?.chapter_id ?? ''; points.value = [...(resource?.knowledge_point_ids ?? [])]
  chosen.value = undefined; if (fileInput.value) fileInput.value.value = ''; error.value = ''; dialog.value = true
}
function pick(event: Event) { chosen.value = (event.target as HTMLInputElement).files?.[0] }
const isVideo = (file?: File) => /\.(mp4|webm)$/i.test(file?.name ?? '')
function validSize(file?: File) {
  const limit = isVideo(file) ? 200 : 20
  if (file && file.size > limit * 1024 * 1024) { error.value = `${isVideo(file) ? '视频' : '文档'}大小不能超过 ${limit} MiB`; return false }
  return true
}
function changeChapter() { points.value = points.value.filter(id => knowledgePoints.value.some(p => p.id === id)) }
async function action(work: () => Promise<unknown>) {
  if (busy.value) return
  busy.value = true; error.value = ''
  try { await work(); emit('changed') }
  catch (e) { error.value = errorMessage(e) }
  finally { busy.value = false }
}
async function save() {
  if (!title.value.trim() || (!editing.value && !chosen.value)) { error.value = '请填写标题并选择文件'; return }
  if (!validSize(chosen.value)) return
  await action(async () => {
    if (editing.value) {
      await api(key(editing.value), { method: 'PATCH', body: { title: title.value, description: description.value, chapter_id: chapter.value, knowledge_point_ids: points.value } })
    } else {
      const body = new FormData(); body.set('file', chosen.value!); body.set('title', title.value); body.set('description', description.value)
      body.set('chapter_id', chapter.value); body.set('knowledge_point_ids', JSON.stringify(points.value))
      await api(base.value, { method: 'POST', body })
      ElMessage.success(isVideo(chosen.value) ? '视频已上传，学生可以打开观看。' : '文件已保存，正在解析；完成后自动更新状态。')
    }
    dialog.value = false
  })
}
async function remove(resource: Resource) {
  try { await ElMessageBox.confirm(`删除“${resource.title}”后，学生将无法访问，答疑也不再检索。`, '删除资料', { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' }) }
  catch { return }
  await action(() => api(key(resource), { method: 'DELETE' }))
}
async function importBuiltin() { await action(async () => { const result = await api<{ imported: number }>(`${base.value}/import-builtin`, { method: 'POST' }); ElMessage.success(`已导入 ${result.imported} 份讲义，已有内容保持原样。`) }) }
async function retry(resource: Resource) { await action(() => api(`${key(resource)}/retry`, { method: 'POST' })) }
function chooseReplacement(resource: Resource) { versionTarget.value = resource; replacementInput.value?.click() }
async function replace(event: Event) {
  const input = event.target as HTMLInputElement, file = input.files?.[0], resource = versionTarget.value
  input.value = ''
  if (!file || !resource) return
  if (!validSize(file)) return
  await action(async () => { const body = new FormData(); body.set('file', file); await api(`${key(resource)}/versions`, { method: 'POST', body }); ElMessage.success(isVideo(file) ? '新版视频已上传，旧版本保留。' : '新版本已保存，正在解析；旧版本保留。') })
}
async function showVersions(resource: Resource) {
  error.value = ''
  try { versions.value = await api<ResourceVersion[]>(`${key(resource)}/versions`); history.value = resource }
  catch (e) { error.value = errorMessage(e) }
}
async function activate(version: ResourceVersion) {
  const resource = history.value; if (!resource) return
  await action(async () => { await api(`${key(resource)}/versions/${version.version}/activate`, { method: 'POST' }); history.value = undefined })
}
</script>

<template>
  <section class="panel resource-management" aria-label="教师资料管理">
    <div class="section-bar"><h2>资料管理</h2><div class="toolbar"><el-button :disabled="busy" @click="importBuiltin">导入六份示例讲义</el-button><el-button type="primary" :disabled="busy" @click="open()">上传资料</el-button><el-button :disabled="busy" @click="emit('changed')">刷新状态</el-button></div></div>
    <p class="muted">支持 MP4、WebM 视频，每份不超过 200 MiB；文档支持 PDF、DOCX、PPTX、Markdown、UTF-8 TXT，每份不超过 20 MiB。视频按学生点击即完成，不统计观看时长。扫描件请先 OCR；旧版 DOC/PPT 请先转换。</p>
    <el-alert v-if="error" :title="error" type="error" :closable="false" />
    <el-empty v-if="!documents.length" description="上传教学资料，或导入项目自编示例讲义" />
    <article v-for="resource in documents" :key="resource.id" class="knowledge-card">
      <div class="panel-meta"><strong>{{ resource.title }}</strong><div class="tag-row"><el-tag effect="plain">{{ resource.type === 'video' ? '视频' : '讲义' }}</el-tag><el-tag :type="resource.status === 'failed' ? 'danger' : resource.status === 'ready' ? 'success' : 'info'">{{ statusLabel(resource.status) }}</el-tag><el-tag effect="plain">{{ resource.origin === 'builtin' ? '系统导入' : '教师上传' }}</el-tag><span>版本 {{ resource.version }}</span></div></div>
      <p>{{ resource.filename }} · {{ Math.ceil((resource.size_bytes ?? 0) / 1024) }} KB · {{ resource.knowledge_point_ids.length }} 个关联知识点</p>
      <p v-if="resource.error" role="alert">{{ resource.error }}</p>
      <div class="toolbar"><el-button :disabled="busy" @click="open(resource)">编辑信息与关联</el-button><el-button :disabled="busy || ['pending', 'parsing'].includes(resource.status ?? '')" @click="chooseReplacement(resource)">更新文件</el-button><el-button :disabled="busy" @click="showVersions(resource)">版本记录</el-button><el-button v-if="resource.status === 'failed'" :disabled="busy" @click="retry(resource)">重新解析</el-button><a v-if="resource.download_url" :href="resource.download_url">下载原文件</a><el-button type="danger" text :disabled="busy" @click="remove(resource)">删除</el-button></div>
    </article>
    <input ref="replacementInput" type="file" accept=".pdf,.docx,.pptx,.md,.txt,.mp4,.webm" hidden aria-label="选择更新文件" @change="replace" />
    <el-dialog v-model="dialog" :title="editing ? '编辑资料' : '上传教学资料'" width="min(640px, 94vw)" :close-on-click-modal="!busy" :show-close="!busy">
      <el-alert v-if="error" :title="error" type="error" :closable="false" />
      <el-form label-position="top" @submit.prevent="save">
        <el-form-item label="标题"><el-input v-model="title" maxlength="200" aria-label="资料标题" /></el-form-item>
        <el-form-item label="说明"><el-input v-model="description" type="textarea" maxlength="4000" /></el-form-item>
        <el-form-item label="所属章节"><el-select v-model="chapter" clearable :value-on-clear="''" placeholder="课程通用资料" style="width:100%" @change="changeChapter"><el-option v-for="c in outline?.chapters" :key="c.id" :value="c.id" :label="c.title" /></el-select></el-form-item>
        <el-form-item label="关联知识点"><el-select v-model="points" multiple filterable style="width:100%" placeholder="可选择多个知识点"><el-option v-for="p in knowledgePoints" :key="p.id" :value="p.id" :label="p.name" /></el-select></el-form-item>
        <el-form-item v-if="!editing" label="文件"><input ref="fileInput" type="file" accept=".pdf,.docx,.pptx,.md,.txt,.mp4,.webm" aria-label="选择教学资料文件" @change="pick" /></el-form-item>
      </el-form>
      <template #footer><el-button :disabled="busy" @click="dialog = false">取消</el-button><el-button type="primary" :loading="busy" @click="save">{{ editing ? '保存资料信息' : isVideo(chosen) ? '上传视频' : '上传并解析' }}</el-button></template>
    </el-dialog>
    <el-dialog :model-value="!!history" title="文件版本记录" width="min(680px, 94vw)" @close="history = undefined">
      <p>学生默认访问当前版本。切换为历史版本后，阅读与答疑一同使用该版本。</p>
      <article v-for="v in versions" :key="v.id" class="knowledge-card"><strong>版本 {{ v.version }} · {{ v.filename }}</strong><p>{{ statusLabel(v.status) }} · {{ new Date(v.created_at).toLocaleString() }}</p><p v-if="v.error">{{ v.error }}</p><div class="toolbar"><a v-if="history" :href="`/api/v1${key(history)}/file?version=${v.version}`">下载此版本</a><el-button v-if="v.status === 'ready' && v.version !== history?.version" :disabled="busy" @click="activate(v)">使用此版本</el-button><el-tag v-if="v.version === history?.version">当前版本</el-tag></div></article>
    </el-dialog>
  </section>
</template>
