<script setup lang="ts">
import { ref, watch } from 'vue'
import { errorMessage } from '../api/client'
import { profileHistoryApi } from '../api/profileHistory'
import type { ProfileSnapshot, SnapshotComparison, SnapshotSummary } from '../types/profileHistory'
const props = defineProps<{ courseId: string; refreshToken?: string }>()
const items = ref<SnapshotSummary[]>([]), next = ref<number | null>(null)
const loading = ref(false), saving = ref(false), checking = ref(false), error = ref('')
const before = ref(''), after = ref(''), selected = ref<ProfileSnapshot | null>(null), comparison = ref<SnapshotComparison | null>(null)
let generation = 0, detailVersion = 0, compareVersion = 0, requestId: string | null = null
const time = (value: string) => new Date(value).toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai' })
const label = (s: SnapshotSummary) => `${time(s.created_at)} · ${s.reason === 'diagnosis' ? '诊断后' : '手动'} · ${s.days}天`
const value = (n: number | null) => n === null ? '未知' : String(n)
const preferenceNames: Record<string, string> = { video: '视频', read: '阅读', ask: '问答与5E', practice: '练习与测验' }
const riskName = (level: string) => level === 'unknown' ? '未知' : level === 'attention' ? '需关注' : '未触发风险'
async function load(more = false) {
 const version = ++generation, course = props.courseId
 loading.value = true; error.value = ''
 try {
  const page = await profileHistoryApi.list(course, more ? next.value ?? 0 : 0)
  if (version !== generation || course !== props.courseId) return
  items.value = more ? [...items.value, ...page.items.filter(x => !items.value.some(old => old.id === x.id))] : page.items
  next.value = page.next_offset
  if (!more) { after.value = items.value[0]?.id ?? ''; before.value = items.value[1]?.id ?? ''; comparison.value = null }
 } catch (e) { if (version === generation) error.value = errorMessage(e) }
 finally { if (version === generation) loading.value = false }
}
async function save() {
 const course = props.courseId
 saving.value = true; error.value = ''; requestId ??= crypto.randomUUID()
 try {
  const result = await profileHistoryApi.save(course, requestId)
  if (course !== props.courseId) return
  requestId = null; selected.value = result; await load()
 } catch (e) { if (course === props.courseId) error.value = errorMessage(e) }
 finally { saving.value = false }
}
async function open(id: string) {
 const version = ++detailVersion, course = props.courseId
 error.value = ''
 try { const result = await profileHistoryApi.detail(course, id); if (version === detailVersion && course === props.courseId) selected.value = result }
 catch (e) { if (version === detailVersion) error.value = errorMessage(e) }
}
async function compare() {
 const version = ++compareVersion, course = props.courseId, a = before.value, b = after.value
 checking.value = true; error.value = ''; comparison.value = null
 try {
  const result = await profileHistoryApi.compare(course, a, b)
  if (version === compareVersion && course === props.courseId && a === before.value && b === after.value) comparison.value = result
 } catch (e) { if (version === compareVersion) error.value = errorMessage(e) }
 finally { if (version === compareVersion) checking.value = false }
}
watch(() => props.courseId, () => { requestId = null; selected.value = null; detailVersion++; compareVersion++; comparison.value = null }, { flush: 'sync' })
watch(() => [props.courseId, props.refreshToken], () => load(), { immediate: true })
watch([before, after], () => { comparison.value = null; compareVersion++; checking.value = false })
</script>
<template>
 <section class="panel">
  <h2>画像历史与对比</h2>
  <p class="muted">有效综合诊断更新掌握度后自动保存；也可手动保存近30天画像。只保存当前真实计算结果，不补造过去历史。</p>
  <el-button :loading="saving" @click="save">保存当前画像快照</el-button>
  <el-button :loading="loading" @click="load()">刷新历史</el-button>
  <el-alert v-if="error" :title="error" type="error" :closable="false" />
  <el-empty v-if="!items.length && !loading" description="暂无快照，可手动保存；既有诊断不会倒填历史" />
  <ul><li v-for="s in items" :key="s.id"><el-button text @click="open(s.id)">{{ label(s) }} · {{ s.rule_version }}</el-button></li></ul>
  <el-button v-if="next !== null" :loading="loading" @click="load(true)">加载更多</el-button>
  <template v-if="selected">
   <h3>已保存快照：{{ time(selected.created_at) }}</h3>
   <p>已知掌握度 {{ selected.profile.knowledge.known_points }}/{{ selected.profile.knowledge.total_points }} 个；有效活动 {{ selected.profile.engagement.event_count }} 次；风险 {{ selected.profile.risk.level === 'unknown' ? '未知' : selected.profile.risk.level === 'attention' ? '需关注' : '未触发风险' }}。</p>
   <el-table :data="selected.profile.knowledge.points"><el-table-column prop="name" label="知识点" /><el-table-column label="掌握度（%）"><template #default="{ row }">{{ value(row.mastery_percent) }}</template></el-table-column><el-table-column label="客观正确率（%）"><template #default="{ row }">{{ value(row.accuracy_percent) }}</template></el-table-column><el-table-column prop="report_id" label="来源诊断ID" /></el-table>
   <p class="muted">风险依据：{{ selected.profile.risk.reasons.join('；') || selected.profile.risk.explanation }}</p>
   <p>累计资源观测秒数：{{ value(selected.profile.engagement.effective_seconds) }}。{{ selected.profile.engagement.explanation }}</p>
   <ul><li v-for="p in selected.profile.preference.items" :key="p.key">{{ p.label }}：次数 {{ value(p.count) }}，占比 {{ value(p.percent) }}%</li></ul>
   <p class="muted">{{ selected.profile.preference.explanation }}</p>
  </template>
  <template v-if="items.length > 1">
   <h3>比较两份历史</h3>
   <el-select v-model="before" aria-label="较早快照" placeholder="较早快照" style="width:100%;max-width:420px"><el-option v-for="s in items" :key="s.id" :label="label(s)" :value="s.id" /></el-select>
   <el-select v-model="after" aria-label="较晚快照" placeholder="较晚快照" style="width:100%;max-width:420px"><el-option v-for="s in items" :key="s.id" :label="label(s)" :value="s.id" /></el-select>
   <el-button :loading="checking" :disabled="!before || !after || before === after" @click="compare">对比</el-button>
  </template>
  <template v-if="comparison">
   <el-alert v-for="warning in comparison.warnings" :key="warning" :title="warning" type="info" :closable="false" />
   <el-table :data="comparison.points"><el-table-column prop="name" label="知识点" /><el-table-column label="掌握度前→后（%）"><template #default="{ row }">{{ value(row.mastery.before) }} → {{ value(row.mastery.after) }}</template></el-table-column><el-table-column label="变化（百分点）"><template #default="{ row }">{{ value(row.mastery.delta) }}</template></el-table-column><el-table-column label="正确率前→后（%）"><template #default="{ row }">{{ value(row.accuracy.before) }} → {{ value(row.accuracy.after) }}</template></el-table-column></el-table>
   <p>有效活动次数：{{ value(comparison.engagement.event_count.before) }} → {{ value(comparison.engagement.event_count.after) }}；活跃天数：{{ value(comparison.engagement.active_days.before) }} → {{ value(comparison.engagement.active_days.after) }}。</p>
   <p>资源累计观测秒数：{{ value(comparison.engagement.effective_seconds.before) }} → {{ value(comparison.engagement.effective_seconds.after) }}。</p>
   <ul><li v-for="(p, key) in comparison.preference" :key="key">{{ preferenceNames[key] ?? key }}占比：{{ value(p.before) }} → {{ value(p.after) }}%；变化 {{ value(p.delta) }} 个百分点。</li></ul>
   <p>风险状态：{{ riskName(comparison.risk_before) }} → {{ riskName(comparison.risk_after) }}。</p>
  </template>
 </section>
</template>
