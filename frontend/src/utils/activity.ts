// Display only meaningful activity fields; internal identifiers remain in API data.
export function activityLabel(source: unknown): string {
  return ({ assessment: '测验作答', practice: '知识点练习', learning_5e: '5E 学习对话',
    dialogue: '学习对话', behavior: '学习行为', learning_path: '学习计划', recommended: '生成学习计划', recommendation_feedback: '学习计划反馈', learning: '5E 学习对话', question: '课程答疑', chat: '课程答疑',
    resource: '资源学习', resource_tracker: '资源学习', answered: '作答',
    asked: '课程提问', responded: '学习回复', viewed: '阅读资料', watched: '观看视频',
  } as Record<string, string>)[String(source)] ?? '学习活动'
}

export function activityDetails(event: { object: Record<string, unknown>; result: Record<string, unknown> }) {
  const fields: [string, unknown][] = [
    ['知识点', event.object.knowledge_point_name], ['题目', event.object.question],
    ['学习内容', event.object.title], ['提问', event.result.question], ['作答', event.result.answer],
    ['计划反馈', event.result.choice === 'accepted' ? '愿意采用' : event.result.choice === 'declined' ? '暂不采用' : null],
    ['判分结果', typeof event.result.correct === 'boolean' ? (event.result.correct ? '正确' : '需要巩固') : null],
    ['推荐步骤数', event.result.step_count], ['预计分钟数', event.result.estimated_minutes], ['时间预算（分钟）', event.result.time_budget_minutes], ['得分', event.result.points], ['有效学习时长（秒）', event.result.effective_seconds],
  ]
  return fields.filter((entry): entry is [string, string | number] =>
    (typeof entry[1] === 'string' && entry[1].trim() !== '') || typeof entry[1] === 'number')
}

export function readableText(value: string | null | undefined, events: { event_id: string; source: string; timestamp: string }[] = []): string {
  return (value ?? '').replace(/\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b/gi, id => {
    const event = events.find(item => item.event_id.toLowerCase() === id.toLowerCase())
    return event ? `${activityLabel(event.source)}，${new Date(event.timestamp).toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai' })}` : '相关学习记录'
  })
}
