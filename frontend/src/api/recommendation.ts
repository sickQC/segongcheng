import { api } from './client'
import type { LearningPath, Prerequisite, PathFeedback, RecommendationMetrics } from '../types/recommendation'

const base = (id: string) => `/courses/${encodeURIComponent(id)}`
export const recommendationApi = {
 edges: (course: string) => api<Prerequisite[]>(`${base(course)}/prerequisites`),
 addEdge: (course: string, from: string, to: string) => api<Prerequisite>(`${base(course)}/prerequisites`, { method: 'POST', body: { from_kp_id: from, to_kp_id: to } }),
 removeEdge: (course: string, edge: string) => api(`${base(course)}/prerequisites/${encodeURIComponent(edge)}`, { method: 'DELETE' }),
 create: (course: string, target: string, requestId: string, strategy: 'baseline' | 'budgeted' = 'baseline', budget: number | null = null) => api<LearningPath>(`${base(course)}/recommendations`, { method: 'POST', body: { target_kp_id: target, strategy, time_budget_minutes: budget, request_id: requestId } }),
 studyTime: (course: string, point: string, minutes: number | null) => api(`${base(course)}/knowledge-points/${encodeURIComponent(point)}/study-time`, { method: 'PATCH', body: { estimated_minutes: minutes } }),
 feedback: (course: string, id: string) => api<PathFeedback | null>(`${base(course)}/recommendations/${encodeURIComponent(id)}/feedback`),
 saveFeedback: (course: string, id: string, choice: 'accepted' | 'declined') => api<PathFeedback>(`${base(course)}/recommendations/${encodeURIComponent(id)}/feedback`, { method: 'POST', body: { choice } }),
 metrics: (course: string) => api<RecommendationMetrics>(`${base(course)}/recommendation-metrics`),
 history: (course: string) => api<LearningPath[]>(`${base(course)}/recommendations`),
}
