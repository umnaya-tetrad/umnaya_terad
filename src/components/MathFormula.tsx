import { useCallback, useLayoutEffect, useRef, useState, type CSSProperties } from 'react'
import katex from 'katex'
import 'katex/dist/katex.min.css'

interface MathFormulaProps {
  latex: string
  className?: string
  wrap?: boolean
}

export interface MathTextSegment {
  kind: 'text' | 'math'
  value: string
  display: boolean
}

// At the mobile base size this keeps mathematical symbols legible; below this
// value an explicit per-card horizontal swipe is more useful than tiny math.
const MIN_FIT_SCALE = 0.68
const FIT_SAFETY_GAP = 0.98

export function getNextFormulaScale(currentScale: number, contentWidth: number, availableWidth: number) {
  if (contentWidth <= availableWidth || !availableWidth) return currentScale

  const proportionalScale = currentScale * (availableWidth / contentWidth) * FIT_SAFETY_GAP
  // The small fixed step keeps the reduction smooth when a single KaTeX glyph
  // creates the overflow; the proportional value handles long fractions at once.
  return Math.max(MIN_FIT_SCALE, Math.min(currentScale - 0.04, proportionalScale))
}

export function normalizeModelLatex(latex: string) {
  // Модель иногда отдаёт финальную подпись как обычный русский текст в math
  // mode (`Ответ: x = …`). KaTeX отображает формулу, но пишет предупреждения
  // и рисует текст некорректно; оформляем только этот известный префикс.
  return latex
    .replace(/^(\s*)([Оо]твет:\s*)/, '$1\\text{$2} ')
    // Иногда модель пропускает открывающий разделитель перед aligned.
    .replace(/\\left\\begin\{aligned\}/g, '\\left\\{\\begin{aligned}')
    // В части ответов модели вместо спецификатора столбца array приходит цифра 1.
    .replace(/\\begin\{array\}\{\s*\d+\s*\}/g, '\\begin{array}{l}')
    // Системы модель иногда записывает с квадратной скобкой вместо фигурной.
    .replace(/\\left\[\s*\\begin\{(aligned|array|cases)\}/g, '\\left\\{\\begin{$1}')
}

function splitPlainFormula(latex: string, consequenceCommands: string[]) {
  const fragments: string[] = []
  let fragment = ''
  let depth = 0

  for (let index = 0; index < latex.length; index += 1) {
    const character = latex[index]
    if (character === '{') depth += 1
    if (character === '}') depth = Math.max(0, depth - 1)

    if (depth === 0 && ['=', '+', '-', ',', ';'].includes(character) && fragment.trim()) {
      fragments.push(`${fragment}${character}`.trim())
      fragment = ''
      continue
    }

    const command = [...consequenceCommands, '\\cdot', '\\times', '\\quad', '\\;', '\\,'].find((item) => latex.startsWith(item, index))
    if (depth === 0 && command) {
      fragments.push(`${fragment}${command}`.trim())
      fragment = ''
      index += command.length - 1
      continue
    }

    fragment += character
  }

  if (fragment.trim()) fragments.push(fragment.trim())
  return fragments.length > 1 ? fragments : [latex]
}

export function getFormulaFragments(latex: string) {
  const consequenceCommands = ['\\Longrightarrow', '\\Rightarrow', '\\Leftrightarrow', '\\implies', '\\iff']
  // Внутри среды матрицы или системы нельзя делить строку на фрагменты:
  // в отдельном фрагменте \begin и \end больше не образуют валидную формулу.
  // То же правило относится к паре \left/\right: перенос одного края
  // превращает вторую половину выражения в синтаксически неверный LaTeX.
  if (
    /\\begin\{(?:aligned|array|cases|matrix|pmatrix|bmatrix|Bmatrix|vmatrix|Vmatrix|smallmatrix|gathered)\}/.test(latex)
    || /\\(?:left|right)\b/.test(latex)
  ) {
    return [latex]
  }

  return splitPlainFormula(latex, consequenceCommands)
}

function hasStructuredLatex(latex: string) {
  return /\\begin\{(?:aligned|array|cases|matrix|pmatrix|bmatrix|Bmatrix|vmatrix|Vmatrix|smallmatrix|gathered)\}/.test(latex)
    || /\\(?:left|right)\b/.test(latex)
}

function renderWithKaTeX(latex: string, displayMode: boolean) {
  return katex.renderToString(normalizeModelLatex(latex), {
    displayMode,
    throwOnError: true,
    trust: false
  })
}

function repairFragment(latex: string) {
  return latex
    // После переноса часть \left/\right может оказаться на другой строке.
    // Обычные круглые скобки остаются валидным и визуально тем же вариантом.
    .replace(/\\left|\\right/g, '')
    // У модели иногда встречается незавершённая среда в одном фрагменте.
    .replace(/\\(?:begin|end)\{(?:aligned|array|cases|matrix|pmatrix|bmatrix|Bmatrix|vmatrix|Vmatrix|smallmatrix|gathered)\}/g, '')
    .replaceAll('&', '')
    .replace(/\\\\/g, ' ')
}

function fallbackFormula(latex: string) {
  const escaped = latex.replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;')
  return `<span class="math-formula__plain-fallback">${escaped}</span>`
}

function renderFormula(latex: string) {
  try {
    return renderWithKaTeX(latex, true)
  } catch {
    // Не пытаемся «чинить» систему или матрицу удалением её структуры:
    // это визуально хуже и может изменить смысл ответа модели.
    if (hasStructuredLatex(latex)) return fallbackFormula(latex)
    try {
      return renderWithKaTeX(repairFragment(latex), true)
    } catch {
      return fallbackFormula(latex)
    }
  }
}

function renderInlineFormula(latex: string) {
  try {
    return renderWithKaTeX(latex, false)
  } catch {
    if (hasStructuredLatex(latex)) return fallbackFormula(latex)
    try {
      return renderWithKaTeX(repairFragment(latex), false)
    } catch {
      return fallbackFormula(latex)
    }
  }
}

function trimFormulaEnd(value: string) {
  return value.replace(/[,:;.!?]+\s*$/, '').trimEnd()
}

function splitUndelimitedLatex(text: string): MathTextSegment[] {
  const segments: MathTextSegment[] = []
  let cursor = 0

  while (cursor < text.length) {
    const start = text.indexOf('\\', cursor)
    if (start === -1) {
      if (text.slice(cursor)) segments.push({ kind: 'text', value: text.slice(cursor), display: false })
      break
    }

    if (start > cursor) segments.push({ kind: 'text', value: text.slice(cursor, start), display: false })

    let end = start
    while (end < text.length && !/[А-Яа-яЁё]/.test(text[end]) && !/[.!?]/.test(text[end])) end += 1
    const formula = trimFormulaEnd(text.slice(start, end))

    if (formula.length > 1) segments.push({ kind: 'math', value: formula, display: false })
    else segments.push({ kind: 'text', value: text.slice(start, end), display: false })

    cursor = end
  }

  return segments
}

/** Splits plain text, `$...$`, `\\(...\\)` and common undelimited LaTex from model explanations. */
export function getMathTextSegments(text: string): MathTextSegment[] {
  const segments: MathTextSegment[] = []
  const delimiter = /\$\$([\s\S]+?)\$\$|\\\[([\s\S]+?)\\\]|\\\(([\s\S]+?)\\\)|\$([^$\n]+?)\$/g
  let cursor = 0
  let match: RegExpExecArray | null

  while ((match = delimiter.exec(text))) {
    if (match.index > cursor) segments.push(...splitUndelimitedLatex(text.slice(cursor, match.index)))
    const value = match[1] ?? match[2] ?? match[3] ?? match[4]
    segments.push({ kind: 'math', value: value.trim(), display: Boolean(match[1] ?? match[2]) })
    cursor = delimiter.lastIndex
  }

  if (cursor < text.length) segments.push(...splitUndelimitedLatex(text.slice(cursor)))
  return segments
}

export function MathFormula({ latex, className, wrap = false }: MathFormulaProps) {
  const formulaRef = useRef<HTMLDivElement>(null)
  const [fitScale, setFitScale] = useState(1)
  const [isScrollable, setIsScrollable] = useState(false)
  const observedWidthRef = useRef(0)

  const measureOverflow = useCallback(() => {
    const formula = formulaRef.current
    if (!formula) return

    if (formula.scrollWidth <= formula.clientWidth + 1) {
      if (isScrollable) setIsScrollable(false)
      return
    }

    const nextScale = getNextFormulaScale(fitScale, formula.scrollWidth, formula.clientWidth)
    if (nextScale < fitScale) {
      setIsScrollable(false)
      setFitScale(nextScale)
      return
    }

    // Matrices and systems can contain a non-breakable row. Their final
    // fallback is scrolling inside this formula, never outside the card.
    setIsScrollable(true)
  }, [fitScale, isScrollable])

  useLayoutEffect(() => {
    if (!wrap) return
    setFitScale(1)
    setIsScrollable(false)
  }, [latex, wrap])

  useLayoutEffect(() => {
    if (!wrap) return

    const formula = formulaRef.current
    if (!formula) return

    let cancelled = false
    const checkOverflow = () => {
      if (!cancelled) measureOverflow()
    }
    const firstFrame = requestAnimationFrame(checkOverflow)
    // KaTeX web-fonts can finish after the first animation frame. A wide
    // fraction then changes its real width without changing the card width,
    // so ResizeObserver alone would not fire again.
    const delayedCheck = window.setTimeout(checkOverflow, 160)
    void document.fonts?.ready.then(checkOverflow)
    const observer = new ResizeObserver(([entry]) => {
      const width = entry.contentRect.width
      if (Math.abs(width - observedWidthRef.current) <= 1) return

      observedWidthRef.current = width
      setFitScale(1)
    })

    observer.observe(formula)
    return () => {
      cancelled = true
      cancelAnimationFrame(firstFrame)
      window.clearTimeout(delayedCheck)
      observer.disconnect()
    }
  }, [latex, measureOverflow, wrap])

  if (wrap) {
    return (
      <div
        ref={formulaRef}
        className={`${className ?? ''} math-formula--wrap math-formula--fit${isScrollable ? ' math-formula--scrollable' : ''}`}
        style={{ '--math-fit-scale': fitScale } as CSSProperties}
      >
        {getFormulaFragments(latex).map((fragment, index) => (
          <span className="math-formula__fragment" key={`${fragment}-${index}`} dangerouslySetInnerHTML={{ __html: renderFormula(fragment) }} />
        ))}
      </div>
    )
  }

  return <div className={className} dangerouslySetInnerHTML={{ __html: renderFormula(latex) }} />
}

export function MathText({ text, className }: { text: string; className?: string }) {
  return (
    <span className={`math-text ${className ?? ''}`.trim()}>
      {getMathTextSegments(text).map((segment, index) => (
        segment.kind === 'text'
          ? <span key={`${index}-${segment.value}`}>{segment.value}</span>
          : <span key={`${index}-${segment.value}`} className={segment.display ? 'math-text__display' : 'math-text__inline'} dangerouslySetInnerHTML={{ __html: renderInlineFormula(segment.value) }} />
      ))}
    </span>
  )
}
