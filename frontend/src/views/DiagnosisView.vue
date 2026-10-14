<script setup lang="ts">
import { computed, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { dateText, request, statusText, type Detail, type Diagnosis } from '../api'
const route = useRoute(), router = useRouter()
const rows = ref<Diagnosis[]>([]), detail = ref<Detail>(), error = ref(''), retrying = ref(false)
let timer: ReturnType<typeof setTimeout> | undefined
let generation = 0
const latestTrace = computed(() => detail.value?.traces.at(-1))
async function load() {
  clearTimeout(timer)
  const run = ++generation
  error.value = ''
  try {
    const id = route.params.id
    if (id) {
      const value = await request<Detail>(`/api/diagnoses/${encodeURIComponent(String(id))}`)
      if (run !== generation) return
      detail.value = value
      if (value.status === 'pending') timer = setTimeout(load, 1200)
    } else {
      const value = await request<Diagnosis[]>('/api/diagnoses')
      if (run === generation) rows.value = value
    }
  } catch (e) { if (run === generation) error.value = e instanceof Error ? e.message : '读取失败' }
}
async function retry() {
  if (!detail.value) return
  retrying.value = true
  try { await request(`/api/diagnoses/${detail.value.id}/retry`, {}); await load() }
  catch (e) { error.value = e instanceof Error ? e.message : '重试失败' }
  finally { retrying.value = false }
}
watch(() => route.params.id, () => { detail.value = undefined; void load() }, { immediate: true })
onUnmounted(() => { ++generation; clearTimeout(timer) })
</script>

<template>
  <section class="page-heading"><div class="eyebrow">LEARNING LAB / 02</div><h1>{{ route.params.id ? '让反馈有据可查。' : '每一次尝试，都有记录。' }}</h1><p>查看原始作答、结构化诊断和处理过程。</p></section>
  <el-alert v-if="error" :title="error" type="error" :closable="false" show-icon class="alert-space" />
  <div class="toolbar"><el-button @click="router.push('/dev/submit')">← 返回作答</el-button><el-button v-if="route.params.id" @click="router.push('/diagnoses')">全部记录</el-button><el-button @click="load">刷新</el-button></div>
  <section v-if="!route.params.id" class="panel"><div class="panel-meta"><h2>最近作答</h2><span class="muted">最多显示 50 条</span></div><el-empty v-if="!rows.length" description="还没有作答记录，先完成一次练习吧。" /><el-table v-else :data="rows" style="width:100%"><el-table-column label="提交时间" min-width="180"><template #default="scope">{{ dateText(scope.row.created_at) }}</template></el-table-column><el-table-column label="模式" min-width="150"><template #default="scope"><el-tag :type="scope.row.mode === 'demo' ? 'warning' : 'info'">{{ scope.row.mode === 'demo' ? '模拟数据 · 无模型调用' : '真实调用' }}</el-tag></template></el-table-column><el-table-column label="处理状态" min-width="140"><template #default="scope">{{ scope.row.mode === 'demo' && scope.row.status === 'supported' ? '模拟演示完成' : statusText(scope.row.status) }}</template></el-table-column><el-table-column label="操作" width="100"><template #default="scope"><el-button link type="primary" @click="router.push(`/diagnoses/${scope.row.id}`)">查看详情 →</el-button></template></el-table-column></el-table></section>
  <template v-else-if="detail">
    <el-alert v-if="detail.mode === 'demo'" title="模拟演示：没有调用大模型" description="以下诊断文本、掌握度与置信度是固定示例，仅演示界面与数据流程，不能作为模型效果或课程验收证据。" type="warning" :closable="false" show-icon class="alert-space" />
    <div class="result-banner"><div><span class="eyebrow">作答已保存</span><h2>{{ detail.mode === 'demo' && detail.status === 'supported' ? '模拟演示完成' : statusText(detail.status) }}</h2><p>{{ dateText(detail.created_at) }} · 软件验证与确认</p></div><el-tag :type="detail.status === 'failed' ? 'danger' : 'success'" size="large">{{ detail.status === 'failed' ? '原始答案保留' : '事件已入库' }}</el-tag></div>
    <section v-if="detail.status === 'failed'" class="panel alert-space"><h3>本次诊断未完成</h3><p>{{ detail.error_message }}</p><p class="mono muted">{{ detail.error_code }}</p><el-button type="primary" :loading="retrying" @click="retry">重试诊断</el-button><p class="field-note">配置模型后请重启后端，再重试。重试会保留原事件，并新增调用记录。</p></section>
    <section v-if="detail.status === 'pending'" class="panel alert-space"><h3>正在处理，请稍候…</h3><p>页面会自动更新。作答已经保存，可以稍后从诊断记录返回。</p></section>
    <div class="result-grid" v-if="detail.output"><section class="panel"><span class="eyebrow">诊断反馈</span><h2>{{ detail.output.problem_type === 'concept_confusion' ? '关注两个概念的边界' : detail.output.status === 'insufficient' ? '还需要更多作答依据' : '本次理解反馈' }}</h2><p class="diagnosis-text">{{ detail.output.problem_description }}</p><div class="metrics"><div><span>{{ detail.mode === 'demo' ? '模拟掌握度' : '模型暂估掌握度' }}</span><strong>{{ detail.output.mastery === null ? '暂不判断' : `${Math.round(detail.output.mastery * 100)}%` }}</strong></div><div><span>{{ detail.mode === 'demo' ? '模拟置信度' : '模型自报置信度' }}</span><strong>{{ Math.round(detail.output.confidence * 100) }}%</strong></div></div><p class="field-note">单次答案无法代表完整学习水平；以上数值未经正式评测校准。</p><h3>下一步建议</h3><p>{{ detail.output.recommendation }}</p><div class="evidence"><span>作答证据</span><code>{{ detail.output.evidence_event_ids[0] }}</code></div></section><section class="guide-card"><div class="eyebrow">想一想</div><h2>再往前思考一步</h2><p class="followup">{{ detail.output.followup_question }}</p><p>此阶段仅展示追问，后续迭代再接入追问作答与学习画像。</p><div class="scope-chip">课程资料引用：尚未接入</div></section></div>
    <section class="panel alert-space"><div class="panel-meta"><h3>这次提交了什么</h3><el-tag type="info">{{ detail.event.actor }}</el-tag></div><p class="answer-preview">{{ detail.event.result.answer }}</p><el-collapse><el-collapse-item title="查看完整学习事件 JSON" name="event"><pre>{{ JSON.stringify(detail.event, null, 2) }}</pre></el-collapse-item></el-collapse></section>
    <section class="panel"><div class="panel-meta"><h3>调用记录</h3><span class="muted">{{ detail.traces.length }} 次尝试</span></div><div v-for="trace in detail.traces" :key="trace.trace_id" class="trace-row"><code>{{ trace.trace_id }}</code><span>{{ trace.source === 'demo' ? '模拟 · 未调用模型' : trace.model }}</span><span>{{ trace.latency_ms === null ? '等待处理' : `${trace.latency_ms} ms` }}</span><el-tag :type="trace.status === 'failed' ? 'danger' : 'info'">{{ trace.status }}</el-tag></div><p class="field-note">提示版本：{{ latestTrace?.prompt_version }} · Token：{{ latestTrace?.usage?.total_tokens ?? '无真实统计' }} · 费用：未配置计价，不估算</p></section>
  </template>
</template>
