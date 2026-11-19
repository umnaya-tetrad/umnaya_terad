import type { Check } from '../api/contract'

export function workbenchAllowed(flag: string | undefined, transport: string | undefined) {
  return flag === 'true' && transport === 'fixture'
}

export const WORKBENCH_ENABLED = workbenchAllowed(
  import.meta.env.VITE_UX_WORKBENCH, import.meta.env.VITE_PILOT_TRANSPORT,
)

export type WorkbenchView = { page: 'check' | 'notebook' | 'review' | 'completion' | 'summary'; task?: string; notebook?: string }
export type Scenario = { id: string; marker: string; title: string; description: string; photos: string[] }
export type PhotoSet = { id: string; title: string; photos: string[] }
export type Manifest = { schema_version: 'ux-workbench/1'; scenarios: Scenario[]; photo_sets?: PhotoSet[] }

export function readWorkbenchView(search: string, enabled = WORKBENCH_ENABLED): WorkbenchView | undefined {
  if (!enabled) return undefined
  const params = new URLSearchParams(search)
  const page = params.get('ux_view')
  if (!['check', 'notebook', 'review', 'completion', 'summary'].includes(page ?? '')) return undefined
  const uuid = (key: string) => /^[\da-f-]{36}$/i.test(params.get(key) ?? '') ? params.get(key)! : undefined
  return { page: page as WorkbenchView['page'], task: uuid('ux_task'), notebook: uuid('ux_notebook') }
}

export function workbenchAsset(path: string, origin: string) {
  const url = new URL(path, `${origin}/ux-workbench/`)
  if (url.origin !== origin || !url.pathname.startsWith('/ux-workbench/')) {
    throw new Error('Фото стенда должно находиться в /ux-workbench/.')
  }
  return url.href
}

export function parseManifest(value: unknown, origin: string): Manifest {
  const item = value as Manifest
  if (item?.schema_version !== 'ux-workbench/1' || !Array.isArray(item.scenarios) || !item.scenarios.length) {
    throw new Error('Не найден каталог сценариев UX-стенда.')
  }
  for (const scenario of item.scenarios) {
    if (typeof scenario.id !== 'string' || typeof scenario.marker !== 'string' ||
      typeof scenario.title !== 'string' || typeof scenario.description !== 'string' || !Array.isArray(scenario.photos) ||
      (!scenario.photos.length && scenario.id !== 'manual')) {
      throw new Error('Некорректный сценарий UX-стенда.')
    }
    for (const photo of scenario.photos) {
      if (typeof photo !== 'string') throw new Error('Некорректный путь демо-фото.')
      workbenchAsset(photo, origin)
    }
  }
  for (const set of item.photo_sets ?? []) for (const photo of set.photos) workbenchAsset(photo, origin)
  return item
}

export function scenarioCheck<T extends { id: string; title: string }>(items: T[], scenario: Scenario) {
  return items.find(item => item.title === scenario.title) ?? items.find(item => item.title.startsWith(`${scenario.marker} `))
}

export type TaskFilter = 'any' | 'correct' | 'error' | 'incomplete' | 'unassessed'
export function selectTask(check: Check, filter: TaskFilter = 'any') {
  return check.notebooks.flatMap(notebook => notebook.bundles.flatMap(bundle =>
    bundle.skipped ? [] : bundle.tasks.filter(task => !task.skipped).map(task => ({ notebook, task })),
  )).find(({ task }) => filter === 'any' ||
    (filter === 'correct' && task.analysis.result === 'all_steps_correct' && task.analysis.completeness === 'complete') ||
    (filter === 'error' && task.analysis.result === 'first_error_found') ||
    (filter === 'incomplete' && task.analysis.completeness === 'incomplete') ||
    (filter === 'unassessed' && task.analysis.result === 'not_assessed'))
}
