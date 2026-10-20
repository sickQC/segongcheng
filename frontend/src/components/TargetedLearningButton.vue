<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { api, errorMessage } from '../api/client'
const props = defineProps<{ courseId: string; knowledgePointId: string; eventId: string }>()
const router = useRouter(), busy = ref(false), error = ref('')
const requestId = crypto.randomUUID()
async function start() {
  if (busy.value) return
  busy.value = true; error.value = ''
  try {
    const value = await api<{ id: string }>('/learning-sessions', { method: 'POST', body: {
      course_id: props.courseId, knowledge_point_id: props.knowledgePointId,
      source_event_id: props.eventId, request_id: requestId,
    } })
    await router.push({ path: `/courses/${props.courseId}/learn`, query: { mode: '5e', session: value.id } })
  } catch (e) { error.value = errorMessage(e) }
  finally { busy.value = false }
}
</script>
<template><div class="practice-actions"><el-button type="primary" plain :loading="busy" @click="start">针对这道题学习（5E）</el-button><span v-if="error" role="alert">{{ error }}</span></div></template>
