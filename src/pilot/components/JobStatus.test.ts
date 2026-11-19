import { expect, test } from 'vitest'
import { lifecycleCheck } from '../__fixtures__/ui-scenarios'
import { reviewQueue, skippable } from '../state/flow'
import { bundleStatus } from './JobStatus'

test('APP-C13 two source photos make one continued task', () => {
  const check = lifecycleCheck('two-photo-continuation')
  const queue = reviewQueue(check)
  const continued = queue.filter(entry => entry.task.analysis.photo_indices.length === 2)
  expect(continued).toHaveLength(1)
  expect(continued[0].task.analysis.photo_indices).toEqual([1, 2])
  expect(new Set(queue.map(entry => entry.task.task_id)).size).toBe(queue.length)
})

test('APP-C21 unknown, blocked and skipped have separate operational status and guards', () => {
  const unknown = lifecycleCheck('unknown-input-no-false-zero').notebooks[0].bundles[0]
  const blocked = lifecycleCheck('blocked-input-no-false-zero').notebooks[0].bundles[0]
  const skipped = lifecycleCheck('skipped-failed-bundle-stays-partial').notebooks[0].bundles[0]
  expect(bundleStatus(unknown)).toBe('job.unknown')
  expect(bundleStatus(blocked)).toBe('job.blocked')
  expect(bundleStatus(skipped)).toBe('job.skipped')
  expect(skippable(unknown)).toBe(true)
  expect(skippable(blocked)).toBe(true)
  expect(skippable(skipped)).toBe(false)
})
