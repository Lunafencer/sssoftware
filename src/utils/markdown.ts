/**
 * Markdown 渲染（FIX3 第 3.1 项 + FIX5 第 18 项）
 * - 关闭 html 解析（防 XSS）
 * - 关闭 linkify（避免误识别）
 * - 链接自动加 target="_blank"，仅允许 https / # / mailto
 * - FIX5 第 18 项：渲染结果再走一次 DOMPurify allowlist，
 *   即便上游 markdown-it 配置被误改也无法注入脚本。
 */
import MarkdownIt from 'markdown-it'
import DOMPurify from 'dompurify'

const md = new MarkdownIt({
  html: false,
  linkify: false,
  breaks: true,
  typographer: false
})

// 链接安全：仅放行 https / # / mailto / 站内 hash 路由
const SAFE_PROTO = /^(https?:|mailto:|#|\/)/i
const defaultRender = md.renderer.rules.link_open || function (tokens, idx, options, _env, self) {
  return self.renderToken(tokens, idx, options)
}
md.renderer.rules.link_open = function (tokens, idx, options, env, self) {
  const tok = tokens[idx]
  const hrefIndex = tok.attrIndex('href')
  if (hrefIndex >= 0) {
    const href = tok.attrs![hrefIndex][1] || ''
    if (!SAFE_PROTO.test(href)) {
      tok.attrs![hrefIndex][1] = '#'
    }
  }
  const targetIdx = tok.attrIndex('target')
  if (targetIdx < 0) tok.attrPush(['target', '_blank'])
  else tok.attrs![targetIdx][1] = '_blank'
  const relIdx = tok.attrIndex('rel')
  if (relIdx < 0) tok.attrPush(['rel', 'noopener noreferrer'])
  return defaultRender(tokens, idx, options, env, self)
}

// FIX5 第 18 项：DOMPurify 白名单，覆盖 markdown 常用标签 + 我们渲染时强加的 target/rel
const PURIFY_CFG = {
  ALLOWED_TAGS: [
    'p', 'br', 'hr',
    'strong', 'b', 'em', 'i', 'u', 's', 'del', 'mark', 'code', 'pre', 'blockquote',
    'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
    'ul', 'ol', 'li',
    'a', 'img',
    'table', 'thead', 'tbody', 'tr', 'th', 'td',
    'span', 'div'
  ],
  ALLOWED_ATTR: ['href', 'title', 'target', 'rel', 'src', 'alt', 'width', 'height', 'class', 'colspan', 'rowspan', 'align'],
  ALLOWED_URI_REGEXP: /^(?:https?:|mailto:|#|\/)/i,
  ALLOW_DATA_ATTR: false,
  FORBID_TAGS: ['script', 'style', 'iframe', 'object', 'embed', 'form', 'input', 'button', 'svg', 'math'],
  FORBID_ATTR: ['onerror', 'onload', 'onclick', 'onmouseover', 'onfocus', 'onblur', 'onchange', 'onsubmit', 'style']
}

export const renderMarkdown = (src: string): string => {
  if (!src) return ''
  let html = ''
  try {
    html = md.render(src)
  } catch {
    html = md.utils.escapeHtml(src)
  }
  return DOMPurify.sanitize(html, PURIFY_CFG) as unknown as string
}
