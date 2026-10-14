<script setup lang="ts">
import { session } from '../composables/useSession'
defineProps<{ courseId: string; title: string; preview: boolean; loading: boolean; error: string }>()
defineEmits<{ 'update:preview': [value: boolean]; reload: [] }>()
</script>
<template>
 <div class="toolbar"><RouterLink :to="`/courses/${courseId}`">← 课程目录</RouterLink><el-switch :model-value="preview" :disabled="loading" active-text="界面预览（样例）" inactive-text="真实接口" @update:model-value="$emit('update:preview', Boolean($event))" /></div>
 <section class="page-heading"><span class="eyebrow">LEARNING WORKSPACE</span><h1>{{ title }}</h1></section>
 <nav class="work-nav"><RouterLink :to="`/courses/${courseId}/learn`">资源学习</RouterLink><RouterLink :to="`/courses/${courseId}/quiz`">课程测验</RouterLink><RouterLink :to="`/courses/${courseId}/report`">学习报告</RouterLink><RouterLink v-if="session.user?.role === 'teacher'" :to="`/teacher/courses/${courseId}/dashboard`">教师看板</RouterLink></nav>
 <el-alert v-if="preview" title="界面样例：所有内容仅供预览，不代表你的学习记录，不保存到数据库。切换模式将清空当前交互。" type="warning" :closable="false" class="alert-space" />
 <el-alert v-if="error" :title="error" type="info" :closable="false" class="alert-space"><el-button text @click="$emit('reload')">重新加载</el-button></el-alert>
</template>
