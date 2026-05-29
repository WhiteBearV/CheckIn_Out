import { StrictMode, Component } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.jsx'

class ErrorBoundary extends Component {
  constructor(props) { super(props); this.state = { error: null } }
  static getDerivedStateFromError(error) { return { error } }
  render() {
    if (this.state.error) {
      return (
        <div style={{ padding: 32, fontFamily: 'monospace', color: '#ff6b6b', background: '#0f0f0f', minHeight: '100vh' }}>
          <p style={{ color: '#00ffff', marginBottom: 8, fontSize: 11, letterSpacing: 2, textTransform: 'uppercase' }}>
            Runtime Error
          </p>
          <p style={{ fontSize: 14, marginBottom: 16 }}>{this.state.error.message}</p>
          <pre style={{ fontSize: 11, color: 'rgba(255,255,255,0.35)', whiteSpace: 'pre-wrap' }}>
            {this.state.error.stack}
          </pre>
          <button
            style={{ marginTop: 24, padding: '8px 20px', border: '1px solid rgba(0,255,255,0.30)', color: '#00ffff', background: 'transparent', cursor: 'pointer', fontFamily: 'monospace', fontSize: 11 }}
            onClick={() => window.location.reload()}
          >
            Reload
          </button>
        </div>
      )
    }
    return this.props.children
  }
}

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <ErrorBoundary>
      <App />
    </ErrorBoundary>
  </StrictMode>,
)
