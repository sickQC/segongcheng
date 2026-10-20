export interface Prerequisite { id: string; course_id: string; from_kp_id: string; to_kp_id: string }
export interface PathPoint {
 knowledge_point_id: string; code: string; name: string; mastery: number | null; confidence: number | null;
 diagnosis_id: string | null; evidence_ids: string[]; input_cutoff: string | null; reason: string;
 reason_source: 'diagnosis' | 'prerequisite_rule';
}
export interface PathStep extends PathPoint {
 estimated_minutes?: number | null; estimate_source?: 'teacher' | 'rule_estimate' | null;
 priority_score?: number | null; deferral_reason?: string | null;
 order: number; prerequisite_ids: string[];
 actions: { kind: 'knowledge' | 'practice'; id: string; title: string; url: string }[]; notes: string[];
}
export interface LearningPath {
 id: string; course_id: string; student_id: string; created_at: string; strategy: 'baseline' | 'budgeted';
 time_budget_minutes?: number | null; estimated_minutes?: number | null; full_path_estimated_minutes?: number | null;
 remaining_estimated_minutes?: number | null; remaining_steps?: PathStep[]; goal_in_plan?: boolean | null;
 scheduling_rule?: string | null;
 algorithm_version: string; mastery_threshold: number; target_kp_id: string; target_name: string;
 status: 'ready' | 'target_mastered'; input_cutoff: string;
 graph_edges: { from_kp_id: string; to_kp_id: string }[]; steps: PathStep[]; skipped: PathPoint[]; notes: string[];
}
export interface PathFeedback { recommendation_id: string; student_id: string; choice: 'accepted' | 'declined'; created_at: string }
export interface StrategyMetrics { strategy: 'baseline' | 'budgeted'; recommendation_count: number; feedback_count: number; accepted_count: number; acceptance_rate: number | null; estimated_path_count: number; average_estimated_minutes: number | null; goal_in_plan_count: number }
export interface RecommendationMetrics { scope: 'student' | 'course'; strategies: StrategyMetrics[]; explanation: string }
