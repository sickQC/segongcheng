<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import { findLectureHeading, lectureDocument } from '../utils/markdown'
const props = defineProps<{ markdown: string; title: string; section?: string; jump?: number }>()
const reader = ref<HTMLElement>()
const document = computed(() => lectureDocument(props.markdown, props.title))
const activeHeading = ref('')
function jumpTo(id: string) {
  const heading = reader.value?.querySelector<HTMLElement>(`#${id}`)
  if (!heading || !reader.value) return
  reader.value.querySelector('.source-highlight')?.classList.remove('source-highlight')
  heading.classList.add('source-highlight')
  activeHeading.value = id
  reader.value.scrollTo({ top: reader.value.scrollTop + heading.getBoundingClientRect().top - reader.value.getBoundingClientRect().top - 18, behavior: 'smooth' })
  heading.focus({ preventScroll: true })
}
watch(() => [props.markdown, props.section, props.jump], async () => {
  activeHeading.value = ''
  await nextTick()
  const heading = findLectureHeading(document.value.headings, props.section ?? '')
  if (heading) jumpTo(heading.id)
}, { immediate: true })
function followAnchor(event: MouseEvent) {
  const anchor = (event.target as HTMLElement).closest('a')
  const href = anchor?.getAttribute('href')
  if (!href?.startsWith('#')) return
  event.preventDefault()
  let fragment: string
  try { fragment = decodeURIComponent(href.slice(1)) } catch { return }
  const heading = document.value.headings.find(item => item.id === fragment || item.title === fragment)
  if (heading) jumpTo(heading.id)
}
</script>
<template>
  <div class="lecture-reader">
    <details v-if="document.headings.length" class="lecture-toc">
      <summary>讲义目录（{{ document.headings.length }} 节）</summary>
      <nav aria-label="讲义章节目录"><button v-for="heading in document.headings" :key="heading.id" type="button" :class="{ selected: activeHeading === heading.id }" :style="{ paddingLeft: `${12 + Math.max(0, heading.level - 2) * 14}px` }" @click="jumpTo(heading.id)">{{ heading.title }}</button></nav>
    </details>
    <p v-if="section && activeHeading" class="lecture-location" role="status">已定位小节：{{ section }}</p>
    <article ref="reader" class="markdown-content lecture-body" aria-label="讲义原文" @click="followAnchor" v-html="document.html" />
  </div>
</template>
