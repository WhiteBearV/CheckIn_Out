import { BrowserRouter, Routes, Route } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ThemeProvider } from './context/ThemeContext'
import Sidebar from './components/Sidebar'
import LiveCam from './pages/LiveCam'
import Dashboard from './pages/Dashboard'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 10_000,
      retry: 1,
    },
  },
})

function PlaceholderPage({ title }) {
  return (
    <div className="p-8 flex items-center justify-center h-full">
      <div className="text-center">
        <p className="font-mono text-xs uppercase tracking-widest mb-3"
          style={{ color: 'var(--c-accent)' }}>
          Coming Soon
        </p>
        <p className="text-xl font-light" style={{ color: 'var(--c-text-2)' }}>{title}</p>
      </div>
    </div>
  )
}

function Layout() {
  return (
    <div className="flex min-h-screen" style={{ background: 'var(--c-bg-app)', color: 'var(--c-text)' }}>
      <Sidebar />
      <main className="flex-1 min-w-0 overflow-auto">
        <Routes>
          <Route path="/"          element={<LiveCam />} />
          <Route path="/live"      element={<LiveCam />} />
          <Route path="/dashboard" element={<Dashboard />} />
          <Route path="/history"   element={<PlaceholderPage title="ประวัติลงเวลา" />} />
          <Route path="/reports"   element={<PlaceholderPage title="รายงาน" />} />
        </Routes>
      </main>
    </div>
  )
}

export default function App() {
  return (
    <ThemeProvider>
      <QueryClientProvider client={queryClient}>
        <BrowserRouter>
          <Layout />
        </BrowserRouter>
      </QueryClientProvider>
    </ThemeProvider>
  )
}
