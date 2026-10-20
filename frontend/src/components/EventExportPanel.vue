<script setup lang="ts">
import { onBeforeUnmount, ref, watch } from 'vue'
import { errorMessage } from '../api/client'
import { fetchEventExport, saveEventExport } from '../api/eventExport'
const props = defineProps<{ courseId: string; studentId?: string; points: { knowledge_point_id: string; name: string }[]; initialStart?: string; initialEnd?: string }>()
const range = ref<[Date, Date] | null>(null), point = ref(''), verb = ref(''), busy = ref(false), error = ref(''), notice = ref('')
let version = 0
function reset() {
 version++; busy.value = false; error.value = ''; notice.value = ''; point.value = ''; verb.value = ''
 const end = props.initialEnd ? new Date(props.initialEnd) : new Date()
 range.value = [props.initialStart ? new Date(props.initialStart) : new Date(end.getTime() - 30 * 86400000), end]
}
watch(() => [props.courseId, props.studentId, props.initialStart, props.initialEnd], reset, { immediate: true })
watch([range, point, verb], () => { version++; busy.value = false; error.value = ''; notice.value = '' })
onBeforeUnmount(() => { version++ })
async function download(format: 'csv' | 'jsonl') {
 const current = ++version
 error.value = ''; notice.value = ''
 if (!range.value || range.value.length !== 2) { error.value = '请选择起止时间'; return }
 const query = new URLSearchParams({ start: range.value[0].toISOString(), end: range.value[1].toISOString() })
 if (props.studentId) query.set('student_id', props.studentId)
 if (point.value) query.set('knowledge_point_id', point.value)
 if (verb.value.trim()) query.set('verb', verb.value.trim())
 busy.value = true
 try {
  const result = await fetchEventExport(props.courseId, query, format)
  if (current !== version) return
  saveEventExport(result.blob, result.filename)
  notice.value = `已请求下载 ${result.count} 条真实事件；请查看浏览器下载列表。`
 } catch (e) { if (current === version) error.value = errorMessage(e) }
 finally { if (current === version) busy.value = false }
}
</script>
<template>
 <section class="event-export">
  <h3>导出真实学习事件</h3>
  <p class="muted">使用下方独立筛选，导出全部匹配记录，不限于已加载列表。最多90天、5,000条、10MiB；不包含模拟记录。文件可能含作答原文，请妥善保存。</p>
  <el-date-picker v-model="range" type="datetimerange" start-placeholder="开始时间" end-placeholder="结束时间" style="max-width:100%" />
  <p class="muted">时间选择使用浏览器本地时区，导出时间统一为UTC。</p>
  <div class="toolbar">
   <el-select v-model="point" clearable placeholder="全部知识点" aria-label="导出知识点" style="width:220px"><el-option v-for="p in points" :key="p.knowledge_point_id" :label="p.name" :value="p.knowledge_point_id" /></el-select>
   <el-input v-model="verb" clearable maxlength="40" placeholder="动作，可留空，例如 answered" aria-label="导出动作" style="width:260px" />
   <el-button :loading="busy" @click="download('csv')">下载CSV</el-button><el-button :loading="busy" @click="download('jsonl')">下载JSONL</el-button>
  </div>
  <p class="muted">CSV供表格查看，危险公式前缀会做文本处理；程序分析建议使用保留原始结构的JSONL。</p>
  <el-alert v-if="error" :title="error" type="error" :closable="false" /><p v-if="notice" role="status">{{ notice }}</p>
 </section>
</template>
