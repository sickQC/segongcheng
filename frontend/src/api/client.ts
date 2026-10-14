let csrfToken = ''
export function setCsrfToken(value: string) { csrfToken = value }
export class ApiError extends Error {
  constructor(message: string, public status: number, public code: string) { super(message) }
}
export async function api<T>(path: string, options: { method?: string; body?: unknown } = {}): Promise<T> {
  const method = options.method ?? 'GET'
  const headers: Record<string, string> = {}
  if (options.body !== undefined) headers['Content-Type'] = 'application/json'
  if (method !== 'GET' && csrfToken) headers['X-CSRF-Token'] = csrfToken
  const response = await fetch('/api/v1' + path, {
    method, headers, credentials: 'same-origin', signal: AbortSignal.timeout(15000),
    body: options.body === undefined ? undefined : JSON.stringify(options.body),
  })
  if (response.status === 204) return undefined as T
  const data = await response.json()
  if (!response.ok) {
    if (response.status === 401 && path !== '/auth/login') window.dispatchEvent(new Event('session-expired'))
    throw new ApiError(data.detail?.message ?? '请求失败，请稍后重试', response.status, data.detail?.code ?? 'HTTP_ERROR')
  }
  return data as T
}
export function errorMessage(error: unknown) {
  return error instanceof Error ? error.message : '操作失败，请稍后重试'
}
