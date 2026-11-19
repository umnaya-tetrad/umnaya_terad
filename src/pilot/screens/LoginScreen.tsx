import { useState, type FormEvent } from 'react'
import type { Login } from '../api/contract'
import { copy } from '../copy'

type Props = { login: (payload: Login) => Promise<void>; busy: boolean; error: string }

export function LoginScreen({ login, busy, error }: Props) {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')

  async function submit(event: FormEvent) {
    event.preventDefault()
    if (!username.trim() || !password || busy) return
    await login({ login: username.trim(), password })
    setPassword('')
  }

  return (
    <section className="sheet login">
      <h1>{copy('login.title')}</h1>
      <p>{copy('login.help')}</p>
      <form className="stack" onSubmit={submit}>
        <label>{copy('login.account')}
          <input required maxLength={128} autoComplete="username" value={username} onChange={event => setUsername(event.target.value)} />
        </label>
        <label>{copy('login.password')}
          <input required maxLength={1024} type="password" autoComplete="current-password" value={password} onChange={event => setPassword(event.target.value)} />
        </label>
        <button className="primary" disabled={busy || !username.trim() || !password}>{copy('login.submit')}</button>
      </form>
      {error && <p role="alert" className="notice danger">{error}</p>}
    </section>
  )
}
