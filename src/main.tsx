import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import App from './App'
import './pilot/styles/pilot.css'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
