import { renderToStaticMarkup } from 'react-dom/server'
import { expect, test } from 'vitest'
import { copy } from '../copy'
import { reviewLabel } from './StaffScreens'

test('REL-C07 staff review wording speaks in the third person', () => {
  expect(reviewLabel('confirmed')).toBe(copy('staff.review_confirmed'))
  expect(reviewLabel('system_error')).toBe(copy('staff.review_system_error'))
  expect(reviewLabel(null)).toBe(copy('staff.review_missing'))

  for (const state of ['confirmed', 'system_error', undefined]) {
    const label = reviewLabel(state)
    expect(label).toContain('Учитель')
    expect(label).not.toContain('Вы ')
  }
})

test('REL-C07 staff copy never implies an action from the staff member', () => {
  const readonly = copy('staff.readonly')
  expect(readonly).toContain('Только просмотр')
  expect(renderToStaticMarkup(<p>{readonly}</p>)).not.toContain('Согласен')
})
