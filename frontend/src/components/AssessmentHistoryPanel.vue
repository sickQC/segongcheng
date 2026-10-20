<script setup lang="ts">
import { ref, watch } from 'vue'
import { api, errorMessage } from '../api/client'
import type { Attempt, QuizResult } from '../types/workspace'
const props = defineProps<{ courseId: string; attemptId?: string }>()
const emit = defineEmits<{ open: [value: { attempt: Attempt; result: QuizResult | null }] }>()
const rows = ref<{ id: string; title: string; status: string }[]>([]), error = ref('')
let generation = 0
async function load() {
  const run = ++generation
  try { const value = await api<typeof rows.value>(`/courses/${encodeURIComponent(props.courseId)}/attempts/me`); if (run === generation) rows.value = value }
  catch (e) { if (run === generation) error.value = errorMessage(e) }
}
async function open(id: string) {
  const run = generation
  try { const value = await api<{ attempt: Attempt; result: QuizResult | null }>(`/courses/${encodeURIComponent(props.courseId)}/attempts/${encodeURIComponent(id)}`); if (run === generation) emit('open', value) }
  catch (e) { if (run === generation) error.value = errorMessage(e) }
}
watch(() => props.courseId, () => void load(), { immediate: true })
watch(() => [props.courseId, props.attemptId], () => { if (props.attemptId) void open(props.attemptId) }, { immediate: true })
</script>
<template><section v-if="rows.length || error" class="panel" aria-label="我的测验记录"><h3>我的测验记录</h3><el-alert v-if="error" :title="error" type="error" :closable="false" /><article v-for="row in rows" :key="row.id" class="practice-entry"><span>{{ row.title }} · {{ row.status === 'submitted' ? '已提交' : row.status === 'expired' ? '已过期' : '作答中' }}</span><el-button @click="open(row.id)">{{ row.status === 'submitted' ? '查看结果和诊断' : '查看答卷' }}</el-button></article></section></template>
