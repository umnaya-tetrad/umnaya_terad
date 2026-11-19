import katex from 'katex'
import 'katex/dist/katex.min.css'
import { getMathTextSegments } from '../../components/MathFormula'

function Formula({ value, display = false }: { value: string; display?: boolean }) {
  const className = display ? 'formula display-formula' : 'formula'
  try {
    const html = katex.renderToString(value, { trust: false, throwOnError: true, displayMode: display, maxExpand: 1000 })
    return <span className={className} dangerouslySetInnerHTML={{ __html: html }} />
  } catch {
    return <span className={className}>{value}</span>
  }
}

export function MathText({ text, formula = false }: { text: string; formula?: boolean }) {
  if (formula) return <Formula value={text} display />
  return <span className="math-text">{getMathTextSegments(text).map((segment, index) =>
    segment.kind === 'math'
      ? <Formula key={index} value={segment.value} display={segment.display} />
      : <span key={index}>{segment.value}</span>,
  )}</span>
}
