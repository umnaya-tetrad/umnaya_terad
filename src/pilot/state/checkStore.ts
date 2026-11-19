import type { Check } from '../api/contract'

// Ignore requests started before one that already published, plus any response
// below the most recent revision acknowledged by a write.
export class CheckStore {
  private started = 0
  private published = 0
  private floor = 0
  current: Check | null = null

  beginRead() { return ++this.started }

  acknowledge(revision: number) {
    this.floor = Math.max(this.floor, revision)
  }

  commit(sequence: number, check: Check) {
    if (sequence < this.published || check.revision < this.floor) return false
    this.published = sequence
    this.acknowledge(check.revision)
    this.current = check
    return true
  }

  acceptFailure(sequence: number, missing: boolean) {
    if (sequence < this.published) return false
    this.published = sequence
    if (missing) this.current = null
    return true
  }

  get revision() { return Math.max(this.floor, this.current?.revision ?? 0) }
}
