import { copy } from '../copy'
import type { ErrorResponse } from './contract'

export class ApiError extends Error {
  constructor(readonly status: number, readonly detail?: ErrorResponse['error']) {
    super(detail?.code ?? 'pilot_request_failed')
  }
}

export function errorText(error: unknown) {
  if (error instanceof ApiError) {
    if (error.status === 401) return copy('common.session_expired')
    if (error.status === 409) return copy('common.conflict')
    if (error.status === 403 || error.status === 404) return copy('common.unavailable')
    if ([413, 415, 422].includes(error.status) && error.detail?.message) return error.detail.message
    if (error.status === 413 || error.status === 415) return copy('capture.file_error')
    return copy('common.save_failed')
  }
  return copy('common.network')
}
