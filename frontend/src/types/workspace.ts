export interface Resource { id: string; title: string; type: 'video' | 'doc'; url: string | null; description: string; knowledge_point_ids: string[] }
export interface Citation { resource_id: string; title: string; page: number | null; seconds: number | null }
export interface ChatReply { message: string; citations: Citation[]; phase: string | null; personalization?: { source: 'synthetic'; matched_knowledge_points: string[]; similarity: number } | null }
export interface Question { id: string; type: 'single' | 'multiple' | 'boolean' | 'fill'; stem: string; options: string[]; points: number }
export interface Quiz { id: string; title: string; duration_minutes: number; attempts_remaining: number }
export interface Attempt { id: string; quiz_id: string; expires_at: string; questions: Question[] }
export interface QuizResult { score: number; total: number; answers: { question_id: string; correct: boolean; explanation: string }[] }
export interface DiagnosisItem { knowledge_point: string; mastery: number; confidence: number; issue: string; evidence_ids: string[] }
export interface Recommendation { title: string; reason: string; minutes: number; resource_id: string | null }
export interface ChapterHistory { title: string; accuracy: number; high_error: boolean; wrong_questions: { stem: string; answer: string; knowledge_point: string }[]; weak_knowledge_points: { name: string; learning_gap: string; practice: string }[] }
export interface Report { history_source?: 'synthetic' | 'real' | null; chapter_history?: ChapterHistory[]; diagnosis: DiagnosisItem[]; profile: { label: string; value: number }[]; recommendations: Recommendation[]; records: { title: string; score: number; at: string }[]; mistakes: { stem: string; explanation: string }[]; timeline: { at: string; description: string }[] }
export interface Dashboard { student_count: number; active_count: number; completion: number; average_score: number; knowledge_points: string[]; students: { id: string; name: string; mastery: number[]; risk: string }[]; questions: { stem: string; correct_rate: number; average_seconds: number; option_counts: Record<string, number> }[]; score_distribution: { label: string; count: number }[] }
