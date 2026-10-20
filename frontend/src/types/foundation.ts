export interface User { id: string; username: string; display_name: string; role: 'teacher' | 'student' }
export interface Course { id: string; title: string; description: string; teacher_id: string }
export type Bloom = 'remember' | 'understand' | 'apply' | 'analyze' | 'evaluate' | 'create'
export interface KnowledgePoint { id: string; code: string; chapter_id: string; name: string; definition: string; difficulty: number; bloom_level: Bloom; resource_ids: string[]; question_ids: string[]; estimated_minutes: number | null }
export interface Chapter { id: string; course_id: string; title: string; sort_order: number; knowledge_points: KnowledgePoint[] }
export interface Outline { course: Course; chapters: Chapter[] }
export interface Auth { user: User; csrf_token: string; expires_at: string; courses: Course[] }
export interface Page<T> { items: T[]; total: number; page: number; page_size: number }
export interface Member { user: User; role: string }
export interface PracticeExercise { id: string; course_id: string; chapter_id: string; knowledge_point_id: string; question_text: string; created_at: string }
export interface PracticeDiagnosis { status: 'supported' | 'insufficient'; mastery: number | null; confidence: number; problem_type: string; problem_description: string; recommendation: string; followup_question: string; evidence_event_ids: string[]; knowledge_point_id: string }
export interface PracticeSubmission { id: string; exercise_id: string; course_id: string; student_id: string; original_answer: string; event_id: string; diagnosis_id: string; created_at: string; status: 'pending' | 'supported' | 'insufficient' | 'failed'; diagnosis: PracticeDiagnosis | null; error_message: string | null; needs_attention: boolean; synthetic: boolean }
export interface PracticeProgress { exercise_id: string; student_count: number; submitted_count: number; attention_count: number; students: { student_id: string; username: string; display_name: string; latest_submission: PracticeSubmission | null; needs_attention: boolean }[] }
export const bloomLabels: Record<Bloom, string> = { remember: '记忆', understand: '理解', apply: '应用', analyze: '分析', evaluate: '评价', create: '创造' }
