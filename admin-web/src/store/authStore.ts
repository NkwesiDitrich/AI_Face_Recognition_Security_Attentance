import { create } from 'zustand'
import type { Admin, AdminRole } from '@/types'
import { api } from '@/lib/api'

interface AuthState {
  admin: Admin | null
  token: string | null
  isAuthenticated: boolean
  isLoading: boolean
  login: (email: string, password: string) => Promise<void>
  logout: () => Promise<void>
  checkAuth: () => Promise<void>
  hasPermission: (requiredRole: AdminRole) => boolean
}

const roleHierarchy: Record<AdminRole, number> = {
  super_admin: 3,
  admin: 2,
  viewer: 1,
}

export const useAuthStore = create<AuthState>((set, get) => ({
  admin: (() => {
    const adminData = localStorage.getItem('admin_data')
    return adminData ? JSON.parse(adminData) : null
  })(),
  token: localStorage.getItem('admin_token'),
  isAuthenticated: !!localStorage.getItem('admin_token'),
  isLoading: true,

  login: async (email: string, password: string) => {
    try {
      const response = await api.login(email, password)
      const { access_token, admin } = response
      
      localStorage.setItem('admin_token', access_token)
      localStorage.setItem('admin_data', JSON.stringify(admin))
      
      set({
        admin,
        token: access_token,
        isAuthenticated: true,
        isLoading: false,
      })
    } catch (error) {
      set({ isLoading: false })
      throw error
    }
  },

  logout: async () => {
    try {
      await api.logout()
    } catch (error) {
      console.error('Logout error:', error)
    } finally {
      localStorage.removeItem('admin_token')
      localStorage.removeItem('admin_data')
      set({
        admin: null,
        token: null,
        isAuthenticated: false,
        isLoading: false,
      })
    }
  },

  checkAuth: async () => {
    const token = localStorage.getItem('admin_token')
    const adminData = localStorage.getItem('admin_data')
    
    if (!token || !adminData) {
      set({ isAuthenticated: false, isLoading: false })
      return
    }

    try {
      const admin = await api.getCurrentAdmin()
      localStorage.setItem('admin_data', JSON.stringify(admin))
      set({
        admin,
        token,
        isAuthenticated: true,
        isLoading: false,
      })
    } catch (error) {
      localStorage.removeItem('admin_token')
      localStorage.removeItem('admin_data')
      set({
        admin: null,
        token: null,
        isAuthenticated: false,
        isLoading: false,
      })
    }
  },

  hasPermission: (requiredRole: AdminRole) => {
    const { admin } = get()
    if (!admin) return false
    
    const userRoleLevel = roleHierarchy[admin.role] || 0
    const requiredRoleLevel = roleHierarchy[requiredRole] || 0
    
    return userRoleLevel >= requiredRoleLevel
  },
}))