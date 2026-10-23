<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { request, type Mode, type Question } from '../api'
const router = useRouter()
const question = ref<Question>()
const answer = ref('')
const mode = ref<Mode>('live')
const error = ref('')
const busy = ref(false)
const started = Date.now()
onMounted(async () => { try { question.value = await request<Question>('/api/dev/question') } catch { error.value = '无法加载题目，请检查后端是否启动，然后刷新页面。' } })
function changeMode() { if (mode.value === 'demo' && question.value) answer.value = question.value.sample_answer }
async function submit() {
  error.value = ''; busy.value = true
  try {
    const data = await request<{diagnosis_id: string}>('/api/dev/submissions', { answer: answer.value, mode: mode.value, duration_seconds: Math.min(86400, Math.floor((Date.now() - started) / 1000)) })
    await router.push(`/diagnoses/${data.diagnosis_id}`)
  } catch (e) { error.value = e instanceof Error ? e.message : '提交失败，请稍后重试。' }
  finally { busy.value = false }
}
</script>

<template>
  <section class="page-heading"><div class="eyebrow">LEARNING LAB / 01</div><h1>一次作答，看见学习的线索。</h1><p>从「验证与确认」出发，体验作答记录与结构化诊断的最小流程。</p></section>
  <div class="workflow"><div class="current"><b>1</b><span>提交作答<small>保存原始学习事件</small></span></div><i>→</i><div><b>2</b><span>生成诊断<small>校验结构与证据</small></span></div><i>→</i><div><b>3</b><span>查看反馈<small>诊断、追问与调用记录</small></span></div></div>
  <el-alert v-if="error" :title="error" type="error" show-icon :closable="false" class="alert-space" />
  <div class="submission-grid" v-if="question">
    <section class="panel question-panel"><div class="panel-meta"><span class="eyebrow">练习 01</span><el-tag type="info" effect="plain">概念理解</el-tag></div><h2>{{ question.title }}</h2><p class="question-text">{{ question.text }}</p><div class="question-source">{{ question.source }}</div>
      <div class="answer-heading"><label for="student-answer">学生作答</label><el-button text @click="answer = question.sample_answer" :disabled="busy">填入混淆概念示例</el-button></div>
      <el-input id="student-answer" v-model="answer" type="textarea" :rows="7" maxlength="4000" show-word-limit :disabled="mode === 'demo' || busy" placeholder="请用自己的话说明两个概念的区别，也可以补充一个例子……" />
      <p class="field-note">{{ mode === 'demo' ? '模拟模式固定使用示例答案，结果不会用于评价其他输入。' : '使用模拟学生身份提交，请勿填写真实姓名、学号等个人信息。' }}</p>
      <div class="submit-row"><span>提交后先保存，诊断失败也不会丢失答案。</span><el-button type="primary" size="large" :loading="busy" :disabled="!answer.trim()" @click="submit">{{ mode === 'demo' ? '保存并查看模拟演示' : '保存并发起真实诊断' }} →</el-button></div>
    </section>
    <aside class="right-column"><section class="panel"><span class="eyebrow">本次运行方式</span><h3>选择诊断模式</h3><el-radio-group v-model="mode" class="mode-options" @change="changeMode"><el-radio value="live" border><strong>真实模型调用</strong></el-radio><el-radio v-if="question.demo_enabled" value="demo" border><strong>模拟演示 · 无模型调用</strong></el-radio></el-radio-group>
      <el-alert v-if="mode === 'demo'" title="固定示例，仅展示流程" description="诊断文本与数值均为模拟数据，不代表 AI 真实输出或学习效果。" type="warning" :closable="false" show-icon />
      <el-alert v-else :title="question.model_configured ? '模型参数已配置' : '尚未配置模型密钥与模型名称'" :description="question.model_configured ? '提交后将请求配置的模型服务，可能产生费用。' : '仍可保存作答并展示明确的诊断失败状态。'" :type="question.model_configured ? 'success' : 'info'" :closable="false" show-icon />
    </section><section class="guide-card"><div class="eyebrow">你将看到什么</div><h3>结果背后，也有证据。</h3><p>每次作答保留原始内容和提交时间，可结合诊断建议回顾自己的理解与进步。</p><ul><li>原始答案与学习事件</li><li>诊断建议与引导性追问</li><li>模型、提示版本与调用耗时</li></ul></section></aside>
  </div>
</template>
