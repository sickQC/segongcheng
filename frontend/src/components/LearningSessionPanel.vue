<script setup lang="ts">
import { computed, onUnmounted, ref, watch } from 'vue'
import { api, errorMessage } from '../api/client'
import { session } from '../composables/useSession'
type Stage = 'engage' | 'explore' | 'explain' | 'elaborate' | 'evaluate'
type Turn = { id: string; answer: string; status: string; stage_before: Stage; stage_after: Stage | null; error_message: string | null; event_id: string; output: { reply: string; quality: number; transition_reason: string; completed: boolean; evaluation_correct: boolean | null } | null }
type Session = { id: string; knowledge_point_name: string; stage: Stage; status: string; pending_turn_id: string | null; task: string; evaluation: { stem: string; options: Record<string, string> } | null; turns: Turn[] }
const props = defineProps<{ courseId: string }>()
const labels: Record<Stage, string> = { engage: '引入', explore: '探究', explain: '解释', elaborate: '迁移', evaluate: '评价' }
const stages = Object.keys(labels) as Stage[]
const points = ref<{ knowledge_point_id: string; name: string }[]>([]), selected = ref('')
const current = ref<Session>(), answer = ref(''), choice = ref(''), busy = ref(false), error = ref('')
const histories = ref<{ id: string; knowledge_point_name: string; stage: Stage; status: string }[]>([])
const student = computed(() => session.user?.role === 'student')
const storageKey = computed(() => `se:5e:${session.user?.id}:${props.courseId}`)
let timer: ReturnType<typeof setTimeout> | undefined
let generation = 0, pendingKey: { answer: string; choice: string; id: string } | undefined
let startRequest = crypto.randomUUID()

async function refresh(id = current.value?.id) {
  if (!id) return
  const run = generation
  clearTimeout(timer)
  try {
    const value = await api<Session>(`/learning-sessions/${encodeURIComponent(id)}`)
    if (run !== generation) return
    current.value = value
    if (value.pending_turn_id) timer = setTimeout(() => void refresh(id), 1500)
  } catch (e) { if (run === generation) error.value = errorMessage(e) }
}
async function load() {
  const run = ++generation
  clearTimeout(timer); current.value = undefined; error.value = ''; answer.value = ''; choice.value = ''
  busy.value = false; pendingKey = undefined; points.value = []; histories.value = []
  try {
    const list = await api<typeof points.value>(`/courses/${encodeURIComponent(props.courseId)}/learning-templates`)
    if (run !== generation) return
    points.value = list; selected.value = list[0]?.knowledge_point_id ?? ''
    const history = await api<typeof histories.value>(`/courses/${encodeURIComponent(props.courseId)}/learning-sessions`)
    if (run !== generation) return
    histories.value = history
    const saved = localStorage.getItem(storageKey.value)
    if (saved && student.value) await refresh(saved)
  } catch (e) { if (run === generation) error.value = errorMessage(e) }
}
async function start() {
  if (!selected.value || busy.value) return
  busy.value = true; error.value = ''
  const run = generation
  try {
    const value = await api<Session>('/learning-sessions', { method: 'POST', body: { course_id: props.courseId, knowledge_point_id: selected.value, request_id: startRequest } })
    if (run !== generation) return
    current.value = value; localStorage.setItem(storageKey.value, value.id)
    startRequest = crypto.randomUUID(); pendingKey = undefined; answer.value = ''; choice.value = ''
    histories.value = await api<typeof histories.value>(`/courses/${encodeURIComponent(props.courseId)}/learning-sessions`)
  } catch (e) { if (run === generation) error.value = errorMessage(e) }
  finally { if (run === generation) busy.value = false }
}
async function submit() {
  if (!current.value || !answer.value.trim() || busy.value || current.value.pending_turn_id) return
  const text = answer.value.trim(), run = generation
  if (pendingKey?.answer !== text || pendingKey?.choice !== choice.value) pendingKey = { answer: text, choice: choice.value, id: crypto.randomUUID() }
  busy.value = true; error.value = ''
  try {
    await api(`/learning-sessions/${encodeURIComponent(current.value.id)}/turns`, { method: 'POST', body: { answer: text, request_id: pendingKey.id, evaluation_choice: current.value.stage === 'evaluate' ? choice.value || null : null } })
    if (run !== generation) return
    pendingKey = undefined; answer.value = ''; choice.value = ''; await refresh()
  } catch (e) { if (run === generation) error.value = errorMessage(e) }
  finally { if (run === generation) busy.value = false }
}
async function resume(id: string) { clearTimeout(timer); ++generation; answer.value = ''; choice.value = ''; localStorage.setItem(storageKey.value, id); await refresh(id) }
watch(selected, () => { startRequest = crypto.randomUUID() })
watch(() => props.courseId, () => void load(), { immediate: true })
onUnmounted(() => { ++generation; clearTimeout(timer) })
</script>

<template>
  <section aria-label="5E 学习会话">
    <p>从场景引入、探究比较到解释、迁移和评价；阶段由本轮回答质量决定，答案和反馈均会保存。</p>
    <el-alert v-if="error" :title="error" type="error" :closable="false" />
    <template v-if="student">
      <el-select v-model="selected" aria-label="5E 知识点" :disabled="busy"><el-option v-for="point in points" :key="point.knowledge_point_id" :value="point.knowledge_point_id" :label="point.name" /></el-select>
      <el-button :disabled="!selected || !!current?.pending_turn_id" :loading="busy" @click="start">开始新会话</el-button>
      <div v-if="histories.length" class="practice-actions"><el-select placeholder="恢复历史会话" aria-label="恢复5E会话" @change="resume(String($event))"><el-option v-for="item in histories" :key="item.id" :value="item.id" :label="`${item.knowledge_point_name} · ${labels[item.stage]} · ${item.status === 'completed' ? '已完成' : '进行中'}`" /></el-select></div>
    </template>
    <p v-else class="muted">请使用学生账号开始学习会话。</p>
    <template v-if="current">
      <h3>{{ current.knowledge_point_name }}</h3>
      <div class="practice-actions"><el-tag v-for="stage in stages" :key="stage" :type="stage === current.stage ? 'success' : 'info'">{{ labels[stage] }}</el-tag></div>
      <p><strong>当前任务：</strong>{{ current.task }}</p>
      <article v-for="turn in current.turns" :key="turn.id" class="practice-result">
        <strong>{{ labels[turn.stage_before] }} · 我的作答</strong><p>{{ turn.answer }}</p>
        <template v-if="turn.output"><p>{{ turn.output.reply }}</p><p class="muted">回答质量 {{ Math.round(turn.output.quality * 100) }}% · {{ turn.output.transition_reason }}</p><p v-if="turn.output.evaluation_correct !== null">小测：{{ turn.output.evaluation_correct ? '正确' : '仍需巩固' }}</p></template>
        <p v-else>{{ turn.status === 'pending' ? '正在生成反馈…' : turn.error_message }}</p>
      </article>
      <el-alert v-if="current.status === 'completed'" title="本次五阶段学习会话已完成" type="success" :closable="false" />
      <template v-else-if="student">
        <div v-if="current.evaluation" class="practice-result"><strong>{{ current.evaluation.stem }}</strong><el-radio-group v-model="choice" aria-label="评价小测选项"><el-radio v-for="(text, key) in current.evaluation.options" :key="key" :value="key">{{ key }}. {{ text }}</el-radio></el-radio-group></div>
        <el-input v-model="answer" type="textarea" :rows="3" maxlength="4000" aria-label="5E本轮作答" placeholder="说明你的思考；评价阶段还需解释小测依据" :disabled="!!current.pending_turn_id" />
        <div class="practice-actions"><el-button type="primary" :loading="busy || !!current.pending_turn_id" :disabled="!answer.trim() || (current.stage === 'evaluate' && !choice)" @click="submit">提交本轮思考</el-button><el-button @click="refresh()">刷新会话</el-button></div>
        <p class="muted">失败轮次保留原答案；可重新提交。模型评价用于学习反馈，不是正式成绩。</p>
      </template>
    </template>
  </section>
</template>
