import { renderToStaticMarkup } from 'react-dom/server'
import { expect, test } from 'vitest'
import { copy } from '../copy'
import oracle from '../../../project-context/pilot/planning/shared/analytics/fixtures/oracle.result.json'
import partial from '../../../project-context/pilot/planning/shared/analytics/fixtures/zero-denominator.result.json'
import type { ClassSummary, Summary, SummaryHistory } from '../api/contract'
import { reviewLabel, StaffSummaryHistory } from './StaffScreens'

test('REL-C07 staff review wording speaks in the third person', () => {
  expect(reviewLabel('confirmed')).toBe(copy('staff.review_confirmed'))
  expect(reviewLabel('system_error')).toBe(copy('staff.review_system_error'))
  expect(reviewLabel(null)).toBe(copy('staff.review_missing'))

  for (const state of ['confirmed', 'system_error', undefined]) {
    const label = reviewLabel(state)
    expect(label).toContain('Учитель')
    expect(label).not.toContain('Вы ')
  }
})

test('REL-C07 staff copy never implies an action from the staff member', () => {
  const readonly = copy('staff.readonly')
  expect(readonly).toContain('Только просмотр')
  expect(renderToStaticMarkup(<p>{readonly}</p>)).not.toContain('Согласен')
})

function summary(result: ClassSummary | null, state: Summary['state'] = 'succeeded', stale = false): Summary {
  return { state, stale, snapshot_id: null, job_id: null, data_revision: 1, can_retry: false, can_refresh: false, result }
}

test('REL-C07 historical summaries keep their own counts, denominator and null average', () => {
  const value: SummaryHistory = { items: [
    { created_at: '2026-11-19T12:00:00Z', summary: summary(oracle as ClassSummary, 'succeeded', true) },
    { created_at: '2026-11-19T13:00:00Z', summary: summary(partial as ClassSummary) },
  ] }
  const html = renderToStaticMarkup(<StaffSummaryHistory value={value} />)
  expect(html).not.toMatch(/\{(?:count|value|date)\}/)
  expect(html).toContain(copy('summary.basis', { count: 2 }))
  expect(html).toContain(copy('summary.average', { value: '0,5' }))
  expect(html).toContain(copy('summary.basis', { count: 0 }))
  expect(html).toContain(copy('summary.no_average'))
  expect(html).toContain(copy('summary.partial', { count: partial.notebooks.partial }))
  expect(html).toContain(copy('summary.stale'))
  expect(html).toContain(oracle.top_errors[0].rule)
  expect(html).not.toContain('<button')
})

test('REL-C07 failed historical summaries show their state without invented numeric results', () => {
  const html = renderToStaticMarkup(<StaffSummaryHistory value={{ items: [
    { created_at: '2026-11-19T14:00:00Z', summary: summary(null, 'failed') },
  ] }} />)
  expect(html).toContain(copy('summary.failed'))
  expect(html).not.toContain(copy('summary.with_errors', { count: 0 }))
  expect(html).not.toContain(copy('summary.basis', { count: 0 }))
  expect(html).not.toMatch(/\{\w+\}/)
})
