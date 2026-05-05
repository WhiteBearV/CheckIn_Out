import { createContext, useContext, useEffect, useState } from 'react'
import { Navigate, useLocation } from 'react-router-dom'
import { me, getToken, clearToken } from '../api/client'

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [user,    setUser]    = useState(null)   // { username, role } | null
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    (async () => {
      if (!getToken()) {
        setLoading(false)
        return
      }
      try {
        const u = await me()
        if (u) setUser(u)
        else   clearToken()
      } catch {
        clearToken()
      } finally {
        setLoading(false)
      }
    })()
  }, [])

  const value = {
    user,
    loading,
    isAdmin:  user?.role === 'admin',
    isViewer: user?.role === 'viewer',
    setUser,
    logout: () => {
      clearToken()
      setUser(null)
      window.location.href = '/login'
    },
  }

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used inside <AuthProvider>')
  return ctx
}

export function RequireAuth({ children }) {
  const { user, loading } = useAuth()
  const loc = useLocation()

  if (loading) {
    return (
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center',
                    height: '100vh', color: 'var(--c-text-3)', fontSize: 13 }}>
        กำลังตรวจสอบสิทธิ์…
      </div>
    )
  }
  if (!user) return <Navigate to="/login" replace state={{ from: loc.pathname }} />
  return children
}
