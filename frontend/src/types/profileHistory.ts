import type { LearningProfile } from './workspace'
export interface SnapshotSummary { id: string; reason: 'manual' | 'diagnosis'; report_id: string | null; days: number; created_at: string; rule_version: string; origin?: 'manual' | 'diagnosis' | 'backfill'; source_report_created_at?: string | null }
export interface ProfileSnapshot extends SnapshotSummary { profile: LearningProfile }
export interface SnapshotPage { items: SnapshotSummary[]; next_offset: number | null }
export interface MetricChange { before: number | null; after: number | null; delta: number | null }
export interface SnapshotComparison {
 before: SnapshotSummary; after: SnapshotSummary;
 points: { knowledge_point_id: string; name: string; mastery: MetricChange; accuracy: MetricChange }[];
 engagement: Record<string, MetricChange>; preference: Record<string, MetricChange>;
 risk_before: string; risk_after: string; warnings: string[];
}
