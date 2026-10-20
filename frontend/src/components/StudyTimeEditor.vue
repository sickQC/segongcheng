<script setup lang="ts">
import { onUnmounted, ref, watch } from 'vue'
import { recommendationApi } from '../api/recommendation'
import { errorMessage } from '../api/client'

const props = defineProps<{ courseId: string; points: { id: string; name: string; estimated_minutes?: number | null }[] }>()
const emit = defineEmits<{ changed: [] }>()
const selected = ref(''), minutes = ref<number | undefined>(15), busy = ref(false), error = ref(''), message = ref('')
let version = 0
watch(() => props.courseId, () => { version++; selected.value = ''; error.value = ''; message.value = ''; busy.value = false })
watch([selected, () => props.points.map(p => `${p.id}:${p.estimated_minutes}`).join(',')], () => {
 const point = props.points.find(p => p.id === selected.value)
 minutes.value = point?.estimated_minutes ?? 15
 message.value = point ? point.estimated_minutes == null ? '当前使用规则估时。' : `当前教师估时：${point.estimated_minutes}分钟。` : ''
})
async function save(reset = false) {
 if (!selected.value || busy.value || (!reset && (minutes.value == null || !Number.isInteger(minutes.value)))) return
 const current = version; busy.value = true; error.value = ''
 try { await recommendationApi.studyTime(props.courseId, selected.value, reset ? null : minutes.value!); if (current === version) { message.value = reset ? '已恢复规则估时。' : '教师估时已保存。'; emit('changed') } }
 catch (e) { if (current === version) error.value = errorMessage(e) }
 finally { if (current === version) busy.value = false }
}
onUnmounted(() => { version++ })
</script>

<template>
 <section class="panel" aria-label="推荐学习估时">
  <h2>推荐学习估时</h2><p>填写学习一个知识点及配套练习的预计分钟数。未填写时按难度使用规则估时；这些都是计划估计，不是学生真实耗时。</p>
  <el-alert v-if="error" :title="error" type="error" :closable="false" />
  <div class="toolbar"><el-select v-model="selected" placeholder="选择知识点" aria-label="估时知识点" :disabled="busy" style="width:min(320px,100%)"><el-option v-for="p in points" :key="p.id" :value="p.id" :label="p.name" /></el-select><el-input-number v-model="minutes" :min="1" :max="240" :precision="0" aria-label="教师预计分钟数" :disabled="busy" /><el-button :disabled="!selected || minutes == null || busy" @click="save()">保存估时</el-button><el-button :disabled="!selected || busy" @click="save(true)">恢复规则估时</el-button></div>
  <p class="muted" aria-live="polite">{{ message }}</p>
 </section>
</template>
