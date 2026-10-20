<script setup lang="ts">
import { onUnmounted, ref, watch } from 'vue'
import { api, errorMessage } from '../api/client'
const props = defineProps<{ courseId: string }>()
type Journey = { id: string; knowledge_point_name: string; status: string; stage: string; updated_at: string; source: { question: string; type: string } | null }
const rows = ref<Journey[]>([]), error = ref('')
const labels: Record<string, string> = { engage: '引入', explore: '探究', explain: '解释', elaborate: '迁移', evaluate: '评价' }
let generation = 0
watch(() => props.courseId, async () => {
  const run = ++generation; rows.value = []; error.value = ''
  try { const value = await api<Journey[]>(`/courses/${encodeURIComponent(props.courseId)}/learning-sessions`); if (run === generation) rows.value = value.slice(0, 6) }
  catch (e) { if (run === generation) error.value = errorMessage(e) }
}, { immediate: true })
onUnmounted(() => ++generation)
</script>
<template><section class="panel" aria-label="错题巩固与5E学习记录"><h2>错题巩固与 5E 学习记录</h2><p class="muted">查看学习进度；每轮新作答可作为下方综合诊断的学习证据。</p><el-alert v-if="error" :title="error" type="error" :closable="false" /><p v-if="!rows.length">完成测验或小练习后，可从诊断进入针对性学习。</p><article v-for="row in rows" :key="row.id" class="practice-result"><strong>{{ row.knowledge_point_name }}</strong><p v-if="row.source">来源：{{ row.source.type === 'assessment' ? '测验错题' : '小练习' }} · {{ row.source.question }}</p><p v-else>从知识点自主开始</p><p>{{ row.status === 'completed' ? '五阶段已完成，评价小测与解释通过' : `学习进行中 · ${labels[row.stage]}` }} · {{ new Date(row.updated_at).toLocaleString() }}</p><RouterLink :to="{ path: `/courses/${courseId}/learn`, query: { mode: '5e', session: row.id } }">{{ row.status === 'completed' ? '回顾学习过程' : '继续学习' }}</RouterLink></article></section></template>
