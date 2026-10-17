// Only imported for explicit UI preview. Never persisted or used as an error fallback.
import type { Resource, Quiz, Attempt, Report, Dashboard, TeacherStudentReport } from '../types/workspace'
export const resources: Resource[] = [
 { id: 'preview-video', title: '需求分析入门 · 视频布局样例', type: 'video', url: null, description: '此处显示视频播放器、播放速度和学习进度。未加载真实媒体。', knowledge_point_ids: ['preview-kp'] },
 { id: 'preview-doc', title: '需求规格说明 · 文档布局样例', type: 'doc', url: null, description: '此处显示文档预览和引用页码。未加载真实文件。', knowledge_point_ids: ['preview-kp'] },
]
export const quizzes: Quiz[] = [{ id: 'preview-quiz', title: '需求分析自测（界面样例）', duration_minutes: 20, attempts_remaining: 2 }]
export const attempt: Attempt = { id: 'preview-attempt', quiz_id: 'preview-quiz', expires_at: '', questions: [
 { id: 'q1', type: 'single', stem: '哪一项属于功能需求？', options: ['用户可以导出报告', '响应时间小于两秒', '系统可用率达到目标'], points: 25 },
 { id: 'q2', type: 'multiple', stem: '哪些活动有助于澄清需求？', options: ['访谈', '原型评审', '忽略反馈'], points: 25 },
 { id: 'q3', type: 'boolean', stem: '需求变更应该经过评估。', options: ['正确', '错误'], points: 25 },
 { id: 'q4', type: 'fill', stem: '用来描述用户与系统交互的模型称为____模型。', options: [], points: 25 },
] }
export const report: Report = {
 diagnosis: [{ knowledge_point: '需求分类', mastery: 65, confidence: 80, issue: '概念边界需要巩固（示例）', evidence_ids: ['preview-answer-1', 'preview-event-2'] }],
 profile: [{ label: '知识掌握', value: 65 }, { label: '学习投入', value: 80 }, { label: '视频偏好', value: 70 }, { label: '学习风险', value: 30 }],
 recommendations: [{ title: '复习需求分类', reason: '先巩固先修知识，再完成针对性练习（示例）', minutes: 15, resource_id: 'preview-doc' }],
 records: [{ title: '需求分析自测', score: 75, at: '2026-10-14T08:00:00Z' }],
 mistakes: [{ stem: '功能需求与质量要求有何区别？', explanation: '功能需求描述系统行为，质量要求描述质量约束。（示例）' }],
 timeline: [{ at: '2026-10-14T07:30:00Z', description: '观看需求分析视频（示例事件）' }],
}
export const dashboard: Dashboard = {
 days: 30, include_demo: true, student_count: 2, active_count: 2, quiz_count: 2, practice_count: 1,
 average_quiz_percent: 75, simulated_record_count: 3,
 chapters: [{ chapter_id: 'preview-chapter', name: '第一章 需求工程', correct_count: 3, question_count: 4, accuracy_percent: 75 }],
 points: [{ knowledge_point_id: 'preview-kp', name: '需求分类', chapter: '第一章 需求工程', correct_count: 3, question_count: 4, accuracy_percent: 75 }],
 students: [
  { id: 'preview-student-1', name: '样例学生甲', username: 'preview-a', quiz_count: 1, practice_count: 1, correct_count: 1, question_count: 2, accuracy_percent: 50, attention_reasons: ['该知识点需复习'], last_activity_at: '2026-10-14T08:00:00Z', simulated_record_count: 2 },
  { id: 'preview-student-2', name: '样例学生乙', username: 'preview-b', quiz_count: 1, practice_count: 0, correct_count: 2, question_count: 2, accuracy_percent: 100, attention_reasons: [], last_activity_at: '2026-10-14T08:00:00Z', simulated_record_count: 1 },
 ],
}
export const teacherStudent: TeacherStudentReport = {
 student_id: 'preview-student-1', name: '样例学生甲', username: 'preview-a', days: 30,
 correct_count: 1, question_count: 2, accuracy_percent: 50, chapters: dashboard.chapters, points: dashboard.points,
 activities: [{ kind: 'practice', title: '请解释功能需求与非功能需求', at: '2026-10-14T08:00:00Z', simulated: true, score_percent: null, answer: '两者都是功能。', diagnosis: '混淆了行为与质量约束。', recommendation: '分别写出一个功能与一个性能要求。', evidence_id: 'preview-event' }],
 mistakes: [{ question: '功能需求描述什么？', original_answer: '系统运行速度', explanation: '功能需求描述系统提供的行为。', at: '2026-10-14T08:00:00Z', simulated: true, evidence_id: 'preview-event-2' }],
 attention_reasons: ['该知识点需复习'], simulated_record_count: 1, latest_report: null,
}
