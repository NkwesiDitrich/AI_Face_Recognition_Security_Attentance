import { create } from 'zustand'

interface User {
  id: string
  name: string
  employee_id: string
  access_level: string
}

interface AuthState {
  token: string | null
  user: User | null
  isAuthenticated: boolean
  setAuth: (token: string, user: User) => void
  logout: () => void
}

// Load from localStorage on init
const loadAuth = () => {
  if (typeof window === 'undefined') return { token: null, user: null }
  const token = localStorage.getItem('user_token')
  const userStr = localStorage.getItem('user_data')
  const user = userStr ? JSON.parse(userStr) : null
  return { token, user, isAuthenticated: !!token && !!user }
}

const initialAuth = loadAuth()

export const useAuthStore = create<AuthState>((set) => ({
  token: initialAuth.token,
  user: initialAuth.user,
  isAuthenticated: initialAuth.isAuthenticated,
  setAuth: (token: string, user: User) => {
    localStorage.setItem('user_token', token)
    localStorage.setItem('user_data', JSON.stringify(user))
    set({ token, user, isAuthenticated: true })
  },
  logout: () => {
    localStorage.removeItem('user_token')
    localStorage.removeItem('user_data')
    set({ token: null, user: null, isAuthenticated: false })
  },
}))
