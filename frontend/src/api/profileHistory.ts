import { api } from './client'
import type { ProfileSnapshot, SnapshotPage, SnapshotComparison } from '../types/profileHistory'
const base = (course: string) => `/courses/${encodeURIComponent(course)}/profile/snapshots`
export const profileHistoryApi = {
 list: (course: string, offset = 0) => api<SnapshotPage>(`${base(course)}?offset=${offset}&limit=20`),
 save: (course: string, requestId: string) => api<ProfileSnapshot>(base(course), { method: 'POST', body: { request_id: requestId, days: 30 } }),
 detail: (course: string, id: string) => api<ProfileSnapshot>(`${base(course)}/${encodeURIComponent(id)}`),
 compare: (course: string, before: string, after: string) => api<SnapshotComparison>(`${base(course)}/compare?${new URLSearchParams({ before_id: before, after_id: after })}`),
}
