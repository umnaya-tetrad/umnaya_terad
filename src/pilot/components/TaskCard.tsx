import type { CheckerTask } from '../api/contract'
import { copy } from '../copy'
import { MathText } from './MathText'

export function TaskCard({ value }: { value: CheckerTask }) {
  const first = value.first_error
  return <div className="sheet stack">
    {value.locator && <p className="context">{value.locator}</p>}
    <h2>{copy(
      value.result === 'first_error_found' ? 'result.error_found'
      : value.result === 'all_steps_correct' ? 'result.correct' : 'result.no_result',
    )}</h2>
    {value.completeness !== 'complete' && <div className="notice">
      <p>{copy(value.completeness === 'incomplete' ? 'result.incomplete' : 'result.completeness_unknown')}</p>
      {value.completeness_note && <p><MathText text={value.completeness_note} /></p>}
    </div>}
    {(value.result === 'not_assessed' && value.uncheckable_reason) && <p><MathText text={value.uncheckable_reason} /></p>}
    {value.condition && <div>
      <h3>{copy('result.condition')}</h3><MathText text={value.condition} />
    </div>}
    {!!value.evidence.length && <div>
      <h3>{copy('result.lines')}</h3>
      <ol className="evidence">{value.evidence.slice(0, 4).map((line, index) =>
        <li key={index}><MathText formula text={line.latex} /></li>,
      )}</ol>
    </div>}
    {value.omitted_steps_note && <p><MathText text={value.omitted_steps_note} /></p>}
    {first && <div className="first-error stack">
      <div><h3>{copy('result.first_error')}</h3><MathText formula text={first.wrong_latex} /></div>
      <div><h3>{copy('result.rule')}</h3><p><MathText text={first.rule} /></p></div>
      <div><h3>{copy('result.explanation')}</h3><p><MathText text={first.explanation} /></p></div>
      <div><h3>{copy('result.corrected')}</h3><MathText formula text={first.corrected_latex} /></div>
    </div>}
  </div>
}
