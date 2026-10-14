export interface User { id: string; username: string; display_name: string; role: 'teacher' | 'student' }
export interface Course { id: string; title: string; description: string; teacher_id: string }
export type Bloom = 'remember' | 'understand' | 'apply' | 'analyze' | 'evaluate' | 'create'
export interface KnowledgePoint { id: string; code: string; chapter_id: string; name: string; definition: string; difficulty: number; bloom_level: Bloom; resource_ids: string[]; question_ids: string[] }
export interface Chapter { id: string; course_id: string; title: string; sort_order: number; knowledge_points: KnowledgePoint[] }
export interface Outline { course: Course; chapters: Chapter[] }
export interface Auth { user: User; csrf_token: string; expires_at: string; courses: Course[] }
export interface Page<T> { items: T[]; total: number; page: number; page_size: number }
export interface Member { user: User; role: string }
export const bloomLabels: Record<Bloom, string> = { remember: '记忆', understand: '理解', apply: '应用', analyze: '分析', evaluate: '评价', create: '创造' }
