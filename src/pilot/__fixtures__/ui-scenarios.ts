import lifecycle from '../../../project-context/pilot/planning/shared/api/fixtures/lifecycle.json'
import type { Check } from '../api/contract'

export function lifecycleCheck(name: keyof typeof lifecycle): Check {
  return structuredClone(lifecycle[name]) as Check
}
