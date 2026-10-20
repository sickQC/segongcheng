import MarkdownIt from 'markdown-it'

// Escape raw HTML and keep the parser's default unsafe-link validation enabled.
const renderer = new MarkdownIt({ html: false, linkify: false, breaks: false })
const defaultLink = renderer.renderer.rules.link_open
renderer.renderer.rules.link_open = (tokens, index, options, env, self) => {
  tokens[index].attrSet('target', '_blank')
  tokens[index].attrSet('rel', 'noopener noreferrer')
  return defaultLink ? defaultLink(tokens, index, options, env, self) : self.renderToken(tokens, index, options)
}

export interface LectureHeading { id: string; title: string; level: number; section: string }
export function renderMarkdown(markdown: string): string { return renderer.render(markdown) }

export function lectureDocument(markdown: string, documentTitle: string) {
  const tokens = renderer.parse(markdown, {})
  const headings: LectureHeading[] = []
  let path: string[] = []
  for (let i = 0; i < tokens.length; i++) {
    const token = tokens[i]
    if (token.type !== 'heading_open') continue
    const title = tokens[i + 1]?.content.trim() ?? ''
    const level = Number(token.tag.slice(1))
    path = path.slice(0, level - 1)
    while (path.length < level - 1) path.push('')
    path.push(title)
    const sectionPath = path.filter(Boolean)
    if (normalize(sectionPath[0] ?? '') === normalize(documentTitle)) sectionPath.shift()
    const id = `lecture-section-${headings.length + 1}`
    token.attrSet('id', id)
    token.attrSet('tabindex', '-1')
    headings.push({ id, title, level, section: [documentTitle, ...sectionPath].join(' > ') })
  }
  return { html: renderer.renderer.render(tokens, renderer.options, {}), headings }
}

function normalize(value: string) { return value.normalize('NFKC').replace(/\s+/g, '').toLowerCase() }
export function findLectureHeading(headings: LectureHeading[], section: string) {
  if (!section) return undefined
  return headings.find(heading => normalize(heading.section) === normalize(section))
    ?? headings.find(heading => normalize(heading.title) === normalize(section.split('>').at(-1) ?? ''))
}
