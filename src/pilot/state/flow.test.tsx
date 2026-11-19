import { expect, test } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import oracle from '../../../project-context/pilot/planning/shared/analytics/fixtures/oracle.result.json'
import type { Check, CheckerTask, Summary } from '../api/contract'
import { fixtureByName } from '../__fixtures__/transport'
import { lifecycleCheck } from '../__fixtures__/ui-scenarios'
import { TaskCard } from '../components/TaskCard'
import { movePhoto } from '../photos'
import { SummaryScreen } from '../screens/SummaryScreen'
import { CheckStore } from './checkStore'
import { reviewQueue } from './flow'

const check = fixtureByName('getCheck').response.body as Check

test('APP-C09 reorder preserves the same set and ignores invalid moves', () => {
  expect(movePhoto(['first', 'second', 'third'], 'first', 1)).toEqual(['second', 'first', 'third'])
  expect(movePhoto(['first', 'second'], 'first', -1)).toEqual(['first', 'second'])
})

test('APP-C28 stale GET and replay cannot roll the store back', () => {
  const store = new CheckStore()
  const earlier = store.beginRead()
  const recent = store.beginRead()
  expect(store.commit(recent, { ...check, revision: 14 })).toBe(true)
  store.acknowledge(12)
  expect(store.commit(earlier, { ...check, revision: 14 })).toBe(false)
  expect(store.commit(store.beginRead(), { ...check, revision: 13 })).toBe(false)
  expect(store.revision).toBe(14)
})

test('APP-C13 ready results come from server tasks and omit unassessed and skipped', () => {
  expect(reviewQueue(check).every(({ task }) => task.analysis.result !== 'not_assessed' && !task.skipped)).toBe(true)
})

test('APP-C15 APP-C16 independent completeness and safe rendering', () => {
  const value: CheckerTask = {
    task_id: 'fixture', locator: '<img src=x onerror=alert(1)>', condition: '',
    result: 'all_steps_correct', completeness: 'incomplete', detail_level: 'omitted_steps',
    omitted_steps_note: '', completeness_note: '', first_error: null, evidence: [], photo_indices: [1], uncheckable_reason: '',
  }
  const rendered = renderToStaticMarkup(<TaskCard value={value} photoCount={1} />)
  expect(rendered).toContain('В записанных шагах ошибок не найдено')
  expect(rendered).toContain('Решение не закончено')
  expect(rendered).not.toContain('<img')
  expect(rendered).not.toContain('Правильная запись шага')
})

function renderSummary(value: Summary) {
  return renderToStaticMarkup(<SummaryScreen value={value} check={check} materials={() => {}}
    busy={false} run={async () => false} mutate={async () => { throw new Error('unexpected mutation') }} />)
}

test('APP-C25 APP-C26 renders oracle denominator, frequency and stale guard', () => {
  const value: Summary = {
    ...check.summary, state: 'succeeded', stale: false, can_retry: false, can_refresh: false,
    result: oracle as Summary['result'],
  }
  const rendered = renderSummary(value)
  expect(rendered).toContain('Тетрадей в проверке: 4')
  expect(rendered).toContain('Среднее первых ошибок на тетрадь: 0,5')
  expect(rendered).toContain('В расчете полностью подтвержденных тетрадей: 2')
  expect(rendered.match(/Подтвержденных задач: 1/g)).toHaveLength(2)
  const stale = renderSummary({ ...value, stale: true, can_retry: true, can_refresh: true })
  expect(stale).not.toContain('Тетрадей в проверке: 4')
  expect(stale).toContain('Обновить сводку')
  expect(stale).not.toContain('Повторить подготовку сводки')
})

test('APP-C25 uses lifecycle capabilities for fresh failure and stale in-flight states', () => {
  const failed = renderSummary(lifecycleCheck('fresh-failed-analytics-can-retry').summary)
  const queued = renderSummary(lifecycleCheck('stale-analytics-queued').summary)
  const running = renderSummary(lifecycleCheck('stale-analytics-running').summary)
  const unknown = renderSummary(lifecycleCheck('stale-analytics-unknown').summary)
  expect(failed).toContain('Повторить подготовку сводки')
  expect(queued).toContain('Обновить сводку')
  expect(running).not.toContain('Обновить сводку')
  expect(unknown).not.toContain('Обновить сводку')
  expect(unknown).not.toContain('Повторить подготовку сводки')
})
