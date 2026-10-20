<script setup lang="ts">
import { onUnmounted, ref, watch } from 'vue'
import { ElMessageBox } from 'element-plus'
import { recommendationApi } from '../api/recommendation'
import { ApiError, errorMessage } from '../api/client'
import type { Prerequisite } from '../types/recommendation'

const props = defineProps<{ courseId: string; points: { id: string; code: string; name: string }[] }>()
const edges = ref<Prerequisite[]>([]), from = ref(''), to = ref(''), busy = ref(false), error = ref('')
let version = 0
const label = (id: string) => { const point = props.points.find(p => p.id === id); return point ? `${point.code} ${point.name}` : id }
function describe(e: unknown) {
 if (e instanceof ApiError && e.fields && typeof e.fields === 'object' && 'cycle' in e.fields) {
  const cycle = e.fields.cycle
  if (Array.isArray(cycle) && cycle.every(id => typeof id === 'string')) return `${e.message} ${cycle.map(label).join(' → ')}`
 }
 return errorMessage(e)
}
async function load() {
 const current = ++version; busy.value = true; error.value = ''
 try { const value = await recommendationApi.edges(props.courseId); if (current === version) edges.value = value }
 catch (e) { if (current === version) error.value = describe(e) }
 finally { if (current === version) busy.value = false }
}
async function add() {
 if (!from.value || !to.value || busy.value) return
 const current = version; busy.value = true; error.value = ''
 try { await recommendationApi.addEdge(props.courseId, from.value, to.value); if (current === version) await load() }
 catch (e) { if (current === version) error.value = describe(e) }
 finally { if (current === version) busy.value = false }
}
async function remove(edge: Prerequisite) {
 const current = version, course = props.courseId
 try { await ElMessageBox.confirm(`移除“${label(edge.from_kp_id)} → ${label(edge.to_kp_id)}”？历史推荐保留，新推荐按剩余关系计算。`, '移除先修关系') } catch { return }
 if (current !== version) return
 busy.value = true; error.value = ''
 try { await recommendationApi.removeEdge(course, edge.id); if (current === version) await load() }
 catch (e) { if (current === version) error.value = describe(e) }
 finally { if (current === version) busy.value = false }
}
watch([() => props.courseId, () => props.points.map(p => p.id).join(',')], () => { from.value = ''; to.value = ''; edges.value = []; void load() }, { immediate: true })
onUnmounted(() => { version++ })
</script>

<template>
 <section class="panel" aria-label="先修关系管理" v-loading="busy">
  <h2>先修关系</h2>
  <p>“A → B”表示先学习 A，再学习 B。这里只维护本课程的学习依赖，系统会拒绝环路。</p>
  <el-alert v-if="error" :title="error" type="error" :closable="false" />
  <el-form label-position="top" @submit.prevent="add">
   <el-form-item label="先学的知识点"><el-select v-model="from" filterable aria-label="先修知识点"><el-option v-for="p in points" :key="p.id" :label="label(p.id)" :value="p.id" :disabled="p.id === to" /></el-select></el-form-item>
   <el-form-item label="后学的知识点"><el-select v-model="to" filterable aria-label="后续知识点"><el-option v-for="p in points" :key="p.id" :label="label(p.id)" :value="p.id" :disabled="p.id === from" /></el-select></el-form-item>
   <el-button native-type="submit" type="primary" :disabled="!from || !to || busy">添加先修关系</el-button>
  </el-form>
  <el-table :data="edges" empty-text="尚未配置先修关系；系统不会从章节顺序推断依赖。"><el-table-column label="先学" min-width="170"><template #default="{ row }">{{ label(row.from_kp_id) }}</template></el-table-column><el-table-column label="后学" min-width="170"><template #default="{ row }">{{ label(row.to_kp_id) }}</template></el-table-column><el-table-column label="操作" width="90"><template #default="{ row }"><el-button text type="danger" :disabled="busy" @click="remove(row)">移除</el-button></template></el-table-column></el-table>
 </section>
</template>
