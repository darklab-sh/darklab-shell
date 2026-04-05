import { fromScript } from './helpers/extract.js'

const { escapeHtml, escapeRegex, renderMotd } = fromScript(
  'app/static/js/utils.js',
  'escapeHtml',
  'escapeRegex',
  'renderMotd',
)

// ── escapeHtml ────────────────────────────────────────────────────────────────

describe('escapeHtml', () => {
  it('leaves plain text unchanged', () => {
    expect(escapeHtml('hello world')).toBe('hello world')
  })

  it('escapes ampersand', () => {
    expect(escapeHtml('a&b')).toBe('a&amp;b')
  })

  it('escapes less-than', () => {
    expect(escapeHtml('<tag>')).toBe('&lt;tag&gt;')
  })

  it('escapes greater-than', () => {
    expect(escapeHtml('a>b')).toBe('a&gt;b')
  })

  it('escapes multiple entities in one string', () => {
    expect(escapeHtml('<script>alert("xss & stuff")</script>')).toBe(
      '&lt;script&gt;alert("xss &amp; stuff")&lt;/script&gt;',
    )
  })

  it('returns empty string unchanged', () => {
    expect(escapeHtml('')).toBe('')
  })
})

// ── escapeRegex ───────────────────────────────────────────────────────────────

describe('escapeRegex', () => {
  it('leaves plain text unchanged', () => {
    expect(escapeRegex('hello')).toBe('hello')
  })

  it('escapes dot', () => {
    expect(escapeRegex('.')).toBe('\\.')
  })

  it('escapes star', () => {
    expect(escapeRegex('a*b')).toBe('a\\*b')
  })

  it('escapes parentheses', () => {
    expect(escapeRegex('(a)')).toBe('\\(a\\)')
  })

  it('escapes square brackets', () => {
    expect(escapeRegex('[abc]')).toBe('\\[abc\\]')
  })

  it('escaped string matches literally when used in RegExp', () => {
    const raw = '1+1=2'
    const re = new RegExp(escapeRegex(raw))
    expect(re.test('1+1=2')).toBe(true)
    // Without escaping, + is a quantifier and would match '11=2'
    expect(new RegExp(raw).test('11=2')).toBe(true)
    expect(re.test('11=2')).toBe(false)
  })
})

// ── renderMotd ────────────────────────────────────────────────────────────────

describe('renderMotd', () => {
  it('leaves plain text unchanged', () => {
    expect(renderMotd('hello world')).toBe('hello world')
  })

  it('converts **text** to <strong>', () => {
    expect(renderMotd('**bold**')).toBe('<strong>bold</strong>')
  })

  it('converts `code` to <code>', () => {
    expect(renderMotd('run `ls -la` now')).toBe('run <code>ls -la</code> now')
  })

  it('converts [text](https://url) to an <a> with target and rel', () => {
    expect(renderMotd('[visit](https://example.com)')).toBe(
      '<a href="https://example.com" target="_blank" rel="noopener">visit</a>',
    )
  })

  it('also renders http:// links (not just https)', () => {
    expect(renderMotd('[link](http://example.com)')).toBe(
      '<a href="http://example.com" target="_blank" rel="noopener">link</a>',
    )
  })

  it('does not linkify non-http schemes (XSS guard)', () => {
    const out = renderMotd('[click](javascript:alert(1))')
    expect(out).not.toContain('<a ')
    expect(out).toContain('javascript:alert(1)')
  })

  it('converts newlines to <br>', () => {
    expect(renderMotd('line1\nline2')).toBe('line1<br>line2')
  })

  it('escapes HTML before applying Markdown (XSS prevention)', () => {
    // The < and > in the bold text must be entity-encoded, not raw tags
    expect(renderMotd('**<script>**')).toBe('<strong>&lt;script&gt;</strong>')
  })

  it('renders multiple Markdown constructs in one string', () => {
    const out = renderMotd('**Welcome** — run `ping` or [docs](https://example.com)\nnew line')
    expect(out).toContain('<strong>Welcome</strong>')
    expect(out).toContain('<code>ping</code>')
    expect(out).toContain('<a href="https://example.com"')
    expect(out).toContain('<br>')
  })
})
