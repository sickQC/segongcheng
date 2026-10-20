import { strict as assert } from 'node:assert'
import { test } from 'node:test'
import { lectureDocument, findLectureHeading, renderMarkdown } from '../src/utils/markdown.ts'

test('renders course tables, lists and code instead of raw Markdown', () => {
  const html = renderMarkdown('## 标题\n\n**定义**\n\n- 条目\n\n| A | B |\n| --- | --- |\n| 1 | 2 |\n\n```js\nconst a = 1\n```')
  for (const tag of ['h2', 'strong', 'ul', 'table', 'pre']) assert.ok(html.includes(`<${tag}`))
})

test('raw HTML and unsafe links never execute in rendered content', () => {
  const html = renderMarkdown('<script>alert(1)</script>\n\n<img src=x onerror=alert(2)>\n\n[危险](javascript:alert(3))\n\n[安全](https://example.com)')
  assert.ok(!html.includes('<script>'))
  assert.ok(!html.includes('<img '))
  assert.ok(!html.includes('href="javascript:'))
  assert.ok(html.includes('rel="noopener noreferrer"'))
})

test('citation breadcrumbs match nested headings and skip code block headings', () => {
  const document = lectureDocument('## 需求定义\n\n### 功能需求\n\n正文\n\n```md\n## 不应进入目录\n```\n\n## 其他章节', '讲义')
  assert.equal(document.headings.length, 3)
  const target = findLectureHeading(document.headings, '讲义 > 需求定义 > 功能需求')
  assert.equal(target?.title, '功能需求')
  assert.ok(document.html.includes(`id="${target?.id}"`))
  assert.equal(findLectureHeading(document.headings, '讲义 > 未知章节'), undefined)
})

test('document title is not duplicated in RAG citation headings', () => {
  const document = lectureDocument('# 讲义\n\n## 内容\n\n正文', '讲义')
  assert.equal(document.headings[1].section, '讲义 > 内容')
})
