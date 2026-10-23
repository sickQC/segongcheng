<script setup lang="ts">
import { computed, onUnmounted, ref, watch } from 'vue'
import { api, errorMessage } from '../api/client'
import { session } from '../composables/useSession'
import type { LearningTopic, LectureLink } from '../types/learning'
type Stage = 'engage' | 'explore' | 'explain' | 'elaborate' | 'evaluate'
type Turn = { id: string; answer: string; status: string; stage_before: Stage; stage_after: Stage | null; error_message: string | null; event_id: string; output: { reply: string; quality: number; transition_reason: string; completed: boolean; evaluation_correct: boolean | null } | null }
type Session = { id: string; course_id: string; knowledge_point_id: string; knowledge_point_name: string; chapter: { id: string; title: string } | null; lectures: LectureLink[]; source: { type: string; attempt_id?: string; options?: string[]; question: string; original_answer: string; diagnosis: { problem_description: string; recommendation: string } } | null; practice_available: boolean; stage: Stage; status: string; pending_turn_id: string | null; task: string; evaluation: { stem: string; options: Record<string, string> } | null; turns: Turn[] }
const props = defineProps<{ courseId: string; sessionId?: string; knowledgePointId?: string; resourceId?: string }>()
const emit = defineEmits<{ consult: [lecture?: LectureLink, knowledgePointId?: string]; selected: [id: string] }>()
const origin = computed(() => current.value?.source?.type === 'assessment'
  ? { path: `/courses/${props.courseId}/quiz`, query: { attempt: current.value.source.attempt_id } }
  : { path: `/courses/${props.courseId}`, query: { practice: current.value?.knowledge_point_id } })
const labels: Record<Stage, string> = { engage: '引入', explore: '探究', explain: '解释', elaborate: '迁移', evaluate: '评价' }
const stages = Object.keys(labels) as Stage[]
type Chapter = { id: string; title: string; knowledge_points: { id: string; name: string }[] }
const points = ref<LearningTopic[]>([]), chapters = ref<Chapter[]>([]), selected = ref(''), selectedChapter = ref(''), showAll = ref(false)
const scoped = computed(() => !showAll.value && !props.sessionId && !props.knowledgePointId && props.resourceId && props.resourceId !== 'kb:all')
const scopedPoints = computed(() => scoped.value ? points.value.filter(p => p.lectures.some(l => l.resource_id === props.resourceId)) : points.value)
const chapterOptions = computed(() => scoped.value ? chapters.value.filter(ch => scopedPoints.value.some(p => p.chapter_id === ch.id)) : chapters.value)
const pointOptions = computed(() => (chapters.value.find(ch => ch.id === selectedChapter.value)?.knowledge_points ?? []).filter(p => !scoped.value || scopedPoints.value.some(t => t.knowledge_point_id === p.id)))
const available = (id: string) => points.value.some(p => p.knowledge_point_id === id)
const selectedTopic = computed(() => points.value.find(p => p.knowledge_point_id === selected.value))
const currentTopic = computed(() => points.value.find(p => p.knowledge_point_id === current.value?.knowledge_point_id))
const currentLectures = computed(() => currentTopic.value?.lectures ?? current.value?.lectures ?? [])
function choosePoint(id: string) { selected.value = id; selectedChapter.value = chapters.value.find(ch => ch.knowledge_points.some(p => p.id === id))?.id ?? '' }
function changeChapter() { selected.value = pointOptions.value.find(p => available(p.id))?.id ?? '' }
function allTopics() { showAll.value = true; choosePoint(points.value[0]?.knowledge_point_id ?? '') }
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
    if (value.course_id !== props.courseId) throw new Error('该学习会话不属于当前课程')
    current.value = value; choosePoint(value.knowledge_point_id)
    localStorage.setItem(storageKey.value, value.id)
    if (value.pending_turn_id) timer = setTimeout(() => void refresh(id), 1500)
  } catch (e) { if (run === generation) error.value = errorMessage(e) }
}
async function load() {
  const run = ++generation
  clearTimeout(timer); current.value = undefined; error.value = ''; answer.value = ''; choice.value = ''
  busy.value = false; pendingKey = undefined; points.value = []; histories.value = []; chapters.value = []; selected.value = ''; selectedChapter.value = ''; showAll.value = false
  try {
    const [list, outline] = await Promise.all([
      api<LearningTopic[]>(`/courses/${encodeURIComponent(props.courseId)}/learning-templates`),
      api<{ chapters: Chapter[] }>(`/courses/${encodeURIComponent(props.courseId)}/outline`),
    ])
    if (run !== generation) return
    points.value = list; chapters.value = outline.chapters
    choosePoint((props.knowledgePointId && available(props.knowledgePointId) ? props.knowledgePointId : scopedPoints.value[0]?.knowledge_point_id) ?? '')
    if (props.knowledgePointId && !props.sessionId && !available(props.knowledgePointId)) { choosePoint(''); error.value = '该知识点不在当前课程的 5E 配置中，请从课程章节重新选择。' }
    const history = await api<typeof histories.value>(`/courses/${encodeURIComponent(props.courseId)}/learning-sessions`)
    if (run !== generation) return
    histories.value = history
    const saved = props.sessionId || (!props.knowledgePointId && !scoped.value ? localStorage.getItem(storageKey.value) : null)
    if (saved && student.value) await refresh(saved)
  } catch (e) { if (run === generation) error.value = errorMessage(e) }
}
async function start() {
  if (!selected.value || !available(selected.value) || busy.value) return
  busy.value = true; error.value = ''
  const run = generation
  try {
    const value = await api<Session>('/learning-sessions', { method: 'POST', body: { course_id: props.courseId, knowledge_point_id: selected.value, request_id: startRequest } })
    if (run !== generation) return
    current.value = value; localStorage.setItem(storageKey.value, value.id)
    startRequest = crypto.randomUUID(); pendingKey = undefined; answer.value = ''; choice.value = ''
    histories.value = await api<typeof histories.value>(`/courses/${encodeURIComponent(props.courseId)}/learning-sessions`)
    if (run === generation) emit('selected', value.id)
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
async function resume(id: string) { clearTimeout(timer); const run = ++generation; busy.value = false; pendingKey = undefined; error.value = ''; current.value = undefined; answer.value = ''; choice.value = ''; localStorage.setItem(storageKey.value, id); await refresh(id); if (run === generation && current.value) emit('selected', id) }
async function retry(turn: Turn) {
  if (!current.value || busy.value || current.value.pending_turn_id) return
  const run = generation, id = current.value.id
  busy.value = true; error.value = ''
  try {
    await api(`/learning-sessions/${encodeURIComponent(id)}/turns/${encodeURIComponent(turn.id)}/retry`, { method: 'POST' })
    if (run === generation) await refresh(id)
  } catch (e) { if (run === generation) error.value = errorMessage(e) }
  finally { if (run === generation) busy.value = false }
}
watch(selected, () => { startRequest = crypto.randomUUID() })
watch(() => [props.courseId, props.sessionId, props.knowledgePointId, props.resourceId], () => void load(), { immediate: true })
onUnmounted(() => { ++generation; clearTimeout(timer) })
</script>

<template>
  <section aria-label="5E 学习会话">
    <p>从场景引入、探究比较到解释、迁移和评价；阶段由本轮回答质量决定，答案和反馈均会保存。</p>
    <el-alert v-if="error" :title="error" type="error" :closable="false" />
    <template v-if="student">
      <p class="muted">先选课程章节，再选该章知识点；每个知识点下方列出对应的讲义小节。</p>
      <p v-if="scoped" class="muted">当前只显示所读讲义对应的知识点。<el-button text @click="allTopics">查看课程全部知识点</el-button></p>
      <div class="practice-actions">
        <el-select v-model="selectedChapter" aria-label="5E 课程章节" placeholder="选择课程章节" :disabled="busy || !!current?.pending_turn_id" @change="changeChapter"><el-option v-for="chapter in chapterOptions" :key="chapter.id" :value="chapter.id" :label="chapter.title" /></el-select>
        <el-select v-model="selected" aria-label="5E 知识点" placeholder="选择本章知识点" :disabled="busy || !!current?.pending_turn_id || !selectedChapter"><el-option v-for="point in pointOptions" :key="point.id" :value="point.id" :label="point.name + (available(point.id) ? '' : '（未配置5E）')" :disabled="!available(point.id)" /></el-select>
        <el-button :disabled="!selected || !available(selected) || !!current?.pending_turn_id" :loading="busy" @click="start">开始新会话</el-button>
      </div>
      <p v-if="scoped && !scopedPoints.length" class="muted">这份讲义尚未配置对应的 5E 知识点，可先阅读或课程答疑，或查看课程全部知识点。</p>
      <div v-if="selectedTopic" class="practice-result" aria-label="所选知识点的讲义对应关系">
        <strong>{{ selectedTopic.chapter_title }} → {{ selectedTopic.name }}</strong>
        <p v-for="lecture in selectedTopic.lectures" :key="lecture.resource_id + lecture.section">《{{ lecture.title }}》 · {{ lecture.section }} <el-button text type="primary" @click="emit('consult', lecture, current?.knowledge_point_id === selected ? undefined : selected)">阅读对应小节</el-button></p>
        <p v-if="!selectedTopic.lectures.length" class="muted">尚未绑定可阅读的配套讲义；当前依据课程知识点定义进行引导。</p>
      </div>
      <div v-if="histories.length" class="practice-actions"><el-select placeholder="恢复历史会话" aria-label="恢复5E会话" @change="resume(String($event))"><el-option v-for="item in histories" :key="item.id" :value="item.id" :label="`${item.knowledge_point_name} · ${labels[item.stage]} · ${item.status === 'completed' ? '已完成' : '进行中'}`" /></el-select></div>
    </template>
    <p v-else class="muted">请使用学生账号开始学习会话。</p>
    <p v-if="current && current.knowledge_point_id !== selected" class="muted">已切换待学知识点，点击“开始新会话”后进入。原会话保留在历史记录中。</p>
    <template v-if="current && current.knowledge_point_id === selected">
      <h3>{{ current.knowledge_point_name }}</h3>
      <p class="muted">所属课程章节：{{ current.chapter?.title ?? currentTopic?.chapter_title ?? '原章节已调整' }} · <RouterLink :to="{ path: `/courses/${courseId}`, query: { knowledge_point: current.knowledge_point_id } }">在课程目录中查看</RouterLink></p>
      <aside v-if="current.source" class="practice-result" aria-label="本次学习的原题">
        <strong>本次从{{ current.source.type === 'assessment' ? '测验错题' : '知识点小练习' }}进入</strong>
        <p><strong>原题：</strong>{{ current.source.question }}</p>
        <p v-for="(option, index) in current.source.options ?? []" :key="index">{{ String.fromCharCode(65 + index) }}. {{ option }}</p>
        <p><strong>我的原答案：</strong>{{ current.source.original_answer || '未作答' }}</p>
        <p><strong>此前诊断：</strong>{{ current.source.diagnosis.problem_description }}</p>
        <p><strong>巩固建议：</strong>{{ current.source.diagnosis.recommendation }}</p>
        <RouterLink :to="origin">回看原题与诊断</RouterLink>
      </aside>
      <div class="practice-actions"><el-button @click="emit('consult', currentLectures[0])">查阅本知识点讲义 / 课程答疑</el-button></div>
      <div class="practice-actions"><el-tag v-for="stage in stages" :key="stage" :type="stage === current.stage ? 'success' : 'info'">{{ labels[stage] }}</el-tag></div>
      <p><strong>当前任务：</strong>{{ current.task }}</p>
      <article v-for="turn in current.turns" :key="turn.id" class="practice-result">
        <strong>{{ labels[turn.stage_before] }} · 我的作答</strong><p>{{ turn.answer }}</p>
        <template v-if="turn.output"><p>{{ turn.output.reply }}</p><p class="muted">回答质量 {{ Math.round(turn.output.quality * 100) }}% · {{ turn.output.transition_reason }}</p><p v-if="turn.output.evaluation_correct !== null">小测：{{ turn.output.evaluation_correct ? '正确' : '仍需巩固' }}</p></template>
        <p v-else>{{ turn.status === 'pending' ? '正在生成反馈…' : turn.error_message }}</p>
        <el-button v-if="student && turn.status === 'failed' && current.status === 'active' && current.turns.at(-1)?.id === turn.id && current.stage === turn.stage_before" :loading="busy" :disabled="!!current.pending_turn_id" @click="retry(turn)">用已保存的答案重试</el-button>
      </article>
      <div v-if="current.status === 'completed'" aria-label="完成后的学习安排">
        <el-alert title="五阶段学习已完成，评价小测与本轮解释已通过" type="success" :closable="false" />
        <p>回看原题，试着用现在的理解重新解释；也可以继续练习，再把新作答加入综合诊断。</p>
        <div class="practice-actions">
          <RouterLink v-if="current.source" :to="origin"><el-button>回看原题</el-button></RouterLink>
          <RouterLink v-if="current.practice_available" :to="{ path: `/courses/${courseId}`, query: { practice: current.knowledge_point_id } }"><el-button>再做知识点小练习</el-button></RouterLink>
          <RouterLink :to="{ path: `/courses/${courseId}/report`, query: { knowledge_point: current.knowledge_point_id } }"><el-button type="primary">查看学习报告</el-button></RouterLink>
        </div>
      </div>
      <template v-else-if="student">
        <div v-if="current.evaluation" class="practice-result"><strong>{{ current.evaluation.stem }}</strong><el-radio-group v-model="choice" aria-label="评价小测选项"><el-radio v-for="(text, key) in current.evaluation.options" :key="key" :value="key">{{ key }}. {{ text }}</el-radio></el-radio-group></div>
        <el-input v-model="answer" type="textarea" :rows="3" maxlength="4000" aria-label="5E本轮作答" placeholder="说明你的思考；评价阶段还需解释小测依据" :disabled="!!current.pending_turn_id" />
        <div class="practice-actions"><el-button type="primary" :loading="busy || !!current.pending_turn_id" :disabled="!answer.trim() || (current.stage === 'evaluate' && !choice)" @click="submit">提交本轮思考</el-button><el-button @click="refresh()">刷新会话</el-button></div>
        <p class="muted">失败轮次保留原答案；可重新提交。模型评价用于学习反馈，不是正式成绩。</p>
      </template>
    </template>
  </section>
</template>
