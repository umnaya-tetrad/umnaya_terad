import { expect, test } from 'vitest'
import { lifecycleCheck } from '../__fixtures__/ui-scenarios'
import { parseManifest, readWorkbenchView, scenarioCheck, selectTask, workbenchAllowed, workbenchAsset } from './workbench'

test('UX workbench requires both explicit flags; a query never enables it in polza', () => {
  expect(workbenchAllowed('true', 'fixture')).toBe(true)
  for (const [flag, transport] of [[undefined, 'fixture'], ['false', 'fixture'], ['true', 'polza'], ['true', undefined]]) {
    expect(workbenchAllowed(flag, transport)).toBe(false)
  }
  expect(readWorkbenchView('?ux_view=summary', false)).toBeUndefined()
  expect(readWorkbenchView('?ux_view=review&ux_task=not-a-task', true)).toEqual({ page: 'review', task: undefined, notebook: undefined })
  expect(readWorkbenchView('?ux_view=admin', true)).toBeUndefined()
})

test('UX workbench photo URLs stay in the local public fixture directory', () => {
  const origin = 'http://127.0.0.1:5173'
  expect(workbenchAsset('assets/photo_01.png', origin)).toBe(`${origin}/ux-workbench/assets/photo_01.png`)
  for (const path of ['https://polza.ai/photo.png', '//other.example/photo.png', '../../api/auth/logout']) {
    expect(() => workbenchAsset(path, origin)).toThrow()
  }
  expect(() => parseManifest({ schema_version: 'wrong', scenarios: [] }, origin)).toThrow()
  expect(parseManifest({ schema_version: 'ux-workbench/1', scenarios: [
    { id: 'manual', marker: '[UX 01]', title: '[UX 01] Съемка', description: 'Пустой сценарий', photos: [] },
  ] }, origin).scenarios[0].photos).toEqual([])
})

test('UX workbench discovers the original seed without selecting manual work or a fresh copy', () => {
  const scenario = { id: 'mixed', marker: '[UX 02]', title: '[UX 02] Разборы', description: '', photos: ['assets/photo.png'] }
  const items = [
    { id: 'manual', title: 'Моя проверка с текстом [UX 02]' },
    { id: 'fresh', title: '[UX RUN mixed] Разборы' },
    { id: 'seed', title: scenario.title },
  ]
  expect(scenarioCheck(items, scenario)?.id).toBe('seed')
  expect(scenarioCheck(items.slice(0, 2), scenario)).toBeUndefined()
})

test('UX screen shortcuts select real task IDs and preserve the distinction between errors and missing assessment', () => {
  const check = lifecycleCheck('mixed-skip-only-one-task')
  const first = check.notebooks[0].bundles[0].tasks[0]
  const unassessed = check.notebooks[0].bundles[0].tasks.find(task => task.analysis.result === 'not_assessed')!
  // This lifecycle fixture marks the unassessed task skipped; an active copy is
  // needed to navigate to its real skip UI rather than a deleted/old result.
  unassessed.skipped = false
  expect(selectTask(check, 'error')?.task.task_id).toBe(first.task_id)
  expect(selectTask(check, 'unassessed')?.task.task_id).toBe(unassessed.task_id)
  unassessed.skipped = true
  expect(selectTask(check, 'unassessed')).toBeUndefined()
})
