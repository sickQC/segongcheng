import { reactive, readonly } from 'vue'
import { api, ApiError, setCsrfToken } from '../api/client'
import type { Auth, User } from '../types/foundation'
const state = reactive({ user: null as User | null, ready: false, devEnabled: false })
let loading: Promise<void> | undefined
function accept(auth: Auth) { state.user = auth.user; state.ready = true; setCsrfToken(auth.csrf_token) }
export function clearSession() { state.user = null; state.ready = true; setCsrfToken('') }
export async function loadSession() {
  if (state.ready) return
  if (!loading) loading = (async () => {
    try { accept(await api<Auth>('/auth/me')) }
    catch (e) { if (e instanceof ApiError && e.status === 401) clearSession(); else throw e }
    finally { loading = undefined }
  })()
  return loading
}
export async function loadPublicConfig() {
  try {
    const r = await fetch('/api/config', { signal: AbortSignal.timeout(5000) })
    if (r.ok) state.devEnabled = (await r.json()).dev_routes_enabled === true
  } catch { state.devEnabled = false }
}
export async function login(username: string, password: string) {
  accept(await api<Auth>('/auth/login', { method: 'POST', body: { username, password } }))
}
export async function logout() {
  await api<void>('/auth/logout', { method: 'POST' }); clearSession()
}
export const session = readonly(state)
