<script setup lang="ts">
import { onUnmounted, ref, watch } from 'vue'
import { api, errorMessage } from '../api/client'
const props = defineProps<{ courseId: string; attemptId: string }>()
type Row = { id: string; question: string; original_answer: string; event_id: string; status: string; error_message: string | null; output: { problem_description: string; recommendation: string; followup_question: string } | null }
const rows = ref<Row[]>([]), error = ref(''), busy = ref(false)
let timer: ReturnType<typeof setTimeout> | undefined, generation = 0
const base = () => `/courses/${encodeURIComponent(props.courseId)}/attempts/${encodeURIComponent(props.attemptId)}/diagnoses`
async function load() {
  const run = generation; clearTimeout(timer)
  try { const value = await api<Row[]>(base()); if (run !== generation) return; rows.value = value; error.value = ''; if (value.some(row => row.status === 'pending')) timer = setTimeout(load, 1500) }
  catch (e) { if (run === generation) error.value = errorMessage(e) }
}
async function retry(row: Row) { if (busy.value) return; busy.value = true; try { await api(`${base()}/${encodeURIComponent(row.id)}/retry`, { method: 'POST' }); await load() } catch (e) { error.value = errorMessage(e) } finally { busy.value = false } }
watch(() => [props.courseId, props.attemptId], () => { ++generation; rows.value = []; void load() }, { immediate: true })
onUnmounted(() => { ++generation; clearTimeout(timer) })
</script>
<template><section aria-label="测验自动诊断"><h3>错题学习诊断</h3><el-alert v-if="error" :title="error" type="error" :closable="false" /><p v-if="!rows.length" class="muted">没有需要诊断的错题。</p><article v-for="row in rows" :key="row.id" class="practice-result"><strong>{{ row.question }}</strong><p>原答案：{{ row.original_answer || '未作答' }}</p><template v-if="row.output"><p>{{ row.output.problem_description }}</p><p>建议：{{ row.output.recommendation }}</p><p>思考追问：{{ row.output.followup_question }}</p></template><template v-else-if="row.status === 'failed'"><p>{{ row.error_message }}</p><el-button :loading="busy" @click="retry(row)">重试诊断</el-button></template><p v-else>正在诊断，原答案与分数已保存…</p><p class="muted">证据：{{ row.event_id }}</p></article><p class="muted">AI 解释用于学习反馈，不修改服务端判分结果。</p></section></template>
