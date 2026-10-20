export type LectureLink = { resource_id: string; title: string; section: string }
export type LearningTopic = { knowledge_point_id: string; code: string; name: string; chapter_id: string; chapter_title: string; chapter_order: number; lectures: LectureLink[] }
