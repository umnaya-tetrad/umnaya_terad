import catalog from '../../project-context/pilot/planning/shared/ux-copy.json'

export type CopyKey = keyof typeof catalog.messages

export function copy(key: CopyKey, values: Record<string, string | number> = {}) {
  return catalog.messages[key].replace(/\{(\w+)\}/g, (match, name: string) => String(values[name] ?? match))
}

// The contract catalog includes the fixture disclosure after the short chrome label.
export const fixtureLabel = copy('common.fixture_mode').split('.')[0]
