import axios, { AxiosInstance, InternalAxiosRequestConfig } from 'axios'

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

class ApiClient {
  private client: AxiosInstance

  constructor() {
    this.client = axios.create({
      baseURL: API_BASE_URL,
      headers: {
        'Content-Type': 'application/json',
      },
    })

    // Request interceptor to add auth token
    this.client.interceptors.request.use(
      (config: InternalAxiosRequestConfig) => {
        const token = localStorage.getItem('admin_token')
        if (token && config.headers) {
          config.headers.Authorization = `Bearer ${token}`
        }
        return config
      },
      (error) => Promise.reject(error)
    )

    // Response interceptor to handle errors
    this.client.interceptors.response.use(
      (response) => response,
      (error) => {
        if (error.response?.status === 401) {
          // Unauthorized - clear token and redirect to login
          localStorage.removeItem('admin_token')
          localStorage.removeItem('admin_data')
          window.location.href = '/login'
        }
        return Promise.reject(error)
      }
    )
  }

  // Auth endpoints
  async login(email: string, password: string) {
    const response = await this.client.post('/api/v1/admin/auth/login', {
      email,
      password,
    })
    return response.data
  }

  async logout() {
    await this.client.post('/api/v1/admin/auth/logout')
  }

  async getCurrentAdmin() {
    const response = await this.client.get('/api/v1/admin/auth/me')
    return response.data
  }

  async forgotPassword(email: string) {
    const response = await this.client.post('/api/v1/admin/auth/forgot-password', {
      email,
    })
    return response.data
  }

  async resetPassword(email: string, newPassword: string) {
    const response = await this.client.post('/api/v1/admin/auth/reset-password', {
      email,
      new_password: newPassword,
    })
    return response.data
  }

  // User endpoints
  async getUsers(params?: { search?: string; status?: string; role?: string }) {
    const queryParams: any = {}
    if (params?.search) queryParams.search = params.search
    if (params?.status) queryParams.status = params.status
    if (params?.role) queryParams.role = params.role  // Fixed: send 'role' instead of 'access_level'
    const response = await this.client.get('/api/v1/admin/users', { params: queryParams })
    // Backend returns {users: [], total: ...}, extract the users array
    return response.data.users || []
  }

  async getUserById(id: string) {
    const response = await this.client.get(`/api/v1/admin/users/${id}`)
    return response.data
  }

  async createUser(data: { name: string; employee_id: string; access_level: string }) {
    const response = await this.client.post('/api/v1/admin/users', data)
    return response.data
  }

  async updateUser(id: string, data: Partial<{ name: string; employee_id: string; access_level: string; status: string }>) {
    const response = await this.client.put(`/api/v1/admin/users/${id}`, data)
    return response.data
  }

  async deleteUser(id: string) {
    const response = await this.client.delete(`/api/v1/admin/users/${id}`)
    return response.data
  }

  async getUserEnrollmentStatus(id: string) {
    const response = await this.client.get(`/api/v1/admin/users/${id}/enrollment`)
    return response.data
  }

  async forceReEnrollment(id: string) {
    const response = await this.client.post(`/api/v1/admin/users/${id}/re-enroll`)
    return response.data
  }

  async bulkImportUsers(file: File) {
    const formData = new FormData()
    formData.append('file', file)
    const response = await this.client.post('/api/v1/admin/users/bulk-import', formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    })
    return response.data
  }

  // Attendance endpoints
  async getAttendanceRecords(params?: {
    start_date?: string
    end_date?: string
    user_id?: string
    status?: string
    limit?: number
    offset?: number
  }) {
    const response = await this.client.get('/api/v1/admin/attendance', { params })
    // Backend returns {records: [], total: ...}, extract the records array
    return response.data.records || []
  }

  async getAttendanceRecordById(id: string) {
    const response = await this.client.get(`/api/v1/admin/attendance/${id}`)
    return response.data
  }

  // Logs endpoints
  async getEnrollmentLogs(params?: { user_id?: string; limit?: number }) {
    const response = await this.client.get('/api/v1/admin/logs/enrollment', { params })
    return response.data
  }

  async getRecognitionLogs(params?: { session_id?: string; limit?: number }) {
    const response = await this.client.get('/api/v1/admin/logs/recognition', { params })
    return response.data
  }

  async getLivenessLogs(params?: { session_id?: string; limit?: number }) {
    const response = await this.client.get('/api/v1/admin/logs/liveness', { params })
    return response.data
  }

  async getAdminActionLogs(params?: { admin_id?: string; limit?: number }) {
    const response = await this.client.get('/api/v1/admin/logs/admin-actions', { params })
    return response.data
  }

  // Dashboard (Level 2 - Overview)
  async getDashboardOverview() {
    const response = await this.client.get('/api/v1/admin/dashboard/overview')
    return response.data
  }

  // Notification endpoints
  async getNotifications(params?: { unread_only?: boolean; limit?: number }) {
    const response = await this.client.get('/api/v1/admin/notifications', { params })
    return response.data
  }

  async getUnreadNotificationCount() {
    const response = await this.client.get('/api/v1/admin/notifications/unread-count')
    return response.data.count
  }

  async markNotificationAsRead(notificationId: string) {
    const response = await this.client.post(`/api/v1/admin/notifications/${notificationId}/read`)
    return response.data
  }

  async markAllNotificationsAsRead() {
    const response = await this.client.post('/api/v1/admin/notifications/mark-all-read')
    return response.data
  }

  // Message endpoints
  async sendMessage(data: {
    title: string
    content: string
    message_type: 'info' | 'warning' | 'instruction'
    target_type: 'all_users' | 'group' | 'single_user'
    target_ids: string[]
  }) {
    const response = await this.client.post('/api/v1/admin/messages/send', data)
    return response.data
  }

  async getMessages(params?: { limit?: number }) {
    const response = await this.client.get('/api/v1/admin/messages', { params })
    return response.data
  }

  async getMessageDeliveryStatus(messageId: string) {
    const response = await this.client.get(`/api/v1/admin/messages/${messageId}/delivery-status`)
    return response.data
  }
}

export const api = new ApiClient()