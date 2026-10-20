<script setup lang="ts">
import type { Report } from '../types/workspace'
defineProps<{ report: Report }>()
</script>
<template><el-tabs>
 <el-tab-pane label="诊断与证据"><el-empty v-if="!report.diagnosis.length" description="暂无诊断" /><article v-for="item in report.diagnosis" :key="item.knowledge_point" class="knowledge-card"><h3>{{ item.knowledge_point }}</h3><p>{{ item.issue }}</p><el-progress :percentage="item.mastery" /><p>掌握度 {{ item.mastery }}% · 置信度 {{ item.confidence }}%</p><div class="tag-row"><el-tag v-for="id in item.evidence_ids" :key="id" type="info">证据 {{ id }}</el-tag></div></article></el-tab-pane>
 <el-tab-pane v-if="!report.learning_profile" label="学习画像"><el-empty v-if="!report.profile.length" description="暂无画像" /><div v-for="item in report.profile" :key="item.label" class="knowledge-card"><p>{{ item.label }}</p><el-progress :percentage="item.value" /></div></el-tab-pane>
 <el-tab-pane v-if="!report.learning_profile" label="推荐路径"><el-empty v-if="!report.recommendations.length" description="暂无推荐" /><article v-for="(item, index) in report.recommendations" :key="index" class="knowledge-card"><h3>{{ index + 1 }}. {{ item.title }}</h3><p>{{ item.reason }}</p><span>建议 {{ item.minutes }} 分钟</span><slot name="resource" :item="item" /></article></el-tab-pane>
 <el-tab-pane label="学习记录"><el-table :data="report.records" empty-text="暂无测验记录"><el-table-column prop="title" label="测验" /><el-table-column prop="score" label="得分" /><el-table-column prop="at" label="提交时间" /></el-table><el-timeline class="timeline-space"><el-timeline-item v-for="(event, i) in report.timeline" :key="i" :timestamp="event.at">{{ event.description }}</el-timeline-item></el-timeline></el-tab-pane>
 <el-tab-pane label="错题本"><el-empty v-if="!report.mistakes.length" description="暂无错题" /><article v-for="(item, i) in report.mistakes" :key="i" class="knowledge-card"><h3>{{ item.stem }}</h3><p>{{ item.explanation }}</p></article></el-tab-pane>
</el-tabs></template>
