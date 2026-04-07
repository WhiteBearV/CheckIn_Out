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
    <div className="p-6 flex items-center justify-center h-full">
      <div className="text-center text-slate-400 dark:text-slate-500">
        <p className="text-lg font-medium">{title}</p>
        <p className="text-sm mt-1">Coming soon</p>
      </div>
    </div>
  )
}

function Layout() {
  return (
    <div className="flex min-h-screen bg-slate-50 dark:bg-slate-950">
      <Sidebar />
      <main className="flex-1 min-w-0 overflow-auto">
        <Routes>
          <Route path="/live" element={<LiveCam />} />
          <Route path="/"    element={<Dashboard />} />
          <Route path="/history" element={<PlaceholderPage title="ประวัติลงเวลา" />} />
          <Route path="/reports" element={<PlaceholderPage title="รายงาน" />} />
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
