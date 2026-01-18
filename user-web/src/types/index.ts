export interface User {
  id: string
  name: string
  employee_id: string
  access_level: string
  status: string
  enrollment_status: 'not_enrolled' | 'enrolled' | 'needs_re_enrollment'
}

export interface AttendanceRecord {
  id: string
  date: string
  check_in_time: string | null
  check_out_time: string | null
  status: 'present' | 'failed' | 'late' | 'absent'
  event_type: 'check_in' | 'check_out'
}

export interface Message {
  id: string
  title: string
  content: string
  message_type: 'info' | 'warning' | 'instruction'
  sender_name: string
  created_at: string
  read: boolean
  read_at: string | null
}
