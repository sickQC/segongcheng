<script setup lang="ts">
import { ref, watch } from 'vue'
import WorkspaceHeader from '../components/WorkspaceHeader.vue'
import ReportPanels from '../components/ReportPanels.vue'
import LearningProfilePanel from '../components/LearningProfilePanel.vue'
import ProfileHistoryPanel from '../components/ProfileHistoryPanel.vue'
import RecommendationPanel from '../components/RecommendationPanel.vue'
import EvidenceDiagnosisPanel from '../components/EvidenceDiagnosisPanel.vue'
import { useWorkspace } from '../composables/useWorkspace'
import { workspaceApi } from '../api/workspace'
import * as sample from '../api/preview'
import { errorMessage } from '../api/client'
import type { Report } from '../types/workspace'

const { courseId, preview, loading, error, run } = useWorkspace()
const report = ref<Report>(), history = ref('real')
const message = ref(''), reply = ref(''), replyContext = ref(''), busy = ref(false)
function load() {
 report.value = undefined; message.value = ''; reply.value = ''; replyContext.value = ''
 void run(() => preview.value ? Promise.resolve(sample.report) : workspaceApi.report(courseId.value, 'baseline', history.value), data => report.value = data)
}
watch([preview, history, courseId], load, { immediate: true })
async function followup() {
 if (!message.value.trim()) return
 busy.value = true; replyContext.value = ''
 try {
  if (preview.value) reply.value = '此处展示提问回复。界面预览不调用模型，也不更新画像。'
  else {
   const result = await workspaceApi.followup(courseId.value, message.value)
   reply.value = result.message
   replyContext.value = result.personalization ? `本次参考了模拟历史：${result.personalization.matched_knowledge_points.join('、')}` : '本次问题未匹配到相关薄弱点，未加入模拟学习历史。'
  }
 } catch (e) { reply.value = errorMessage(e) } finally { busy.value = false }
}
</script>

<template>
 <WorkspaceHeader :course-id="courseId" title="个人学习报告" v-model:preview="preview" :loading="loading || busy" :error="error" @reload="load" />
 <section class="panel"><div class="toolbar"><h2>报告数据来源</h2><el-select v-model="history" :disabled="preview || busy" aria-label="报告数据来源" style="width:220px"><el-option label="真实学习记录" value="real" /><el-option label="模拟历史演示" value="synthetic" /></el-select></div><p class="muted">真实报告仅包含当前学生的数据；模拟历史单独选择，不进入正式画像。</p></section>
 <EvidenceDiagnosisPanel v-if="!preview" :course-id="courseId" @completed="load" />
 <LearningProfilePanel v-if="!preview && report?.learning_profile" :profile="report.learning_profile" :course-id="courseId" />
 <ProfileHistoryPanel v-if="!preview && report?.history_source === 'real'" :course-id="courseId" :refresh-token="report.learning_profile?.generated_at" />
 <RecommendationPanel v-if="!preview && report?.history_source === 'real'" :course-id="courseId" />
 <section v-loading="loading" class="panel">
  <h2>学习反馈与记录</h2>
  <p v-if="preview" class="muted">界面预览使用布局样例，尚未运行推荐算法或对比评测。</p>
  <template v-if="report?.history_source === 'synthetic'">
   <el-alert title="以下正确率、错题和薄弱点均为模拟历史，不是实际测验成绩，也不参与真实画像计算。" type="warning" :closable="false" class="alert-space" />
   <h3>分章节模拟历史</h3>
   <article v-for="chapter in report.chapter_history" :key="chapter.title" class="knowledge-card"><h3>{{ chapter.title }}</h3><el-progress :percentage="chapter.accuracy" /><p>模拟正确率 {{ chapter.accuracy }}%</p><h4>模拟错题</h4><p v-for="(wrong, i) in chapter.wrong_questions" :key="i">{{ wrong.stem }}<br /><span class="muted">模拟作答：{{ wrong.answer }} · {{ wrong.knowledge_point }}</span></p><h4>模拟薄弱点</h4><p v-for="weak in chapter.weak_knowledge_points" :key="weak.name"><strong>{{ weak.name }}</strong>：{{ weak.learning_gap }}。建议练习：{{ weak.practice }}。</p></article>
  </template>
  <ReportPanels v-else-if="report" :report="report"><template #resource="{ item }"><RouterLink v-if="item.resource_id" :to="{ path: `/courses/${courseId}/learn`, query: { resource: item.resource_id } }"><el-button text>前往学习</el-button></RouterLink></template></ReportPanels>
  <el-empty v-else description="暂无可展示的学习报告" />
 </section>
 <section v-if="preview || report?.history_source === 'synthetic'" class="panel followup-panel"><h2>模拟历史学习助手</h2><p class="muted">此演示助手结合相关模拟历史提问，不使用或更新上方真实画像。真实诊断追问可在课程小练习中进行。</p><el-input v-model="message" type="textarea" :rows="3" maxlength="2000" aria-label="学习提问" /><el-button type="primary" :loading="busy" :disabled="!report || !message.trim()" @click="followup">发送问题</el-button><p v-if="replyContext" class="muted">{{ replyContext }}</p><p aria-live="polite">{{ reply }}</p></section>
</template>
