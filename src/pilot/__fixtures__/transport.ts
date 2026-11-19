import fixtures from '../../../project-context/pilot/planning/shared/api/fixtures/http.json'
import spec from '../../../project-context/pilot/planning/shared/api/openapi.json'

type Fixture = typeof fixtures[number]

export function fixtureByName(name: string): Fixture {
  const fixture = fixtures.find(item => item.name === name)
  if (!fixture) throw new Error('Unknown fixture: ' + name)
  return fixture
}

/** Explicit injection for tests. The application always uses same-origin HTTP. */
export function fixtureTransport(...names: string[]): typeof fetch {
  const remaining = names.map(fixtureByName)
  return async (input, init) => {
    const fixture = remaining.shift()
    if (!fixture) throw new Error('Unexpected fixture request')
    const endpoint = Object.entries(spec.paths).flatMap(([path, methods]) =>
      Object.entries(methods).map(([method, operation]) => ({ path, method, operation })),
    ).find(({ operation }) => operation.operationId === fixture.operation_id)
    if (!endpoint) throw new Error('Unknown operation: ' + fixture.operation_id)
    const expected = endpoint.path.replace(/\{(\w+)\}/g, (_, key: string) =>
      String(fixture.path_parameters[key as keyof typeof fixture.path_parameters]),
    )
    const actual = new URL(String(input), 'http://fixture.invalid')
    if (actual.pathname !== expected || (init?.method ?? 'GET').toLowerCase() !== endpoint.method) {
      throw new Error('Unexpected request for ' + fixture.name)
    }
    const headers = new Headers({ 'Content-Type': 'application/json' })
    for (const [name, value] of Object.entries(fixture.response.headers)) {
      if (typeof value === 'string') headers.set(name, value)
    }
    return new Response(fixture.response.status === 204 ? null : JSON.stringify(fixture.response.body), {
      status: fixture.response.status, headers,
    })
  }
}
