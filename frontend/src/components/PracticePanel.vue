<script setup lang="ts">
import { computed, onUnmounted, reactive, ref, watch } from 'vue'
import { api, errorMessage } from '../api/client'
import { session } from '../composables/useSession'
import type { PracticeExercise, PracticeProgress, PracticeSubmission } from '../types/foundation'

type Submission = PracticeSubmission & { parent_submission_id: string | null }
const props = defineProps<{
  courseId: string; chapterId: string; knowledgePointId: string
  exercise?: PracticeExercise; editable: boolean
}>()
const emit = defineEmits<{ created: [] }>()
const opened = ref(false), busy = ref(false), loading = ref(false), error = ref('')
const question = ref(''), answer = ref(''), submissions = ref<Submission[]>([])
const progress = ref<PracticeProgress>()
const followupAnswers = reactive<Record<string, string>>({})
const requests = new Map<string, { answer: string; id: string }>()
const teacher = computed(() => session.user?.role === 'teacher')
const base = computed(() => `/courses/${encodeURIComponent(props.courseId)}/practices`)
const exerciseBase = computed(() => `${base.value}/${encodeURIComponent(props.exercise?.id ?? '')}`)
const statusLabels = { pending: '诊断中', supported: '诊断完成', insufficient: '证据不足', failed: '诊断失败' }
let timer: ReturnType<typeof setTimeout> | undefined
let generation = 0

function requestId(key: string, text: string) {
  const previous = requests.get(key)
  if (previous?.answer === text) return previous.id
  const id = crypto.randomUUID()
  requests.set(key, { answer: text, id })
  return id
}

async function load(silent = false) {
  if (!props.exercise || !opened.value) return
  clearTimeout(timer)
  const run = generation
  if (!silent) loading.value = true
  try {
    if (teacher.value) {
      const result = await api<PracticeProgress>(`${exerciseBase.value}/progress`)
      if (run !== generation) return
      progress.value = result
      if (result.students.some(row => row.latest_submission?.status === 'pending')) {
        timer = setTimeout(() => void load(true), 1500)
      }
    } else {
      const result = await api<Submission[]>(`${exerciseBase.value}/submissions/me`)
      if (run !== generation) return
      submissions.value = result
      if (result.some(row => row.status === 'pending')) timer = setTimeout(() => void load(true), 1200)
    }
    error.value = ''
  } catch (e) { if (run === generation) error.value = errorMessage(e) }
  finally { if (run === generation && !silent) loading.value = false }
}

async function create() {
  if (!question.value.trim() || busy.value) return
  const run = generation
  busy.value = true; error.value = ''
  try {
    await api(`${base.value.replace(/\/practices$/, '')}/chapters/${encodeURIComponent(props.chapterId)}/practices`, {
      method: 'POST', body: { knowledge_point_id: props.knowledgePointId, question_text: question.value.trim() },
    })
    if (run === generation) { question.value = ''; emit('created') }
  } catch (e) { if (run === generation) error.value = errorMessage(e) }
  finally { if (run === generation) busy.value = false }
}

async function submit(parent?: Submission) {
  const text = (parent ? followupAnswers[parent.id] ?? '' : answer.value).trim()
  if (!text || busy.value) return
  const run = generation, key = parent?.id ?? 'initial'
  busy.value = true; error.value = ''
  try {
    const path = parent
      ? `${exerciseBase.value}/submissions/${encodeURIComponent(parent.id)}/followups`
      : `${exerciseBase.value}/submissions`
    await api<Submission>(path, { method: 'POST', body: { answer: text, request_id: requestId(key, text) } })
    if (run !== generation) return
    requests.delete(key)
    if (parent) followupAnswers[parent.id] = ''; else answer.value = ''
    await load()
  } catch (e) { if (run === generation) error.value = errorMessage(e) }
  finally { if (run === generation) busy.value = false }
}

async function retry(row: PracticeSubmission) {
  if (busy.value) return
  const run = generation
  busy.value = true; error.value = ''
  try {
    await api(`${exerciseBase.value}/submissions/${encodeURIComponent(row.id)}/retry`, { method: 'POST' })
    if (run === generation) await load()
  } catch (e) { if (run === generation) error.value = errorMessage(e) }
  finally { if (run === generation) busy.value = false }
}

function toggle() { opened.value = !opened.value; if (opened.value) void load(); else clearTimeout(timer) }
watch(() => [props.courseId, props.chapterId, props.knowledgePointId, props.exercise?.id], () => {
  ++generation; clearTimeout(timer); requests.clear()
  opened.value = false; busy.value = false; loading.value = false; error.value = ''
  question.value = ''; answer.value = ''; submissions.value = []; progress.value = undefined
  Object.keys(followupAnswers).forEach(key => delete followupAnswers[key])
})
onUnmounted(() => { ++generation; clearTimeout(timer) })
</script>

<template>
  <section v-if="exercise || editable" class="practice-box" aria-label="知识点小练习">
    <div class="practice-entry">
      <div><strong>知识点小练习</strong><p v-if="exercise">{{ exercise.question_text }}</p></div>
      <el-button @click="toggle">{{ opened ? '收起' : !exercise ? '添加小练习' : teacher ? '查看提交情况' : '完成小练习' }}</el-button>
    </div>
    <div v-if="opened" class="practice-content" v-loading="loading">
      <el-alert v-if="error" :title="error" type="error" :closable="false" show-icon />
      <template v-if="!exercise && editable">
        <label :for="`practice-question-${knowledgePointId}`">简答题题目</label>
        <el-input :id="`practice-question-${knowledgePointId}`" v-model="question" type="textarea" :rows="3" maxlength="4000" show-word-limit />
        <el-button type="primary" :disabled="!question.trim()" :loading="busy" @click="create">创建小练习</el-button>
      </template>
      <template v-else-if="teacher && progress">
        <div class="practice-stats"><span>课程学生 {{ progress.student_count }}</span><span>已提交 {{ progress.submitted_count }}</span><span>需关注 {{ progress.attention_count }}</span></div>
        <p class="muted">需关注表示诊断失败、证据不足或暂估掌握度低于 60%，用于教学提醒。</p>
        <el-table :data="progress.students" class="practice-table">
          <el-table-column prop="display_name" label="学生" />
          <el-table-column label="最新状态"><template #default="scope">{{ scope.row.latest_submission ? statusLabels[scope.row.latest_submission.status as keyof typeof statusLabels] : '未提交' }}</template></el-table-column>
          <el-table-column label="提醒"><template #default="scope">{{ scope.row.needs_attention ? '需关注' : '—' }}</template></el-table-column>
          <el-table-column label="最近作答" min-width="180"><template #default="scope"><span class="answer-preview">{{ scope.row.latest_submission?.original_answer || '—' }}</span></template></el-table-column>
          <el-table-column label="诊断摘要" min-width="180"><template #default="scope">{{ scope.row.latest_submission?.diagnosis?.problem_description || scope.row.latest_submission?.error_message || '—' }}</template></el-table-column>
          <el-table-column label="操作"><template #default="scope"><el-button v-if="scope.row.latest_submission?.status === 'failed'" :loading="busy" @click="retry(scope.row.latest_submission)">重试诊断</el-button></template></el-table-column>
        </el-table>
      </template>
      <template v-else-if="exercise && !teacher">
        <label :for="`practice-answer-${knowledgePointId}`">我的作答</label>
        <el-input :id="`practice-answer-${knowledgePointId}`" v-model="answer" type="textarea" :rows="3" maxlength="4000" show-word-limit />
        <div class="practice-actions"><el-button type="primary" :disabled="!answer.trim()" :loading="busy" @click="submit()">提交并诊断</el-button><el-button @click="load()">刷新记录</el-button></div>
        <p class="muted">原答案先保存，再请求 AI 诊断。以下最多展示最近 50 次作答和追问回复。</p>
        <el-empty v-if="!submissions.length" description="还没有作答记录" :image-size="50" />
        <article v-for="row in submissions" :key="row.id" class="practice-result">
          <div class="practice-result-head"><strong>{{ row.parent_submission_id ? '追问回复' : '原题作答' }}</strong><el-tag :type="row.status === 'failed' ? 'danger' : 'info'">{{ statusLabels[row.status] }}</el-tag></div>
          <p>{{ row.original_answer }}</p>
          <p v-if="row.parent_submission_id" class="muted">关联上一轮：{{ row.parent_submission_id }}</p>
          <template v-if="row.diagnosis">
            <p><strong>诊断：</strong>{{ row.diagnosis.problem_description }}</p>
            <p><strong>建议：</strong>{{ row.diagnosis.recommendation }}</p>
            <p class="muted">暂估掌握度：{{ row.diagnosis.mastery === null ? '证据不足，暂不判断' : `${Math.round(row.diagnosis.mastery * 100)}%` }} · 作答证据：{{ row.event_id }}</p>
            <p><strong>思考追问：</strong>{{ row.diagnosis.followup_question }}</p>
            <el-input v-model="followupAnswers[row.id]" type="textarea" :rows="2" maxlength="4000" aria-label="回复本轮追问" />
            <el-button :disabled="!(followupAnswers[row.id] ?? '').trim()" :loading="busy" @click="submit(row)">回复追问并复核</el-button>
          </template>
          <template v-else-if="row.status === 'failed'"><p>{{ row.error_message }}</p><el-button :loading="busy" @click="retry(row)">重试诊断</el-button></template>
          <p v-else>作答已保存，正在诊断…</p>
        </article>
      </template>
    </div>
  </section>
</template>
