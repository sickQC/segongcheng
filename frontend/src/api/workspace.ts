import { api } from './client'
import type { Resource, ChatReply, Quiz, Attempt, QuizResult, Report, Dashboard } from '../types/workspace'
const base = (id: string) => `/courses/${encodeURIComponent(id)}`
export const workspaceApi = {
 resources: (id: string) => api<Resource[]>(`${base(id)}/resources`),
 chat: (id: string, body: { resource_id: string; message: string; mode: 'rag' | '5e' }) => api<ChatReply>(`${base(id)}/chat`, { method: 'POST', body }),
 quizzes: (id: string) => api<Quiz[]>(`${base(id)}/quizzes`),
 start: (id: string, quiz_id: string) => api<Attempt>(`${base(id)}/attempts`, { method: 'POST', body: { quiz_id } }),
 submit: (id: string, attemptId: string, answers: { question_id: string; value: string[] }[]) => api<QuizResult>(`${base(id)}/attempts/${encodeURIComponent(attemptId)}/submit`, { method: 'POST', body: { answers } }),
 report: (id: string, algorithm = 'baseline') => api<Report>(`${base(id)}/report?algorithm=${algorithm}`),
 followup: (id: string, message: string) => api<ChatReply>(`${base(id)}/report/followup`, { method: 'POST', body: { message } }),
 dashboard: (id: string) => api<Dashboard>(`${base(id)}/dashboard`),
 student: (id: string, studentId: string) => api<Report>(`${base(id)}/students/${encodeURIComponent(studentId)}/report`),
 diagnose: (id: string, studentId: string) => api<{ job_id: string }>(`${base(id)}/students/${encodeURIComponent(studentId)}/diagnoses`, { method: 'POST' }),
}
