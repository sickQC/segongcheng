export type Mode = 'live' | 'demo'
export interface Question { id: string; title: string; text: string; sample_answer: string; source: string; model_configured: boolean; demo_enabled: boolean }
export interface Output { status: string; knowledge_point_id: string; mastery: number | null; confidence: number; problem_type: string; problem_description: string; evidence_event_ids: string[]; recommendation: string; followup_question: string; citations: unknown[] }
export interface Diagnosis { id: string; event_id: string; mode: Mode; status: string; output: Output | null; error_code: string | null; error_message: string | null; created_at: string }
export interface Trace { trace_id: string; source: string; model: string; prompt_version: string; latency_ms: number | null; usage: Record<string, number> | null; status: string; error_code: string | null }
export interface Detail extends Diagnosis { event: { event_id: string; actor: string; verb: string; result: { answer: string }; [key: string]: unknown }; traces: Trace[] }

export async function request<T>(path: string, body?: unknown): Promise<T> {
  const response = await fetch(path, {
    method: body === undefined ? 'GET' : 'POST',
    headers: body === undefined ? {} : { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
    signal: AbortSignal.timeout(15000),
  })
  const data = await response.json()
  if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : '请求参数不正确，请检查输入。')
  return data as T
}
export const statusText = (status: string) => ({ pending: '诊断处理中', supported: '诊断可查看', insufficient: '证据不足', failed: '诊断未完成' }[status] ?? status)
export const dateText = (value: string) => new Date(value).toLocaleString('zh-CN', { hour12: false })
