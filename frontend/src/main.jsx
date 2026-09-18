import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App'
import './styles/index.css'

// Apply the saved/system preference before React paints to avoid a theme flash.
const initialTheme = localStorage.getItem('netmonitor.theme') || 'system'
const effectiveTheme = initialTheme === 'system'
  ? (window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light')
  : initialTheme
document.documentElement.dataset.theme = effectiveTheme
document.documentElement.style.colorScheme = effectiveTheme

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
)
