<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import WorkspaceHeader from '../components/WorkspaceHeader.vue'
import { useWorkspace } from '../composables/useWorkspace'
import { workspaceApi } from '../api/workspace'
import * as sample from '../api/preview'
import { errorMessage } from '../api/client'
import type { Resource, ChatReply, Citation } from '../types/workspace'
const { courseId, preview, loading, error, run } = useWorkspace(), route = useRoute()
const resources = ref<Resource[]>([]), selected = ref(''), mode = ref<'rag' | '5e'>('rag'), message = ref(''), busy = ref(false), chatError = ref('')
const turns = ref<{ role: string; reply: ChatReply }[]>([]), media = ref<HTMLVideoElement>(), page = ref(1)
const resource = computed(() => resources.value.find(r => r.id === selected.value))
function safeUrl(url: string | null | undefined) { if (!url) return ''; try { const u = new URL(url, location.origin); return ['http:', 'https:'].includes(u.protocol) ? u.href : '' } catch { return '' } }
const url = computed(() => safeUrl(resource.value?.url))
function load() { resources.value = []; selected.value = ''; turns.value = []; message.value = ''; chatError.value = ''; void run(() => preview.value ? Promise.resolve(sample.resources) : workspaceApi.resources(courseId.value), data => { resources.value = data; selected.value = data.find(r => r.id === route.query.resource)?.id ?? data[0]?.id ?? '' }) }
watch(preview, load, { immediate: true })
watch(mode, () => { turns.value = []; chatError.value = '' })
function cite(c: Citation) { selected.value = c.resource_id; page.value = c.page ?? 1; setTimeout(() => { if (media.value && c.seconds !== null) media.value.currentTime = c.seconds }, 0) }
async function send() {
 if (!message.value.trim() || !resource.value || busy.value) return
 const content = message.value.trim(); busy.value = true; chatError.value = ''
 turns.value.push({ role: '我', reply: { message: content, citations: [], phase: null } }); message.value = ''
 try { const reply = preview.value ? { message: '这是界面样例回复。真实检索、流式输出和 5E 阶段推进尚未接入。请尝试解释功能需求与质量要求的区别。', citations: [{ resource_id: 'preview-doc', title: '需求规格说明（样例）', page: 2, seconds: null }], phase: mode.value === '5e' ? 'engage · 引入（示例）' : null } : await workspaceApi.chat(courseId.value, { resource_id: selected.value, message: content, mode: mode.value }); turns.value.push({ role: '学习助手', reply }) }
 catch (e) { chatError.value = errorMessage(e); message.value = content }
 finally { busy.value = false }
}
</script>
<template><WorkspaceHeader :course-id="courseId" title="资源学习" v-model:preview="preview" :loading="loading || busy" :error="error" @reload="load" />
<div v-loading="loading" class="learning-grid">
 <section class="panel"><h2>课程资源</h2><el-empty v-if="!resources.length" description="暂无可用资源" /><el-select v-else v-model="selected" aria-label="选择学习资源" :disabled="busy" style="width:100%"><el-option v-for="r in resources" :key="r.id" :value="r.id" :label="r.title" /></el-select>
 <template v-if="resource"><h3>{{ resource.title }}</h3><p>{{ resource.description }}</p><video v-if="resource.type === 'video' && url" :key="url" ref="media" :src="url" controls preload="metadata" class="resource-video" /><iframe v-else-if="url" :key="url + page" :src="url + '#page=' + page" title="课程文档预览" sandbox="allow-same-origin" class="resource-document" /><el-empty v-else :description="preview ? '媒体预览区域 · 未加载样例文件' : '资源尚未生成预览地址'" />
 <div class="toolbar"><el-input-number v-if="resource.type === 'doc'" v-model="page" :min="1" aria-label="文档页码" /><a v-if="url" :href="url" target="_blank" rel="noopener noreferrer">打开原始资源</a></div><p class="muted">学习进度保存与行为采集待后端接入。</p></template></section>
 <section class="panel"><h2>学习助手</h2><el-radio-group v-model="mode" :disabled="busy"><el-radio-button value="rag">课程答疑</el-radio-button><el-radio-button value="5e">5E 引导</el-radio-button></el-radio-group><p class="muted">结合当前资源提问，回答引用可定位到页码或视频时间。</p><div class="chat-log" aria-live="polite"><el-empty v-if="!turns.length" description="选择资源后开始提问" :image-size="60" /><article v-for="(turn, i) in turns" :key="i" class="chat-turn"><strong>{{ turn.role }}</strong><el-tag v-if="turn.reply.phase">{{ turn.reply.phase }}</el-tag><p>{{ turn.reply.message }}</p><el-button v-for="(c, j) in turn.reply.citations" :key="j" text type="primary" @click="cite(c)">{{ c.title }} · {{ c.page !== null ? `第 ${c.page} 页` : `${c.seconds} 秒` }}</el-button></article></div><el-alert v-if="chatError" :title="chatError" type="error" :closable="false" /><el-input v-model="message" type="textarea" :rows="3" maxlength="2000" placeholder="输入你的问题" aria-label="提问内容" /><el-button type="primary" :loading="busy" :disabled="!resource || !message.trim()" @click="send">发送问题</el-button></section>
</div></template>
