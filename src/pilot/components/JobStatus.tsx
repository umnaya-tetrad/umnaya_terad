import type { Bundle, Summary } from '../api/contract'
import { copy, type CopyKey } from '../copy'

export function bundleStatus(bundle: Bundle): CopyKey | undefined {
  if (bundle.skipped) return 'job.skipped'
  if (bundle.result?.report.status === 'uncheckable') return 'job.uncheckable'
  switch (bundle.job?.state) {
    case 'queued': case 'running': return 'job.pending'
    case 'retry_wait': return 'job.retry_wait'
    case 'blocked': return 'job.blocked'
    case 'unknown': return 'job.unknown'
    case 'failed': return 'job.failed'
  }
}

export function JobStatus({ bundle }: { bundle: Bundle }) {
  const label = bundleStatus(bundle)
  return label && <p className="notice" role="status">{copy(label)}</p>
}

export function summaryStatus(summary: Summary): CopyKey | undefined {
  switch (summary.state) {
    case 'not_started': return 'summary.not_started'
    case 'queued': case 'running': return 'summary.pending'
    case 'retry_wait': return 'summary.retry_wait'
    case 'blocked': return 'summary.blocked'
    case 'unknown': return 'summary.unknown'
    case 'failed': case 'cancelled': case 'superseded': return 'summary.failed'
  }
}
