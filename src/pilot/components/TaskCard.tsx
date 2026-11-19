import type { CheckerTask } from '../api/contract'
import { copy } from '../copy'
import { MathText } from './MathText'
import { MathFormula } from '../../components/MathFormula'

export function TaskCard({ value, photoCount }: { value: CheckerTask; photoCount: number }) {
  const first = value.first_error
  const lines = value.evidence.slice(0, 4)
  // Presentation only: use the error already identified by the checker. Never
  // present that line, or its subsequent transformations, as verified steps.
  const errorLine = first ? lines.findIndex(line => line.photo_index === first.photo_index &&
    line.latex.replace(/\s/g, '') === first.wrong_latex.replace(/\s/g, '')) : -1
  const leadingLines = errorLine >= 0 ? lines.slice(0, errorLine) : lines
  const verifiedLines = value.result === 'all_steps_correct' || errorLine >= 0
  const outcome = value.result === 'first_error_found' ? 'incorrect'
    : value.result === 'all_steps_correct' ? 'correct' : 'unassessed'
  const conditionIsFormula = !/[А-Яа-яЁё]|\$|\\\(|\\\[/.test(value.condition ?? '') ||
    /^\\(?:text|begin|left)\b/.test(value.condition ?? '')

  return <div className="task-analysis stack">
    {value.locator && <p className="context">{value.locator}</p>}
    {value.condition && <section className="task-condition task-frame">
      <h3>{copy('result.condition')}</h3>
      <div className="task-equation">{conditionIsFormula
        ? <MathFormula latex={value.condition} wrap />
        : <MathText text={value.condition} />}</div>
    </section>}
    <section className={`task-outcome task-frame task-outcome--${outcome}`}>
      <h2>{copy(
      value.result === 'first_error_found' ? 'result.error_found'
      : value.result === 'all_steps_correct' ? 'result.correct' : 'result.no_result',
      )}</h2>
    </section>
    {value.completeness !== 'complete' && <div className="notice">
      <p>{copy(value.completeness === 'incomplete' ? 'result.incomplete' : 'result.completeness_unknown')}</p>
      {value.completeness_note && <p><MathText text={value.completeness_note} /></p>}
    </div>}
    {(value.result === 'not_assessed' && value.uncheckable_reason) && <p><MathText text={value.uncheckable_reason} /></p>}
    {!!leadingLines.length && <section className={`task-lines task-frame${verifiedLines ? ' task-lines--correct' : ''}`}>
      <h3><span aria-hidden="true">{verifiedLines ? '✓' : '≡'}</span> {copy('result.lines')}</h3>
      <div className="task-lines-content">{leadingLines.map((line, index) =>
        <div className="task-key-line" key={index}>
          <div className="task-equation"><MathFormula latex={line.latex} wrap /></div>
          <small className="task-photo-ref">{copy('capture.photo', { number: line.photo_index, total: photoCount })}</small>
        </div>,
      )}</div>
    </section>}
    {value.omitted_steps_note && <p><MathText text={value.omitted_steps_note} /></p>}
    {first && <>
      <section className="task-wrong-step task-frame">
        <span className="task-error-marker" aria-hidden="true">!</span>
        <div className="task-wrong-content">
          <h3>{copy('result.first_error')}</h3>
          <div className="task-equation"><MathFormula latex={first.wrong_latex} wrap /></div>
          <small className="task-photo-ref">{copy('capture.photo', { number: first.photo_index, total: photoCount })}</small>
        </div>
      </section>
      <section className="task-error-explanation task-frame">
        <span className="task-explanation-marker" aria-hidden="true">!</span>
        <div className="task-error-copy stack">
          <div>
            <p className="task-block-label">{copy('result.rule')}</p>
            <h3><MathText text={first.rule} /></h3>
          </div>
          <div>
            <p className="task-block-label">{copy('result.explanation')}</p>
            <p><MathText text={first.explanation} /></p>
          </div>
          <div className="task-correction">
            <h4>{copy('result.corrected')}</h4>
            <div className="task-equation"><MathFormula latex={first.corrected_latex} wrap /></div>
          </div>
        </div>
      </section>
    </>}
  </div>
}
