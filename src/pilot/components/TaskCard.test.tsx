import { renderToStaticMarkup } from 'react-dom/server'
import { expect, test } from 'vitest'
import singlePage from '../../../project-context/pilot/ai/examples/K01.response.json'
import twoTasks from '../../../project-context/pilot/ai/examples/E_C01.response.json'
import twoPages from '../../../project-context/pilot/ai/examples/M06.response.json'
import type { CheckerTask } from '../api/contract'
import { TaskCard } from './TaskCard'

function render(tasks: CheckerTask[], photoCount = 1) {
  return tasks.map(task => renderToStaticMarkup(<TaskCard value={task} photoCount={photoCount} />))
}

const one = singlePage.tasks as CheckerTask[]
const two = twoTasks.tasks as CheckerTask[]
const mixed = twoPages.tasks as CheckerTask[]
const continuation = mixed[1]

test('APP-C13 frozen page and continuation combinations have the expected independent cards', () => {
  expect(render(one)).toHaveLength(1)
  expect(render(two)).toHaveLength(2)
  expect(render([continuation], 2)).toHaveLength(1)
  expect(render(mixed, 2)).toHaveLength(2)
  expect(continuation.photo_indices).toEqual([1, 2])
  expect(continuation.first_error?.photo_index).toBe(2)
})

test('APP-C15 shows the exact checker correction and omits the error section for a correct report', () => {
  const [first] = render(two)
  const [correct] = render(one)
  const [, secondPage] = render(mixed, 2)
  expect(first).toContain('(2x-1)(6x-1)=0')
  expect(first).toContain('(2x-1)(6x+1)=0')
  expect(correct).not.toContain('Правильная запись шага')
  expect(secondPage).toContain(continuation.first_error!.corrected_latex)
})

test.each([
  ['K01', one, 1],
  ['E_C01', two, 1],
  ['M06', mixed, 2],
  ['M06 continuation only', [continuation], 2],
] as const)('APP-F02 %s labels evidence and the erroneous step with source photos', (_case, tasks, total) => {
  for (const task of tasks) {
    const [markup] = render([task], total)
    const labels = [...markup.matchAll(/<small class="context">([^<]+)<\/small>/g)].map(match => match[1])
    const indices = task.evidence.slice(0, 4).map(line => line.photo_index)
    if (task.first_error) indices.push(task.first_error.photo_index)
    expect(labels).toEqual(indices.map(index => `Фото ${index} из ${total}`))
  }
})
