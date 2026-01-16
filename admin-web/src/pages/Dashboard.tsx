import { useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { Users, Calendar, XCircle, AlertCircle, Activity, CheckCircle, Download } from 'lucide-react'
import { api } from '@/lib/api'
import { format } from 'date-fns'

export default function Dashboard() {
  const navigate = useNavigate()

  const { data: stats, isLoading, isError } = useQuery({
    queryKey: ['dashboard-overview'],
    queryFn: () => api.getDashboardOverview(),
    refetchInterval: 8000, // near real-time refresh
    staleTime: 4000,
  })

  const todayRange = useMemo(() => {
    const now = new Date()
    const start = new Date(now)
    start.setHours(0, 0, 0, 0)
    const end = new Date(now)
    end.setHours(23, 59, 59, 999)
    return { start: start.toISOString(), end: end.toISOString() }
  }, [])

  const handleExportToday = async () => {
    const records = await api.getAttendanceRecords({
      start_date: todayRange.start,
      end_date: todayRange.end,
    })

    const headers = ['User', 'Date', 'Time', 'Event Type', 'Liveness', 'Status', 'Device', 'Session ID']
    const rows = (records || []).map((record: any) => {
      const date = new Date(record.timestamp)
      const liveness = record.liveness_status || record.liveness
      return [
        record.user_name || 'Unknown',
        format(date, 'yyyy-MM-dd'),
        format(date, 'HH:mm:ss'),
        record.event_type || 'check_in',
        liveness === 'passed' ? 'Passed' : liveness === 'failed' ? 'Failed' : 'N/A',
        liveness === 'passed' ? 'Success' : 'Failed',
        record.device_id || 'N/A',
        record.session_id || 'N/A',
      ]
    })

    const csvContent = [headers.join(','), ...rows.map((row: any[]) => row.map((cell) => `"${cell}"`).join(','))].join('\n')
    const blob = new Blob([csvContent], { type: 'text/csv' })
    const url = window.URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `attendance-today-${format(new Date(), 'yyyy-MM-dd')}.csv`
    a.click()
    window.URL.revokeObjectURL(url)
  }

  const statsCards = [
    {
      title: 'Total Registered Users',
      value: stats?.total_users || 0,
      icon: Users,
      color: 'bg-blue-500',
      textColor: 'text-blue-600',
      bgColor: 'bg-blue-50',
    },
    {
      title: "Today's Attendance",
      value: stats?.today_attendance_count || 0,
      icon: Calendar,
      color: 'bg-green-500',
      textColor: 'text-green-600',
      bgColor: 'bg-green-50',
    },
    {
      title: 'Currently Checked In',
      value: stats?.currently_checked_in_users || 0,
      icon: CheckCircle,
      color: 'bg-purple-500',
      textColor: 'text-purple-600',
      bgColor: 'bg-purple-50',
    },
    {
      title: 'Failed Recognition (Today)',
      value: stats?.failed_recognition_today || 0,
      icon: XCircle,
      color: 'bg-red-500',
      textColor: 'text-red-600',
      bgColor: 'bg-red-50',
    },
    {
      title: 'Failed Liveness (Today)',
      value: stats?.failed_liveness_today || 0,
      icon: AlertCircle,
      color: 'bg-orange-500',
      textColor: 'text-orange-600',
      bgColor: 'bg-orange-50',
    },
    {
      title: 'System Status',
      value: stats?.system_status || 'online',
      icon: Activity,
      color: stats?.system_status === 'online' ? 'bg-green-500' : stats?.system_status === 'degraded' ? 'bg-yellow-500' : 'bg-red-500',
      textColor: stats?.system_status === 'online' ? 'text-green-600' : stats?.system_status === 'degraded' ? 'text-yellow-600' : 'text-red-600',
      bgColor: stats?.system_status === 'online' ? 'bg-green-50' : stats?.system_status === 'degraded' ? 'bg-yellow-50' : 'bg-red-50',
    },
  ]

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold text-gray-900">Dashboard</h1>
          <p className="mt-1 text-sm text-gray-600">
            Welcome back! Here's what's happening with your attendance system.
          </p>
        </div>
        <div className="flex space-x-3">
          <button onClick={handleExportToday} className="btn btn-secondary">
            <Download className="w-4 h-4 mr-2" />
            Export Today's Report
          </button>
        </div>
      </div>

      {/* Stats Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        {isLoading && (
          <div className="card md:col-span-2 lg:col-span-3">
            <div className="text-center py-8 text-gray-500">Loading dashboard data...</div>
          </div>
        )}
        {isError && (
          <div className="card md:col-span-2 lg:col-span-3">
            <div className="text-center py-8 text-red-600">Failed to load dashboard data. Check backend logs.</div>
          </div>
        )}
        {statsCards.map((card, index) => {
          const Icon = card.icon
          return (
            <div key={index} className="card hover:shadow-lg transition-shadow">
              <div className="flex items-center justify-between">
                <div className="flex-1">
                  <p className="text-sm font-medium text-gray-600 mb-1">{card.title}</p>
                  <p className={`text-3xl font-bold ${card.textColor}`}>
                    {typeof card.value === 'number' ? card.value.toLocaleString() : card.value}
                  </p>
                </div>
                <div className={`${card.bgColor} p-3 rounded-lg`}>
                  <Icon className={`w-6 h-6 ${card.textColor}`} />
                </div>
              </div>
            </div>
          )
        })}
      </div>

      {/* Recent Activity */}
      <div className="card">
        <div className="flex items-center justify-between mb-6">
          <h2 className="text-xl font-bold text-gray-900">Recent Activity</h2>
          <button
            className="text-sm text-primary-600 hover:text-primary-700 font-medium"
            onClick={() => navigate('/attendance')}
          >
            View Attendance
          </button>
        </div>
        <div className="space-y-4">
          {stats?.recent_activity && stats.recent_activity.length > 0 ? (
            stats.recent_activity.map((activity: any, index: number) => (
              <div key={index} className="flex items-center space-x-4 p-4 bg-gray-50 rounded-lg">
                <div className="flex-shrink-0">
                  <div className="w-10 h-10 bg-primary-100 rounded-full flex items-center justify-center">
                    <Activity className="w-5 h-5 text-primary-600" />
                  </div>
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium text-gray-900">
                    {activity.user_name ? `${activity.user_name} — ` : ''}{activity.title}
                  </p>
                  <p className="text-xs text-gray-500">
                    {activity.timestamp ? format(new Date(activity.timestamp), 'PPpp') : ''}
                  </p>
                </div>
                <div className="flex-shrink-0">
                  <span className={`badge ${activity.status === 'failed' ? 'badge-danger' : activity.status === 'success' ? 'badge-success' : 'badge-info'}`}>
                    {activity.status || 'info'}
                  </span>
                </div>
              </div>
            ))
          ) : (
            <div className="text-center py-12 text-gray-500">
              <Activity className="w-12 h-12 mx-auto mb-3 text-gray-400" />
              <p>No recent activity</p>
            </div>
          )}
        </div>
      </div>

      {/* Quick Actions */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <button onClick={() => navigate('/users')} className="card hover:shadow-lg transition-shadow text-left group">
          <Users className="w-8 h-8 text-primary-600 mb-3 group-hover:scale-110 transition-transform" />
          <h3 className="text-lg font-semibold text-gray-900 mb-2">Register New User</h3>
          <p className="text-sm text-gray-600">Add a new user to the system</p>
        </button>
        <button onClick={() => navigate('/attendance')} className="card hover:shadow-lg transition-shadow text-left group">
          <Calendar className="w-8 h-8 text-green-600 mb-3 group-hover:scale-110 transition-transform" />
          <h3 className="text-lg font-semibold text-gray-900 mb-2">View Today's Attendance</h3>
          <p className="text-sm text-gray-600">See all attendance records for today</p>
        </button>
        <button className="card hover:shadow-lg transition-shadow text-left group" disabled>
          <AlertCircle className="w-8 h-8 text-orange-600 mb-3 group-hover:scale-110 transition-transform" />
          <h3 className="text-lg font-semibold text-gray-900 mb-2">Send Announcement</h3>
          <p className="text-sm text-gray-600">Coming next (Level 2 - Notifications & Messaging)</p>
        </button>
      </div>
    </div>
  )
}