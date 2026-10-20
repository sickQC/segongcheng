<script setup lang="ts">
import { onUnmounted, ref, watch } from 'vue'
import { api, errorMessage } from '../api/client'
import { recommendationApi } from '../api/recommendation'
import type { LearningPath, PathFeedback, RecommendationMetrics } from '../types/recommendation'

const props = defineProps<{ courseId: string }>()
const points = ref<{ id: string; name: string; code: string }[]>([]), target = ref('')
const history = ref<LearningPath[]>([]), current = ref<LearningPath>(), busy = ref(false), error = ref('')
const strategy = ref<'baseline' | 'budgeted'>('baseline'), budget = ref<number | undefined>(30)
const feedback = ref<PathFeedback | null>(null), feedbackBusy = ref(false)
const metrics = ref<RecommendationMetrics>(), metricsBusy = ref(false)
let version = 0, feedbackVersion = 0, pending: { signature: string; request: string } | undefined
const strategyLabel = (value: string) => value === 'budgeted' ? 'E7 时间预算' : '基础顺序'
const time = (value: string) => new Date(value).toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai' })
async function load() {
 const generation = ++version; points.value = []; history.value = []; current.value = undefined
 target.value = ''; pending = undefined; busy.value = true; error.value = ''; feedback.value = null; feedbackBusy.value = false; metrics.value = undefined; metricsBusy.value = false
 try {
  const [outline, saved] = await Promise.all([api<{ chapters: { knowledge_points: { id: string; name: string; code: string }[] }[] }>(`/courses/${encodeURIComponent(props.courseId)}/outline`), recommendationApi.history(props.courseId)])
  if (generation !== version) return
  points.value = outline.chapters.flatMap(ch => ch.knowledge_points); history.value = saved
  current.value = saved[0]; target.value = points.value.find(p => p.id === saved[0]?.target_kp_id)?.id ?? points.value[0]?.id ?? ''
  if (saved[0]) await loadFeedback(saved[0].id)
 } catch (e) { if (generation === version) error.value = errorMessage(e) }
 finally { if (generation === version) busy.value = false }
}
async function generate() {
 if (busy.value || feedbackBusy.value || !target.value || budget.value == null) return
 const generation = version
 const signature = JSON.stringify([target.value, strategy.value, budget.value])
 if (pending?.signature !== signature) pending = { signature, request: crypto.randomUUID() }
 busy.value = true; error.value = ''
 try {
  const value = await recommendationApi.create(props.courseId, target.value, pending.request, strategy.value, budget.value)
  if (generation !== version) return
  pending = undefined; current.value = value; history.value = [value, ...history.value.filter(p => p.id !== value.id)].slice(0, 20)
  await loadFeedback(value.id)
  if (metrics.value) await loadMetrics()
 } catch (e) { if (generation === version) error.value = errorMessage(e) }
 finally { if (generation === version) busy.value = false }
}
async function loadFeedback(id: string) {
 const generation = version, request = ++feedbackVersion
 feedback.value = null; feedbackBusy.value = true
 try { const value = await recommendationApi.feedback(props.courseId, id); if (generation === version && request === feedbackVersion && current.value?.id === id) feedback.value = value }
 catch (e) { if (generation === version && request === feedbackVersion) error.value = errorMessage(e) }
 finally { if (generation === version && request === feedbackVersion) feedbackBusy.value = false }
}
async function saveFeedback(choice: 'accepted' | 'declined') {
 if (!current.value || feedbackBusy.value || feedback.value) return
 const generation = version, id = current.value.id
 feedbackBusy.value = true; error.value = ''
 try { const value = await recommendationApi.saveFeedback(props.courseId, id, choice); if (generation === version && current.value?.id === id) { feedback.value = value; if (metrics.value) await loadMetrics() } }
 catch (e) { if (generation === version) error.value = errorMessage(e) }
 finally { if (generation === version) feedbackBusy.value = false }
}
async function loadMetrics() {
 const generation = version; metricsBusy.value = true
 try { const value = await recommendationApi.metrics(props.courseId); if (generation === version) metrics.value = value }
 catch (e) { if (generation === version) error.value = errorMessage(e) }
 finally { if (generation === version) metricsBusy.value = false }
}
function open(id: unknown) { current.value = history.value.find(p => p.id === String(id)); if (current.value) void loadFeedback(current.value.id) }
watch(() => props.courseId, () => void load(), { immediate: true })
onUnmounted(() => { version++ })
</script>

<template>
 <section class="panel" aria-label="先修路径与时间预算推荐" v-loading="busy">
  <h2>先修路径与时间预算推荐</h2>
  <p>基础策略按先修顺序安排预算内的前缀；E7 在先修满足且放得下的步骤中，综合薄弱程度、目标距离和估时选择下一步。两者都列出未安排的步骤。</p>
  <el-alert v-if="error" :title="error" type="error" :closable="false" />
  <div class="toolbar"><el-select v-model="target" filterable aria-label="推荐目标知识点" style="width: min(360px, 100%)" :disabled="busy || feedbackBusy"><el-option v-for="p in points" :key="p.id" :value="p.id" :label="`${p.code} ${p.name}`" /></el-select><el-select v-model="strategy" aria-label="推荐策略" :disabled="busy || feedbackBusy" style="width:190px"><el-option label="基础顺序" value="baseline" /><el-option label="E7 时间预算" value="budgeted" /></el-select><label>本次预算（分钟） <el-input-number v-model="budget" :min="1" :max="240" :precision="0" aria-label="本次时间预算" :disabled="busy || feedbackBusy" /></label><el-button type="primary" :disabled="!target || budget == null || busy || feedbackBusy" @click="generate">生成学习路径</el-button></div>
  <el-select v-if="history.length" :model-value="current?.id" @change="open" aria-label="推荐历史" :disabled="busy || feedbackBusy" style="width:min(600px, 100%)"><el-option v-for="p in history" :key="p.id" :value="p.id" :label="`${time(p.created_at)} · ${strategyLabel(p.strategy)} · ${p.time_budget_minutes ?? '不限'}分钟 · ${p.target_name}`" /></el-select>
  <template v-if="current">
   <h3>目标：{{ current.target_name }}</h3>
   <el-alert v-if="!current.scheduling_rule" title="这是一份旧版历史路径，未记录预算和估时；请重新生成以使用当前策略。" type="info" :closable="false" />
   <p class="muted">{{ strategyLabel(current.strategy) }} · 生成于 {{ time(current.created_at) }} · 掌握阈值 {{ Math.round(current.mastery_threshold * 100) }}% · 本次 {{ current.steps.length }} 步</p>
   <p v-if="current.estimated_minutes != null">本次预计 {{ current.estimated_minutes }} 分钟 / 预算 {{ current.time_budget_minutes ?? '不限' }} 分钟 · 完整路径估时 {{ current.full_path_estimated_minutes }} 分钟。估时不是实际耗时。</p>
   <el-alert v-if="current.goal_in_plan === false" title="本次预算内尚未安排到目标；请按步骤学习，之后继续剩余路径。" type="info" :closable="false" />
   <el-alert v-if="current.status === 'target_mastered'" title="目标已达到掌握阈值，本次无需安排新路径。" type="success" :closable="false" />
   <article v-for="step in current.steps" :key="step.knowledge_point_id" class="knowledge-card">
    <h3>{{ step.order }}. {{ step.name }}</h3><p>{{ step.reason }}</p>
    <p v-if="step.estimated_minutes != null">预计 {{ step.estimated_minutes }} 分钟（{{ step.estimate_source === 'teacher' ? '教师估时' : '规则估时，非实测' }}）</p>
    <p class="muted">依据：{{ step.reason_source === 'diagnosis' ? '有效综合诊断' : '先修规则，尚待测评' }} · 置信度 {{ step.confidence === null ? '未知' : `${Math.round(step.confidence * 100)}%` }}</p>
    <details v-if="step.diagnosis_id"><summary>核对诊断来源</summary><p>综合诊断 {{ step.diagnosis_id }} · 输入截止 {{ step.input_cutoff ? time(step.input_cutoff) : '未知' }}</p><p v-for="id in step.evidence_ids" :key="id">事件 {{ id }}</p></details>
    <div class="tag-row"><RouterLink v-for="action in step.actions" :key="`${action.kind}-${action.id}`" :to="action.url"><el-button text type="primary">{{ action.title }}</el-button></RouterLink></div>
    <p v-for="note in step.notes" :key="note" class="muted">{{ note }}</p>
   </article>
   <details v-if="current.remaining_steps?.length" open><summary>未安排 {{ current.remaining_steps.length }} 步 · 合计估时 {{ current.remaining_estimated_minutes }} 分钟</summary><article v-for="step in current.remaining_steps" :key="step.knowledge_point_id" class="knowledge-card"><h4>{{ step.name }} · 预计 {{ step.estimated_minutes }} 分钟</h4><p>{{ step.deferral_reason }}</p></article></details>
   <details v-if="current.skipped.length"><summary>已跳过 {{ current.skipped.length }} 个已掌握知识点</summary><article v-for="point in current.skipped" :key="point.knowledge_point_id" class="knowledge-card"><h4>{{ point.name }}</h4><p>{{ point.reason }}</p><p class="muted">综合诊断 {{ point.diagnosis_id }}</p></article></details>
   <p v-for="note in current.notes" :key="note" class="muted">{{ note }}</p>
   <h3>是否愿意采用这份计划？</h3><p class="muted">此反馈只记录你的意愿，不代表完成学习，也不更新掌握度。每份计划保留一次反馈，可对新计划再次反馈。</p>
   <p v-if="feedback">已反馈：{{ feedback.choice === 'accepted' ? '愿意采用' : '暂不采用' }}</p><div v-else class="tag-row"><el-button :loading="feedbackBusy" @click="saveFeedback('accepted')">愿意采用</el-button><el-button :disabled="feedbackBusy" @click="saveFeedback('declined')">暂不采用</el-button></div>
  </template>
  <el-empty v-else-if="!busy" description="选择目标后生成路径；尚无推荐历史。" />
  <el-button :loading="metricsBusy" @click="loadMetrics">查看两种策略使用统计</el-button>
  <template v-if="metrics"><p class="muted">{{ metrics.explanation }}</p><el-table :data="metrics.strategies"><el-table-column label="策略" min-width="110"><template #default="{ row }">{{ strategyLabel(row.strategy) }}</template></el-table-column><el-table-column prop="recommendation_count" label="推荐份数" /><el-table-column prop="feedback_count" label="反馈份数" /><el-table-column label="接受率"><template #default="{ row }">{{ row.acceptance_rate === null ? '暂无反馈' : `${Math.round(row.acceptance_rate * 100)}%` }}</template></el-table-column><el-table-column label="平均估时"><template #default="{ row }">{{ row.average_estimated_minutes === null ? '未知' : `${row.average_estimated_minutes}分钟` }}</template></el-table-column></el-table></template>
 </section>
</template>

<style scoped>
details p { overflow-wrap: anywhere; }
</style>
