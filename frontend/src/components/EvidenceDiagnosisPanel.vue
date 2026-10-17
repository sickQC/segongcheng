<script setup lang="ts">
import { onUnmounted, ref, watch } from 'vue'
import { api, errorMessage } from '../api/client'
import { session } from '../composables/useSession'

type Event = { event_id: string; source: string; timestamp: string; answer?: string }
type Point = { knowledge_point_id: string; name: string; events: Event[]; baseline: { graded_count: number; accuracy: number | null; behavior_available: boolean } }
type Diagnosis = { knowledge_point_id: string; status: string; mastery: number | null; problem_type: string; explanation: string; recommendation: string; followup_question: string; evidence_event_ids: string[] }
type Report = { id: string; status: string; snapshot: { cutoff: string; points: Point[] }; output: { points: Diagnosis[]; excluded_instruction_events: string[]; guardrail_actions?: unknown[]; observed_behaviors?: { knowledge_point_id: string; problem_type: string }[] } | null; error_message: string | null; trace_id: string; created_at: string }
const props = defineProps<{ courseId: string }>()
const points = ref<{ id: string; name: string }[]>([]), selected = ref<string[]>([])
const reports = ref<Report[]>([]), current = ref<Report>(), busy = ref(false), error = ref('')
const labels: Record<string, string> = { concept_confusion: '概念混淆', prerequisite_gap: '前置知识可能不足', repeated_error: '反复错误', low_engagement: '有效学习记录偏少', practice_only: '答题与资源学习失衡', no_obvious_issue: '未发现明显问题', insufficient_evidence: '证据不足' }
let timer: ReturnType<typeof setTimeout> | undefined, generation = 0
let pendingRequest: { signature: string; id: string } | undefined
const base = () => `/courses/${encodeURIComponent(props.courseId)}/diagnosis-reports`
async function refresh(id = current.value?.id) {
  if (!id) return
  const run = generation
  clearTimeout(timer)
  try {
    const value = await api<Report>(`${base()}/${encodeURIComponent(id)}`)
    if (run !== generation) return
    current.value = value
    reports.value = reports.value.map(row => row.id === value.id ? value : row)
    if (value.status === 'pending') timer = setTimeout(() => void refresh(id), 1500)
  } catch (e) { if (run === generation) error.value = errorMessage(e) }
}
async function load() {
  const run = ++generation
  clearTimeout(timer); current.value = undefined; reports.value = []; selected.value = []; points.value = []; error.value = ''; busy.value = false; pendingRequest = undefined
  try {
    const outline = await api<{ chapters: { knowledge_points: { id: string; name: string }[] }[] }>(`/courses/${encodeURIComponent(props.courseId)}/outline`)
    if (run !== generation) return
    points.value = outline.chapters.flatMap(ch => ch.knowledge_points)
    selected.value = points.value.slice(0, 20).map(p => p.id)
    const history = await api<Report[]>(base())
    if (run !== generation) return
    reports.value = history
    if (history[0]) await refresh(history[0].id)
  } catch (e) { if (run === generation) error.value = errorMessage(e) }
}
async function analyze() {
  if (busy.value || !selected.value.length) return
  const run = generation, signature = [...selected.value].sort().join(',')
  if (pendingRequest?.signature !== signature) pendingRequest = { signature, id: crypto.randomUUID() }
  busy.value = true; error.value = ''
  try {
    const value = await api<Report>(base(), { method: 'POST', body: { knowledge_point_ids: [...selected.value].sort(), days: 30, request_id: pendingRequest.id } })
    if (run !== generation) return
    pendingRequest = undefined; current.value = value; reports.value = [value, ...reports.value.filter(r => r.id !== value.id)].slice(0, 20); await refresh(value.id)
  } catch (e) { if (run === generation) error.value = errorMessage(e) }
  finally { if (run === generation) busy.value = false }
}
async function retry() {
  if (!current.value || busy.value) return
  const id = current.value.id, run = generation
  busy.value = true; error.value = ''
  try { await api(`${base()}/${encodeURIComponent(id)}/retry`, { method: 'POST' }); if (run === generation) await refresh(id) }
  catch (e) { if (run === generation) error.value = errorMessage(e) }
  finally { if (run === generation) busy.value = false }
}
async function open(id: string) { ++generation; clearTimeout(timer); busy.value = false; await refresh(id) }
watch(() => props.courseId, () => void load(), { immediate: true })
onUnmounted(() => { ++generation; clearTimeout(timer) })
</script>
<template>
  <section class="panel" aria-label="综合学习诊断">
    <h2>综合学习诊断</h2>
    <p class="muted">汇总最近 30 天的实际答题、练习和学习对话。模型判断与客观正确率分别展示，不修改成绩或模拟画像。</p>
    <el-alert v-if="error" :title="error" type="error" :closable="false" />
    <div v-if="session.user?.role === 'student'" class="practice-actions">
      <el-select v-model="selected" multiple :multiple-limit="20" collapse-tags aria-label="综合诊断知识点" :disabled="busy || current?.status === 'pending'"><el-option v-for="point in points" :key="point.id" :value="point.id" :label="point.name" /></el-select>
      <el-button type="primary" :loading="busy || current?.status === 'pending'" :disabled="!selected.length" @click="analyze">分析最近学习记录</el-button>
    </div>
    <el-select v-if="reports.length" placeholder="查看诊断历史" aria-label="综合诊断历史" @change="open(String($event))"><el-option v-for="row in reports" :key="row.id" :value="row.id" :label="`${new Date(row.created_at).toLocaleString()} · ${row.status}`" /></el-select>
    <template v-if="current">
      <p class="muted">证据截止：{{ new Date(current.snapshot.cutoff).toLocaleString() }} · Trace：{{ current.trace_id }}</p>
      <el-alert v-if="current.status === 'pending'" title="正在分析，证据快照已保存…" type="info" :closable="false" />
      <el-alert v-if="current.output?.guardrail_actions?.length" title="部分判断已根据学习记录修正，请核对引用证据。" type="warning" :closable="false" />
      <template v-else-if="current.status === 'failed'"><el-alert :title="current.error_message ?? '诊断失败'" type="error" :closable="false" /><el-button :loading="busy" @click="retry">重试综合诊断</el-button></template>
      <article v-for="point in current.snapshot.points" :key="point.knowledge_point_id" class="knowledge-card">
        <h3>{{ point.name }}</h3>
        <p>客观正确率：{{ point.baseline.accuracy === null ? '暂无客观作答' : `${Math.round(point.baseline.accuracy * 100)}%（${point.baseline.graded_count} 题）` }} · 行为数据：{{ point.baseline.behavior_available ? '已有服务端测量' : '未采集' }}</p>
        <p v-for="observation in current.output?.observed_behaviors?.filter(o => o.knowledge_point_id === point.knowledge_point_id) ?? []" :key="observation.problem_type">记录支持的行为观察：{{ labels[observation.problem_type] }}。此项不代表知识掌握度。</p>
        <template v-for="item in current.output?.points.filter(p => p.knowledge_point_id === point.knowledge_point_id) ?? []" :key="item.knowledge_point_id">
          <el-tag :type="item.status === 'insufficient' ? 'info' : 'warning'">{{ labels[item.problem_type] }}</el-tag>
          <p>模型暂估掌握度：{{ item.mastery === null ? '未知' : `${Math.round(item.mastery * 100)}%` }}</p>
          <p>{{ item.explanation }}</p><p>建议：{{ item.recommendation }}</p><p>思考追问：{{ item.followup_question }}</p>
          <p class="muted">引用事件：{{ item.evidence_event_ids.join('、') || '无可用证据' }}</p>
        </template>
        <details><summary>核对本次证据（{{ point.events.length }} 条）</summary><p v-for="event in point.events" :key="event.event_id">{{ event.source }} · {{ event.timestamp }}<br />{{ event.answer ?? '服务端行为测量' }}<br /><span class="muted">{{ event.event_id }}</span></p></details>
      </article>
    </template>
    <p v-else class="muted">先完成练习或测验，再生成综合诊断。</p>
  </section>
</template>
