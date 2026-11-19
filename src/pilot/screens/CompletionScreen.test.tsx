import { renderToStaticMarkup } from 'react-dom/server'
import { expect, test } from 'vitest'
import { lifecycleCheck } from '../__fixtures__/ui-scenarios'
import type { Check } from '../api/contract'
import { CompletionScreen } from './CompletionScreen'

function render(check: Check) {
  const noop = () => {}
  return renderToStaticMarkup(<CompletionScreen check={check} busy={false} finalized={noop}
    materials={noop} ready={noop} unresolved={noop} draft={noop} photo={noop} cameraOpened={noop} />)
}

test('APP-C23 pending work and an empty check obey distinct server conditions', () => {
  const check = lifecycleCheck('completion-waits-checker')
  const pending = render(check)
  expect(pending).toContain('Еще обрабатываются комплекты:')
  expect(pending).toContain('Посмотреть разборы')
  expect(pending).not.toContain('Завершить и создать сводку')

  const empty = render({
    ...check, notebooks: [], completion: {
      pending_jobs: 0, unreviewed_tasks: 0, unresolved_tasks: 0, unresolved_bundles: 0, unsent_drafts: 0,
      can_finalize: false,
    },
  })
  expect(empty).toContain('Добавьте и отправьте хотя бы один комплект фото.')
  expect(empty).toContain('Снять фото')
  expect(empty).toContain('Выбрать из галереи')
  expect(empty).not.toContain('Завершить и создать сводку')
})

test('APP-C24 server capability permits finalization without a bulk review control', () => {
  const check = lifecycleCheck('red-resolves-review-excluded-from-math')
  const rendered = render(check)
  expect(rendered).toContain('Завершить и создать сводку')
  expect(rendered).not.toContain('Согласен с проверкой')
})
