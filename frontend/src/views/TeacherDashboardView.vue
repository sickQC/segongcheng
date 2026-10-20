<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import WorkspaceHeader from '../components/WorkspaceHeader.vue'
import EventExportPanel from '../components/EventExportPanel.vue'
import { useWorkspace } from '../composables/useWorkspace'
import { workspaceApi } from '../api/workspace'
import * as sample from '../api/preview'
import { errorMessage } from '../api/client'
import type { Dashboard, TeacherStudentReport } from '../types/workspace'

const { courseId, preview, loading, error, run } = useWorkspace()
const data = ref<Dashboard>(), detail = ref<TeacherStudentReport>()
const days = ref(30), includeDemo = ref(false), onlyAttention = ref(false), search = ref('')
const drawer = ref(false), detailBusy = ref(false), detailError = ref(''), notice = ref('')
const selectedPoint = ref(''), triggerBusy = ref(false)
const visibleStudents = computed(() => (data.value?.students ?? []).filter(row =>
  (!onlyAttention.value || row.attention_reasons.length > 0) &&
  (!search.value.trim() || `${row.name} ${row.username}`.toLowerCase().includes(search.value.trim().toLowerCase()))
))
const rate = (correct: number, total: number, percent: number | null) =>
  percent === null ? '暂无证据' : `${correct}/${total} 题 · ${percent}%`

function load() {
  data.value = undefined; drawer.value = false; detail.value = undefined
  void run(
    () => preview.value ? Promise.resolve(sample.dashboard) : workspaceApi.dashboard(courseId.value, days.value, includeDemo.value),
    value => { data.value = value; selectedPoint.value = value.points[0]?.knowledge_point_id ?? '' },
  )
}
watch([preview, days, includeDemo, courseId], load, { immediate: true })

async function openStudent(id: string) {
  drawer.value = true; detail.value = undefined; detailBusy.value = true; detailError.value = ''; notice.value = ''
  try {
    detail.value = preview.value ? sample.teacherStudent : await workspaceApi.student(courseId.value, id, days.value, includeDemo.value)
  } catch (e) { detailError.value = errorMessage(e) }
  finally { detailBusy.value = false }
}
async function refreshStudent() { if (detail.value) await openStudent(detail.value.student_id) }
async function diagnose() {
  if (!detail.value || !selectedPoint.value || preview.value) return
  triggerBusy.value = true; detailError.value = ''; notice.value = ''
  try {
    const job = await workspaceApi.diagnose(courseId.value, detail.value.student_id, [selectedPoint.value], days.value)
    notice.value = `综合诊断已受理（${job.status}），可稍后刷新学生详情。`
    detail.value = await workspaceApi.student(courseId.value, detail.value.student_id, days.value, includeDemo.value)
  } catch (e) { detailError.value = errorMessage(e) }
  finally { triggerBusy.value = false }
}
</script>

<template>
  <WorkspaceHeader :course-id="courseId" title="教师学情看板" v-model:preview="preview" :loading="loading || detailBusy || triggerBusy" :error="error" @reload="load" />
  <section class="panel">
    <div class="toolbar">
      <span>统计范围</span>
      <el-select v-model="days" aria-label="统计范围" style="width: 130px"><el-option :value="7" label="近 7 天" /><el-option :value="30" label="近 30 天" /><el-option :value="90" label="近 90 天" /></el-select>
      <el-switch v-model="includeDemo" aria-label="包含模拟数据" active-text="包含模拟数据" />
    </div>
    <p class="muted">正确率仅来自已判分的测验题；练习诊断是学习参考，不参与成绩。无作答时显示“暂无证据”。</p>
    <el-alert v-if="preview" title="当前是界面预览，所有数字均为样例" type="warning" :closable="false" />
    <el-alert v-else-if="data?.simulated_record_count" :title="`当前统计包含 ${data.simulated_record_count} 条模拟作答，仅供演示`" type="warning" :closable="false" />
  </section>
  <div v-loading="loading">
    <el-empty v-if="!data" description="暂无学情统计" />
    <template v-else>
      <div class="metric-grid">
        <section class="panel"><p>课程学生</p><strong class="metric-value">{{ data.student_count }}</strong></section>
        <section class="panel"><p>近 {{ data.days }} 天有提交</p><strong class="metric-value">{{ data.active_count }}</strong></section>
        <section class="panel"><p>测验 / 小练习提交</p><strong class="metric-value">{{ data.quiz_count }} / {{ data.practice_count }}</strong></section>
        <section class="panel"><p>测验平均得分率</p><strong class="metric-value">{{ data.average_quiz_percent === null ? '暂无证据' : `${data.average_quiz_percent}%` }}</strong></section>
      </div>
      <section class="panel">
        <h2>章节表现</h2>
        <el-table :data="data.chapters" empty-text="课程尚无章节">
          <el-table-column prop="name" label="章节" />
          <el-table-column label="测验正确率"><template #default="scope">{{ rate(scope.row.correct_count, scope.row.question_count, scope.row.accuracy_percent) }}</template></el-table-column>
        </el-table>
      </section>
      <section class="panel">
        <h2>知识点作答情况</h2>
        <el-table :data="data.points" empty-text="课程尚无知识点">
          <el-table-column prop="chapter" label="章节" min-width="160" />
          <el-table-column prop="name" label="知识点" min-width="180" />
          <el-table-column label="已判分测验题"><template #default="scope">{{ rate(scope.row.correct_count, scope.row.question_count, scope.row.accuracy_percent) }}</template></el-table-column>
        </el-table>
      </section>
      <section class="panel">
        <div class="toolbar"><h2>学生画像</h2><el-input v-model="search" placeholder="搜索学生" aria-label="搜索学生" clearable style="width: 190px" /><el-switch v-model="onlyAttention" active-text="只看待关注" /></div>
        <p class="muted">“待关注”依据未提交、测验错误和诊断状态提示，由教师查看原始证据后判断。</p>
        <el-table :data="visibleStudents" empty-text="没有符合条件的学生">
          <el-table-column label="学生" min-width="140"><template #default="scope"><el-button text type="primary" @click="openStudent(scope.row.id)">{{ scope.row.name }}</el-button></template></el-table-column>
          <el-table-column label="测验" min-width="100"><template #default="scope">{{ scope.row.quiz_count }} 次</template></el-table-column>
          <el-table-column label="练习" min-width="100"><template #default="scope">{{ scope.row.practice_count }} 次</template></el-table-column>
          <el-table-column label="正确率" min-width="150"><template #default="scope">{{ rate(scope.row.correct_count, scope.row.question_count, scope.row.accuracy_percent) }}</template></el-table-column>
          <el-table-column label="教师提醒" min-width="190"><template #default="scope">{{ scope.row.attention_reasons.join('；') || '暂无' }}</template></el-table-column>
          <el-table-column label="数据来源" min-width="110"><template #default="scope"><el-tag v-if="scope.row.simulated_record_count" type="warning">含模拟记录</el-tag><span v-else>真实/暂无</span></template></el-table-column>
        </el-table>
      </section>
    </template>
  </div>
  <el-drawer v-model="drawer" :title="`${detail?.name ?? '学生'} · 学习详情`" size="min(760px, 96vw)">
    <div v-loading="detailBusy">
      <el-alert v-if="detailError" :title="detailError" type="error" :closable="false" />
      <el-alert v-if="notice" :title="notice" type="success" :closable="false" />
      <template v-if="detail">
        <EventExportPanel v-if="!preview" :key="`${courseId}:${detail.student_id}`" :course-id="courseId" :student-id="detail.student_id" :points="detail.points" />
        <el-alert v-if="detail.simulated_record_count" :title="`下方包含 ${detail.simulated_record_count} 条模拟记录`" type="warning" :closable="false" />
        <p>近 {{ detail.days }} 天测验正确率：<strong>{{ rate(detail.correct_count, detail.question_count, detail.accuracy_percent) }}</strong></p>
        <p>教师提醒：{{ detail.attention_reasons.join('；') || '暂无' }}</p>
        <h3>章节表现</h3>
        <el-table :data="detail.chapters" empty-text="暂无章节"><el-table-column prop="name" label="章节" /><el-table-column label="测验正确率"><template #default="scope">{{ rate(scope.row.correct_count, scope.row.question_count, scope.row.accuracy_percent) }}</template></el-table-column></el-table>
        <h3>知识点证据</h3>
        <el-table :data="detail.points" empty-text="暂无知识点"><el-table-column prop="name" label="知识点" /><el-table-column label="测验正确率"><template #default="scope">{{ rate(scope.row.correct_count, scope.row.question_count, scope.row.accuracy_percent) }}</template></el-table-column></el-table>
        <h3>最近作答与建议</h3>
        <el-empty v-if="!detail.activities.length" description="当前范围内暂无作答" :image-size="55" />
        <article v-for="item in detail.activities" :key="item.evidence_id ?? item.at" class="knowledge-card">
          <div class="panel-meta"><strong>{{ item.kind === 'quiz' ? '测验' : '小练习' }} · {{ item.title }}</strong><el-tag v-if="item.simulated" type="warning">模拟</el-tag></div>
          <p class="muted">{{ new Date(item.at).toLocaleString() }} · 证据 {{ item.evidence_id }}</p>
          <p v-if="item.score_percent !== null">得分率 {{ item.score_percent }}%</p>
          <p v-if="item.answer"><strong>原答案：</strong><span class="answer-preview">{{ item.answer }}</span></p>
          <p v-if="item.diagnosis"><strong>诊断：</strong>{{ item.diagnosis }}</p>
          <p v-if="item.recommendation"><strong>建议：</strong>{{ item.recommendation }}</p>
        </article>
        <h3>最近错题</h3>
        <el-empty v-if="!detail.mistakes.length" description="当前范围内没有错题记录" :image-size="55" />
        <article v-for="item in detail.mistakes" :key="item.evidence_id ?? item.question" class="knowledge-card"><div class="panel-meta"><strong>{{ item.question }}</strong><el-tag v-if="item.simulated" type="warning">模拟</el-tag></div><p>学生作答：{{ item.original_answer }}</p><p>解析：{{ item.explanation }}</p><p class="muted">证据：{{ item.evidence_id || '无对应事件' }}</p></article>
        <h3>综合诊断</h3>
        <p v-if="detail.latest_report">最近报告：{{ detail.latest_report.status }} · {{ new Date(detail.latest_report.created_at).toLocaleString() }}</p>
        <p v-else class="muted">暂无综合诊断报告。</p>
        <article v-for="point in detail.latest_report?.points ?? []" :key="point.knowledge_point_id" class="knowledge-card"><p>{{ point.explanation }}</p><p>建议：{{ point.recommendation }}</p><p class="muted">证据：{{ point.evidence_event_ids.join('、') || '不足' }}</p></article>
        <div class="practice-actions"><el-select v-model="selectedPoint" aria-label="选择诊断知识点" style="width: 220px"><el-option v-for="point in data?.points ?? []" :key="point.knowledge_point_id" :label="point.name" :value="point.knowledge_point_id" /></el-select><el-button type="primary" :disabled="preview || !selectedPoint" :loading="triggerBusy" @click="diagnose">生成综合诊断</el-button><el-button @click="refreshStudent">刷新详情</el-button></div>
        <p class="muted">综合诊断由真实学习记录生成；模拟记录不会作为正式诊断证据。</p>
      </template>
    </div>
  </el-drawer>
</template>
