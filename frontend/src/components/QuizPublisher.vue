<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { api, errorMessage } from '../api/client'
import type { Outline } from '../types/foundation'
const props = defineProps<{ courseId: string }>()
const emit = defineEmits<{ published: [] }>()
type Question = { knowledge_point_id: string; prerequisite_for: string | null; type: string; stem: string; options: string[]; correct_values: string[]; explanation: string; points: number }
const outline = ref<Outline>(), title = ref(''), minutes = ref(20), attempts = ref(1)
const kp = ref(''), type = ref('single'), stem = ref(''), options = ref(''), correct = ref(''), explanation = ref(''), points = ref(10)
const prerequisiteFor = ref('')
const questions = ref<Question[]>([]), busy = ref(false), error = ref(''), success = ref('')
const knowledgePoints = computed(() => outline.value?.chapters.flatMap(chapter => chapter.knowledge_points) ?? [])
const lines = (value: string) => value.split(/\r?\n/).map(item => item.trim()).filter(Boolean)
watch(() => props.courseId, async () => {
  questions.value = []; success.value = ''; error.value = ''
  try { outline.value = await api<Outline>(`/courses/${encodeURIComponent(props.courseId)}/outline`); kp.value = knowledgePoints.value[0]?.id ?? '' }
  catch (e) { error.value = errorMessage(e) }
}, { immediate: true })
watch(type, value => { options.value = value === 'boolean' ? '正确\n错误' : ''; correct.value = '' })
function add() {
  error.value = ''; success.value = ''
  if (!kp.value || !stem.value.trim() || !correct.value.trim() || !explanation.value.trim()) { error.value = '请补全知识点、题目、标准答案和解析。'; return }
  questions.value.push({ knowledge_point_id: kp.value, prerequisite_for: prerequisiteFor.value || null, type: type.value, stem: stem.value.trim(), options: type.value === 'fill' ? [] : lines(options.value), correct_values: lines(correct.value), explanation: explanation.value.trim(), points: points.value })
  stem.value = ''; options.value = type.value === 'boolean' ? '正确\n错误' : ''; correct.value = ''; explanation.value = ''
}
async function publish() {
  if (busy.value || !questions.value.length || !title.value.trim()) return
  busy.value = true; error.value = ''; success.value = ''
  try { await api(`/courses/${encodeURIComponent(props.courseId)}/quizzes`, { method: 'POST', body: { title: title.value.trim(), duration_minutes: minutes.value, max_attempts: attempts.value, questions: questions.value } }); questions.value = []; title.value = ''; success.value = '测验已发布，课程学生可以作答。'; emit('published') }
  catch (e) { error.value = errorMessage(e) }
  finally { busy.value = false }
}
</script>
<template>
  <section class="panel" aria-label="发布课程测验">
    <h2>发布课程测验</h2><p class="muted">题目发布后冻结；标准答案仅供判分，学生交卷前不会收到。</p>
    <el-alert v-if="error" :title="error" type="error" :closable="false" /><el-alert v-if="success" :title="success" type="success" :closable="false" />
    <el-form label-position="top">
      <el-form-item label="测验标题"><el-input v-model="title" maxlength="200" aria-label="测验标题" /></el-form-item>
      <el-form-item label="作答分钟数"><el-input-number v-model="minutes" :min="1" :max="180" aria-label="作答分钟数" /></el-form-item>
      <el-form-item label="最多作答次数"><el-input-number v-model="attempts" :min="1" :max="10" aria-label="最多作答次数" /></el-form-item>
      <el-form-item label="知识点"><el-select v-model="kp" aria-label="测验知识点"><el-option v-for="point in knowledgePoints" :key="point.id" :value="point.id" :label="point.name" /></el-select></el-form-item>
      <el-form-item label="本题检查哪个知识点的基础（可选）"><el-select v-model="prerequisiteFor" clearable aria-label="前置检查目标"><el-option v-for="point in knowledgePoints" :key="point.id" :value="point.id" :label="point.name" /></el-select></el-form-item>
      <el-form-item label="题型"><el-select v-model="type" aria-label="题型"><el-option v-for="(label, value) in { single: '单选', multiple: '多选', boolean: '判断', fill: '填空' }" :key="value" :label="label" :value="value" /></el-select></el-form-item>
      <el-form-item label="题目"><el-input v-model="stem" type="textarea" maxlength="2000" aria-label="测验题目" /></el-form-item>
      <el-form-item v-if="type !== 'fill'" label="选项（每行一个）"><el-input v-model="options" type="textarea" aria-label="测验选项" :disabled="type === 'boolean'" /></el-form-item>
      <el-form-item :label="type === 'fill' ? '可接受的填空答案（每行一个）' : '正确选项文本（多选每行一个）'"><el-input v-model="correct" type="textarea" aria-label="测验标准答案" /></el-form-item>
      <el-form-item label="解析"><el-input v-model="explanation" type="textarea" maxlength="2000" aria-label="测验解析" /></el-form-item>
      <el-form-item label="分值"><el-input-number v-model="points" :min="1" :max="100" aria-label="题目分值" /></el-form-item>
      <el-button :disabled="busy || questions.length >= 100" @click="add">加入题目</el-button>
    </el-form>
    <article v-for="(question, index) in questions" :key="index" class="practice-result"><strong>{{ index + 1 }}. {{ question.stem }}</strong><p>标准答案：{{ question.correct_values.join('、') }} · {{ question.points }} 分</p><el-button :disabled="busy" @click="questions.splice(index, 1)">移除未发布题目</el-button></article>
    <el-button type="primary" :loading="busy" :disabled="!title.trim() || !questions.length" @click="publish">发布测验（{{ questions.length }} 题）</el-button>
  </section>
</template>
