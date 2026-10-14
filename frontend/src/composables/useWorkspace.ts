import { computed, ref } from 'vue'
import { useRoute } from 'vue-router'
import { errorMessage } from '../api/client'
export function useWorkspace() {
 const route = useRoute(), preview = ref(false), loading = ref(false), error = ref('')
 const courseId = computed(() => String(route.params.id))
 let version = 0
 async function run<T>(fetcher: () => Promise<T>, accept: (data: T) => void) {
  const current = ++version; loading.value = true; error.value = ''
  try { const data = await fetcher(); if (current === version) accept(data) }
  catch (e) { if (current === version) error.value = errorMessage(e) }
  finally { if (current === version) loading.value = false }
 }
 return { courseId, preview, loading, error, run }
}
