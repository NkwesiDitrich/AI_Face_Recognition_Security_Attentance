// Admin Types
export type AdminRole = 'super_admin' | 'admin' | 'viewer'

export interface Admin {
  id: string
  email: string
  name: string
  role: AdminRole
  createdAt: string
  lastLoginAt?: string
}

export interface AuthResponse {
  access_token: string
  token_type: string
  admin: Admin
}

// User Types
export type AccessLevel = 'employee' | 'admin' | 'manager'
export type EnrollmentStatus = 'not_enrolled' | 'enrolled' | 'needs_re_enrollment'
export type UserStatus = 'active' | 'inactive'

export interface User {
  id: string
  name: string
  employee_id: string
  access_level: AccessLevel
  status?: UserStatus
  enrollment_status?: EnrollmentStatus
  enrollment_date?: string
  enrollment_device?: string
  enrollment_attempts?: number
  createdAt?: string
  updatedAt?: string
}

export interface UserCreate {
  name: string
  employee_id: string
  access_level: AccessLevel
}

export interface UserUpdate {
  name?: string
  employee_id?: string
  access_level?: AccessLevel
  status?: UserStatus
}

// Attendance Types
export type EventType = 'check_in' | 'check_out'
export type AttendanceStatus = 'success' | 'failed'

export interface AttendanceRecord {
  id: string
  user_id: string
  user_name?: string
  event_type: EventType
  status: AttendanceStatus
  liveness_status?: 'passed' | 'failed'
  device_id?: string
  session_id?: string
  timestamp: string
  confidence?: number
  distance?: number
  attempts_used?: number
  total_duration_ms?: number
}

// Enrollment Types
export interface EnrollmentLog {
  id: string
  user_id: string
  stage: 'started' | 'completed' | 'reset' | 'failed'
  timestamp: string
  initiated_by?: string
  device_id?: string
  embedding_size?: number
  model_version?: string
  duration_ms?: number
  reason?: string
  admin_id?: string
}

// Recognition Types
export interface RecognitionLog {
  id: string
  session_id: string
  user_id?: string
  stage: 'started' | 'success' | 'failed'
  timestamp: string
  device_id?: string
  confidence?: number
  distance?: number
  duration_ms?: number
  reason?: string
}

// Liveness Types
export interface LivenessLog {
  id: string
  session_id: string
  user_id?: string
  stage: 'started' | 'attempt' | 'passed' | 'failed'
  timestamp: string
  device_id?: string
  attempts_used?: number
  attempt_number?: number
  failed_action?: string
  final_failed_action?: string
  actions_requested?: string[]
  duration_ms?: number
  reason?: string
}