import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { api } from '@/lib/api'
import { Calendar, Clock, CheckCircle, XCircle, ArrowRight, MessageSquare, User } from 'lucide-react'
import { format, isToday, startOfWeek, endOfWeek, startOfMonth, endOfMonth } from 'date-fns'

export default function Dashboard() {
  const { data: attendance = [] } = useQuery({
    queryKey: ['attendance'],
    queryFn: () => api.getAttendance({ limit: 100 }),
    refetchInterval: 30000, // Refresh every 30 seconds for real-time data
  })

  const { data: messages = [] } = useQuery({
    queryKey: ['messages'],
    queryFn: () => api.getMessages({ limit: 5 }),
  })

  // Calculate statistics
  const todayAttendance = attendance.filter((record: any) => {
    const recordDate = new Date(record.date)
    return isToday(recordDate) && record.status === 'present'
  })

  const thisWeekStart = startOfWeek(new Date(), { weekStartsOn: 1 })
  const thisWeekEnd = endOfWeek(new Date(), { weekStartsOn: 1 })
  const thisWeekAttendance = attendance.filter((record: any) => {
    const recordDate = new Date(record.date)
    return recordDate >= thisWeekStart && recordDate <= thisWeekEnd && record.status === 'present'
  })

  const thisMonthStart = startOfMonth(new Date())
  const thisMonthEnd = endOfMonth(new Date())
  const thisMonthAttendance = attendance.filter((record: any) => {
    const recordDate = new Date(record.date)
    return recordDate >= thisMonthStart && recordDate <= thisMonthEnd && record.status === 'present'
  })
  const thisMonthTotal = attendance.filter((record: any) => {
    const recordDate = new Date(record.date)
    return recordDate >= thisMonthStart && recordDate <= thisMonthEnd
  }).length
  const attendancePercentage = thisMonthTotal > 0 
    ? Math.round((thisMonthAttendance.length / thisMonthTotal) * 100) 
    : 0

  // Get last check-in time
  const lastCheckIn = attendance
    .filter((r: any) => r.check_in_time && r.status === 'present')
    .sort((a: any, b: any) => new Date(b.check_in_time).getTime() - new Date(a.check_in_time).getTime())[0]

  // Today's status
  const todayStatus = todayAttendance.length > 0 ? 'present' : 'absent'
  const todayRecord = attendance.find((r: any) => {
    const recordDate = new Date(r.date)
    return isToday(recordDate)
  })

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-3xl font-bold text-gray-900">Dashboard</h1>
        <p className="mt-1 text-sm text-gray-600">Welcome back! Here's your attendance overview.</p>
      </div>

      {/* Today's Status Card */}
      <div className="card">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-lg font-semibold text-gray-900 mb-2">Today's Attendance</h2>
            <div className="flex items-center space-x-4">
              {todayStatus === 'present' ? (
                <div className="flex items-center space-x-2 text-green-600">
                  <CheckCircle className="w-6 h-6" />
                  <span className="text-xl font-bold">Present</span>
                </div>
              ) : (
                <div className="flex items-center space-x-2 text-gray-500">
                  <XCircle className="w-6 h-6" />
                  <span className="text-xl font-bold">Not Checked In</span>
                </div>
              )}
            </div>
            {lastCheckIn && (
              <p className="mt-2 text-sm text-gray-600">
                Last check-in: {format(new Date(lastCheckIn.check_in_time), 'PPp')}
              </p>
            )}
          </div>
          <div className="text-4xl">
            {todayStatus === 'present' ? '✅' : '⏰'}
          </div>
        </div>
      </div>

      {/* Summary Cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <div className="card">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm text-gray-600 mb-1">This Week</p>
              <p className="text-2xl font-bold text-gray-900">{thisWeekAttendance.length} days</p>
              <p className="text-xs text-gray-500 mt-1">Present this week</p>
            </div>
            <Calendar className="w-12 h-12 text-primary-500" />
          </div>
        </div>

        <div className="card">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm text-gray-600 mb-1">This Month</p>
              <p className="text-2xl font-bold text-gray-900">{attendancePercentage}%</p>
              <p className="text-xs text-gray-500 mt-1">
                {thisMonthAttendance.length} of {thisMonthTotal} days
              </p>
            </div>
            <CheckCircle className="w-12 h-12 text-green-500" />
          </div>
        </div>

        <div className="card">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm text-gray-600 mb-1">Unread Messages</p>
              <p className="text-2xl font-bold text-gray-900">
                {messages.filter((m: any) => !m.read).length}
              </p>
              <p className="text-xs text-gray-500 mt-1">New messages</p>
            </div>
            <MessageSquare className="w-12 h-12 text-blue-500" />
          </div>
        </div>
      </div>

      {/* Quick Actions */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <Link
          to="/attendance"
          className="card hover:shadow-md transition-shadow cursor-pointer"
        >
          <div className="flex items-center justify-between">
            <div>
              <h3 className="text-lg font-semibold text-gray-900 mb-1">View Full Attendance</h3>
              <p className="text-sm text-gray-600">See your complete attendance history</p>
            </div>
            <ArrowRight className="w-6 h-6 text-primary-600" />
          </div>
        </Link>

        <Link
          to="/messages"
          className="card hover:shadow-md transition-shadow cursor-pointer"
        >
          <div className="flex items-center justify-between">
            <div>
              <h3 className="text-lg font-semibold text-gray-900 mb-1">Messages</h3>
              <p className="text-sm text-gray-600">View messages from admins</p>
            </div>
            <ArrowRight className="w-6 h-6 text-primary-600" />
          </div>
        </Link>
      </div>

      {/* Recent Activity */}
      <div className="card">
        <h3 className="text-lg font-semibold text-gray-900 mb-4">Recent Activity</h3>
        {attendance.length === 0 ? (
          <p className="text-gray-500 text-center py-8">No attendance records yet</p>
        ) : (
          <div className="space-y-3">
            {attendance.slice(0, 5).map((record: any) => (
              <div
                key={record.id}
                className="flex items-center justify-between p-3 bg-gray-50 rounded-lg"
              >
                <div className="flex items-center space-x-3">
                  <div className={`w-2 h-2 rounded-full ${
                    record.status === 'present' ? 'bg-green-500' : 'bg-red-500'
                  }`} />
                  <div>
                    <p className="text-sm font-medium text-gray-900">
                      {format(new Date(record.date), 'EEEE, MMMM d, yyyy')}
                    </p>
                    {record.check_in_time && (
                      <p className="text-xs text-gray-500">
                        Check-in: {format(new Date(record.check_in_time), 'h:mm a')}
                      </p>
                    )}
                  </div>
                </div>
                <span className={`badge ${
                  record.status === 'present' ? 'badge-success' : 'badge-danger'
                }`}>
                  {record.status}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
