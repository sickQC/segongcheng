<script setup lang="ts">
defineProps<{ modelValue?: number; disabled?: boolean }>()
const emit = defineEmits<{ 'update:modelValue': [value: number | undefined] }>()
function update(event: Event) {
  const input = event.target as HTMLInputElement
  emit('update:modelValue', input.value === '' || !Number.isFinite(input.valueAsNumber) ? undefined : input.valueAsNumber)
}
</script>

<template>
  <input class="minute-input" type="number" min="1" max="240" step="1" :value="modelValue ?? ''" :disabled="disabled" :aria-disabled="Boolean(disabled)" @input="update" @change="update" />
</template>

<style scoped>
.minute-input { width: 110px; padding: 8px 11px; border: 1px solid var(--el-border-color); border-radius: var(--el-border-radius-base); background: var(--el-fill-color-blank); color: var(--el-text-color-regular); font: inherit; }
.minute-input:focus { outline: 2px solid var(--el-color-primary); outline-offset: 1px; }
.minute-input:disabled { background: var(--el-disabled-bg-color); color: var(--el-disabled-text-color); cursor: not-allowed; }
</style>
