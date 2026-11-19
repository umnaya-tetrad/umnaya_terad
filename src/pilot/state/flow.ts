import type { Action } from '../api/client'
import type { Bundle, Check, Mutation, Notebook, TaskAnalysis } from '../api/contract'

export type Mutate = (action: Action, reload?: boolean) => Promise<Mutation>
export type RefreshRevision = (compatible: (check: Check) => boolean) => Promise<Check>
export type Run = (work: (refreshRevision: RefreshRevision) => Promise<void>) => Promise<boolean>
export type TaskLocation = { notebook: Notebook; bundle: Bundle; task: TaskAnalysis; number: number }

export function notebookPhotoCount(notebook: Notebook): number {
  return new Set(notebook.bundles.flatMap(bundle => [
    ...(bundle.current_input?.photos ?? []),
    ...(bundle.draft?.photos ?? []),
  ]).map(photo => photo.id)).size
}

export function tasksIn(notebook: Notebook): TaskLocation[] {
  return notebook.bundles.flatMap(bundle =>
    bundle.skipped ? [] : bundle.tasks.map(task => ({ notebook, bundle, task })),
  ).map((entry, index) => ({ ...entry, number: index + 1 }))
}

export function reviewQueue(check: Check, unreviewed = false) {
  return check.notebooks.flatMap(tasksIn).filter(({ task }) => (
    !task.skipped && task.analysis.result !== 'not_assessed' && (!unreviewed || !task.review)
  ))
}

export function skippedCounts(check: Check) {
  const bundles = check.notebooks.flatMap(notebook => notebook.bundles)
  const tasks = bundles.flatMap(bundle => bundle.tasks)
  return {
    disputed: tasks.filter(task => task.review?.state === 'system_error' && !task.skipped).length,
    skipped_tasks: tasks.filter(task => task.skipped).length,
    skipped_bundles: bundles.filter(bundle => bundle.skipped).length,
  }
}

export function skippable(bundle: Bundle) {
  return !bundle.skipped && !!bundle.current_input && (
    bundle.result?.report.status === 'uncheckable' ||
    bundle.job?.state === 'failed' || bundle.job?.state === 'blocked' || bundle.job?.state === 'unknown'
  )
}
