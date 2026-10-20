<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import EventExportPanel from './EventExportPanel.vue'
import { workspaceApi } from '../api/workspace'
import { errorMessage } from '../api/client'
import type { LearningProfile, LearningEvent } from '../types/workspace'

const props = defineProps<{ profile: LearningProfile; courseId: string }>()
const events = ref<LearningEvent[]>([]), selectedPoint = ref(''), busy = ref(false), error = ref('')
const loaded = ref(false), nextOffset = ref<number | null>(null)
let requestVersion = 0
const riskLabel = computed(() => ({ unknown: '证据不足，暂不判断', attention: '建议关注', normal: '当前规则未提示风险' }[props.profile.risk.level]))
function time(value: string | null) { return value ? new Date(value).toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai' }) : '未知' }
function percent(value: number | null) { return value === null ? '未知' : `${value}%` }
function resetEvents() { requestVersion++; events.value = []; loaded.value = false; nextOffset.value = null; error.value = ''; busy.value = false }
watch([() => props.courseId, () => props.profile.generated_at, selectedPoint], resetEvents)
async function loadEvents(more = false) {
 const version = ++requestVersion
 busy.value = true; error.value = ''
 const query = new URLSearchParams({ limit: '20', offset: String(more ? nextOffset.value ?? 0 : 0), start: props.profile.window_start, end: props.profile.window_end })
 if (selectedPoint.value) query.set('knowledge_point_id', selectedPoint.value)
 try {
  const page = await workspaceApi.events(props.courseId, query)
  if (version !== requestVersion) return
  events.value = more ? [...events.value, ...page.items] : page.items
  nextOffset.value = page.next_offset; loaded.value = true
 } catch (e) { if (version === requestVersion) error.value = errorMessage(e) }
 finally { if (version === requestVersion) busy.value = false }
}
</script>

<template>
 <section class="panel" aria-label="真实学习画像">
  <h2>真实学习画像</h2>
  <p class="muted">统计区间：{{ time(profile.window_start) }} 至 {{ time(profile.window_end) }}（北京时间） · 更新于 {{ time(profile.generated_at) }}</p>
  <el-alert title="画像仅使用你的真实课程记录。掌握度需要有效综合诊断；没有依据的指标显示未知。下方可按目标与预算生成基础或 E7 路径；推荐不代表已完成学习。" type="info" :closable="false" />
  <h3>知识掌握</h3>
  <p>{{ profile.knowledge.explanation }} 已有依据：{{ profile.knowledge.known_points }}/{{ profile.knowledge.total_points }} 个知识点。</p>
  <el-table :data="profile.knowledge.points" empty-text="课程尚无知识点">
   <el-table-column prop="name" label="知识点" min-width="150" />
   <el-table-column label="诊断掌握度" min-width="110"><template #default="{ row }">{{ percent(row.mastery_percent) }}</template></el-table-column>
   <el-table-column label="置信度" min-width="90"><template #default="{ row }">{{ percent(row.confidence_percent) }}</template></el-table-column>
   <el-table-column label="客观正确率" min-width="110"><template #default="{ row }">{{ percent(row.accuracy_percent) }}（{{ row.question_count }}题）</template></el-table-column>
   <el-table-column label="依据" min-width="170"><template #default="{ row }"><details v-if="row.report_id"><summary>查看来源与时间</summary><p>综合诊断 {{ row.report_id }}</p><p>输入截止 {{ time(row.input_cutoff) }}</p><p>掌握度更新 {{ time(row.updated_at) }}</p><p v-for="id in row.evidence_ids" :key="id">事件 {{ id }}</p></details><span v-else>尚无有效掌握度诊断</span></template></el-table-column>
  </el-table>
  <h3>学习投入</h3>
  <p>活跃 {{ profile.engagement.active_days }} 天 · {{ profile.engagement.event_count }} 条学习活动 · 已测资源 {{ profile.engagement.observed_resource_count }} 个</p>
  <p>已测资源累计时长：{{ profile.engagement.effective_seconds === null ? '未知' : `${Math.round(profile.engagement.effective_seconds / 60)} 分钟` }} · 已测资源完成比例：{{ percent(profile.engagement.completed_resource_percent) }}</p>
  <p class="muted">{{ profile.engagement.explanation }}</p>
  <h3>活动偏好</h3>
  <p v-for="item in profile.preference.items" :key="item.key">{{ item.label }}：{{ item.count === null ? '未采集' : `${item.count} 次` }} · 占比 {{ percent(item.percent) }}</p>
  <p class="muted">{{ profile.preference.explanation }}</p>
  <h3>学习风险：{{ riskLabel }}</h3>
  <p v-for="reason in profile.risk.reasons" :key="reason">{{ reason }}</p>
  <p class="muted">{{ profile.risk.explanation }}</p>
  <details v-if="profile.risk.evidence_ids.length"><summary>风险依据事件</summary><p v-for="id in profile.risk.evidence_ids" :key="id">{{ id }}</p></details>
  <h3>核对真实学习事件</h3>
  <div class="toolbar"><el-select v-model="selectedPoint" clearable placeholder="全部知识点" aria-label="事件知识点筛选" style="width:240px"><el-option v-for="point in profile.knowledge.points" :key="point.knowledge_point_id" :label="point.name" :value="point.knowledge_point_id" /></el-select><el-button :loading="busy" @click="loadEvents()">查询事件</el-button></div>
  <el-alert v-if="error" :title="error" type="error" :closable="false" />
  <el-empty v-if="loaded && !events.length" description="此范围暂无真实事件" />
  <article v-for="event in events" :key="event.event_id" class="knowledge-card"><p>{{ time(event.timestamp) }} · {{ event.verb }}</p><details><summary>查看事件 {{ event.event_id }}</summary><pre class="event-detail">{{ JSON.stringify({ object: event.object, result: event.result, context: event.context }, null, 2) }}</pre></details></article>
  <el-button v-if="nextOffset !== null" :loading="busy" @click="loadEvents(true)">加载更多</el-button>
  <EventExportPanel :course-id="courseId" :points="profile.knowledge.points" :initial-start="profile.window_start" :initial-end="profile.window_end" />
 </section>
</template>

<style scoped>
.event-detail { white-space: pre-wrap; overflow-wrap: anywhere; }
details p { overflow-wrap: anywhere; }
</style>
