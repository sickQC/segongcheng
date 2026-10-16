export interface Resource { id: string; title: string; type: 'video' | 'doc'; url: string | null; description: string; knowledge_point_ids: string[] }
export interface Citation {
  resource_id: string
  title: string
  page: number | null
  seconds: number | null
  /** 讲义类来源没有页码/时间点，用小节路径定位 */
  section?: string | null
}
export interface ChatReply { message: string; citations: Citation[]; phase: string | null }
export interface Question { id: string; type: 'single' | 'multiple' | 'boolean' | 'fill'; stem: string; options: string[]; points: number }
export interface Quiz { id: string; title: string; duration_minutes: number; attempts_remaining: number }
export interface Attempt { id: string; quiz_id: string; expires_at: string; questions: Question[] }
export interface QuizResult { score: number; total: number; answers: { question_id: string; correct: boolean; explanation: string }[] }
export interface DiagnosisItem { knowledge_point: string; mastery: number; confidence: number; issue: string; evidence_ids: string[] }
export interface Recommendation { title: string; reason: string; minutes: number; resource_id: string | null }
export interface Report { diagnosis: DiagnosisItem[]; profile: { label: string; value: number }[]; recommendations: Recommendation[]; records: { title: string; score: number; at: string }[]; mistakes: { stem: string; explanation: string }[]; timeline: { at: string; description: string }[] }
export interface Dashboard { student_count: number; active_count: number; completion: number; average_score: number; knowledge_points: string[]; students: { id: string; name: string; mastery: number[]; risk: string }[]; questions: { stem: string; correct_rate: number; average_seconds: number; option_counts: Record<string, number> }[]; score_distribution: { label: string; count: number }[] }
