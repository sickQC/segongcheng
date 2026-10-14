<script setup lang="ts">
import { ref, watch } from 'vue'
import WorkspaceHeader from '../components/WorkspaceHeader.vue'
import ReportPanels from '../components/ReportPanels.vue'
import { useWorkspace } from '../composables/useWorkspace'
import { workspaceApi } from '../api/workspace'
import * as sample from '../api/preview'
import { errorMessage } from '../api/client'
import type { Report } from '../types/workspace'
const { courseId, preview, loading, error, run } = useWorkspace(), report = ref<Report>(), algorithm = ref('baseline'), message = ref(''), reply = ref(''), busy = ref(false)
function load() { report.value = undefined; message.value = ''; reply.value = ''; void run(() => preview.value ? Promise.resolve(sample.report) : workspaceApi.report(courseId.value, algorithm.value), data => report.value = data) }
watch([preview, algorithm], load, { immediate: true })
async function followup() { if (!message.value.trim()) return; busy.value = true; try { reply.value = preview.value ? '此处展示诊断追问回复。样例模式不更新诊断或画像。' : (await workspaceApi.followup(courseId.value, message.value)).message } catch (e) { reply.value = errorMessage(e) } finally { busy.value = false } }
</script>
<template><WorkspaceHeader :course-id="courseId" title="个人学习报告" v-model:preview="preview" :loading="loading || busy" :error="error" @reload="load" /><section v-loading="loading" class="panel"><div class="toolbar"><h2>学习反馈</h2><el-select v-model="algorithm" :disabled="busy" aria-label="推荐算法" style="width:220px"><el-option label="基础推荐" value="baseline" /><el-option label="增强推荐（E7）" value="enhanced" /></el-select></div><p v-if="preview" class="muted">两种算法共用布局样例，尚未运行推荐算法或对比评测。</p><ReportPanels v-if="report" :report="report"><template #resource="{ item }"><RouterLink v-if="item.resource_id" :to="{ path: `/courses/${courseId}/learn`, query: { resource: item.resource_id } }"><el-button text>前往学习</el-button></RouterLink></template></ReportPanels><el-empty v-else description="暂无可展示的学习报告" /></section><section class="panel followup-panel"><h2>诊断追问</h2><p class="muted">描述你的理解或困难，后续由诊断服务结合证据处理。</p><el-input v-model="message" type="textarea" :rows="3" maxlength="2000" aria-label="诊断追问" /><el-button type="primary" :loading="busy" :disabled="!report || !message.trim()" @click="followup">提交追问</el-button><p aria-live="polite">{{ reply }}</p></section></template>
