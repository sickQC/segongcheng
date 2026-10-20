import { ApiError } from './client'

export async function fetchEventExport(course: string, query: URLSearchParams, format: 'csv' | 'jsonl') {
 const params = new URLSearchParams(query); params.set('format', format)
 const response = await fetch(`/api/v1/courses/${encodeURIComponent(course)}/learning-events/export?${params}`, { credentials: 'same-origin', signal: AbortSignal.timeout(30000) })
 if (!response.ok) {
  if (response.status === 401) window.dispatchEvent(new Event('session-expired'))
  const body = await response.json().catch(() => null)
  throw new ApiError(body?.detail?.message ?? '导出失败，请缩小范围或重试', response.status, body?.detail?.code ?? 'EXPORT_ERROR')
 }
 return { blob: await response.blob(), filename: `learning-events.${format}`, count: Number(response.headers.get('X-Export-Event-Count') ?? 0) }
}

export function saveEventExport(blob: Blob, filename: string) {
 const url = URL.createObjectURL(blob), link = document.createElement('a')
 link.href = url; link.download = filename; document.body.appendChild(link); link.click(); link.remove()
 setTimeout(() => URL.revokeObjectURL(url), 1000)
}
