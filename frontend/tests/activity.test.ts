import assert from 'node:assert/strict'
import test from 'node:test'
import { activityDetails, readableText } from '../src/utils/activity.ts'

test('活动详情保留零分和错误结果，排除内部标识与原始上下文', () => {
  const rows = activityDetails({ object: { id: 'internal', question: '需求如何分类？' }, result: { correct: false, points: 0, answer: '功能需求', event_id: 'internal' } })
  assert.deepEqual(rows, [['题目', '需求如何分类？'], ['作答', '功能需求'], ['判分结果', '需要巩固'], ['得分', 0]])
})
test('诊断正文的事件引用使用实际活动与时间，未知引用不泄露编码', () => {
  const id = '6f9730d1-f94b-4dc7-933a-556f707bc4f1'
  const text = readableText(`依据（${id}）判断`, [{ event_id: id, source: 'assessment', timestamp: '2026-10-22T06:00:00Z' }])
  assert.match(text, /测验作答/)
  assert.match(text, /14:00:00/)
  assert.ok(!text.includes(id))
  assert.equal(readableText(id), '相关学习记录')
  assert.equal(readableText('正确率 50%，2 道题'), '正确率 50%，2 道题')
})
