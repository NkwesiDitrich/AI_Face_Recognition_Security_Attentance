import axios from 'axios'

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

class ApiClient {
  private client = axios.create({
    baseURL: API_BASE_URL,
    headers: {
      'Content-Type': 'application/json',
    },
  })

  constructor() {
    // Add auth token to requests
    this.client.interceptors.request.use((config) => {
      const token = localStorage.getItem('user_token')
      if (token) {
        config.headers.Authorization = `Bearer ${token}`
      }
      return config
    })

    // Handle 401 errors
    this.client.interceptors.response.use(
      (response) => response,
      (error) => {
        if (error.response?.status === 401) {
          localStorage.removeItem('user_token')
          localStorage.removeItem('user_data')
          window.location.href = '/login'
        }
        return Promise.reject(error)
      }
    )
  }

  // User Portal Endpoints
  async checkUser(userId: string) {
    const response = await this.client.post('/api/v1/user-portal/check-user', { user_id: userId })
    return response.data
  }

  async setupPassword(data: { user_id: string; password: string; confirm_password: string }) {
    const response = await this.client.post('/api/v1/user-portal/setup-password', data)
    return response.data
  }

  async login(data: { user_id: string; password: string }) {
    const response = await this.client.post('/api/v1/user-portal/login', data)
    return response.data
  }

  async getProfile() {
    const response = await this.client.get('/api/v1/user-portal/profile')
    return response.data
  }

  async getAttendance(params?: { start_date?: string; end_date?: string; limit?: number }) {
    const response = await this.client.get('/api/v1/user-portal/attendance', { params })
    return response.data.attendance || []
  }

  async getMessages(params?: { limit?: number }) {
    const response = await this.client.get('/api/v1/user-portal/messages', { params })
    return response.data.messages || []
  }

  async markMessageAsRead(messageId: string) {
    const response = await this.client.post(`/api/v1/user-portal/messages/${messageId}/read`)
    return response.data
  }

  async changePassword(data: { old_password: string; new_password: string; confirm_password: string }) {
    const response = await this.client.post('/api/v1/user-portal/change-password', data)
    return response.data
  }
}

export const api = new ApiClient()
