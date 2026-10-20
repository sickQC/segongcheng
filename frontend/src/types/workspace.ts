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
export interface Report { history_source?: 'synthetic' | 'real' | null; chapter_history?: ChapterHistory[]; learning_profile?: LearningProfile | null; diagnosis: DiagnosisItem[]; profile: { label: string; value: number }[]; recommendations: Recommendation[]; records: { title: string; score: number; at: string }[]; mistakes: { stem: string; explanation: string }[]; timeline: { at: string; description: string }[] }
export interface MasteryPoint { knowledge_point_id: string; name: string; mastery_percent: number | null; confidence_percent: number | null; report_id: string | null; evidence_ids: string[]; input_cutoff: string | null; updated_at: string | null; accuracy_percent: number | null; question_count: number }
export interface LearningProfile {
 student_id: string; course_id: string; rule_version: string; generated_at: string; window_start: string; window_end: string;
 knowledge: { known_points: number; total_points: number; points: MasteryPoint[]; explanation: string };
 engagement: { active_days: number; event_count: number; effective_seconds: number | null; observed_resource_count: number; completed_resource_percent: number | null; explanation: string };
 preference: { items: { key: string; label: string; count: number | null; percent: number | null }[]; explanation: string };
 risk: { level: 'unknown' | 'attention' | 'normal'; reasons: string[]; evidence_ids: string[]; explanation: string };
}
export interface LearningEvent { event_id: string; actor: string; verb: string; object: Record<string, unknown>; result: Record<string, unknown>; context: Record<string, unknown>; timestamp: string }
export interface EventPage { items: LearningEvent[]; next_offset: number | null; window_start: string; window_end: string }
export interface PointStat { knowledge_point_id: string; name: string; chapter: string; correct_count: number; question_count: number; accuracy_percent: number | null }
export interface ChapterStat { chapter_id: string; name: string; correct_count: number; question_count: number; accuracy_percent: number | null }
export interface DashboardStudent { id: string; name: string; username: string; quiz_count: number; practice_count: number; correct_count: number; question_count: number; accuracy_percent: number | null; attention_reasons: string[]; last_activity_at: string | null; simulated_record_count: number }
export interface Dashboard { days: number; include_demo: boolean; student_count: number; active_count: number; quiz_count: number; practice_count: number; average_quiz_percent: number | null; simulated_record_count: number; chapters: ChapterStat[]; points: PointStat[]; students: DashboardStudent[] }
export interface TeacherActivity { kind: 'quiz' | 'practice'; title: string; at: string; simulated: boolean; score_percent: number | null; answer: string | null; diagnosis: string | null; recommendation: string | null; evidence_id: string | null }
export interface TeacherMistake { question: string; original_answer: string; explanation: string; at: string; simulated: boolean; evidence_id: string | null }
export interface TeacherStudentReport { student_id: string; name: string; username: string; days: number; correct_count: number; question_count: number; accuracy_percent: number | null; chapters: ChapterStat[]; points: PointStat[]; activities: TeacherActivity[]; mistakes: TeacherMistake[]; attention_reasons: string[]; simulated_record_count: number; latest_report: { id: string; status: string; created_at: string; points: { knowledge_point_id: string; explanation: string; recommendation: string; evidence_event_ids: string[] }[] } | null }
