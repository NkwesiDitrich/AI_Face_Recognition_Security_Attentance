import { useQuery } from '@tanstack/react-query'
import { Users, Calendar, XCircle, AlertCircle, Activity, CheckCircle } from 'lucide-react'
import { api } from '@/lib/api'

export default function Dashboard() {
  const { data: stats } = useQuery({
    queryKey: ['dashboard-stats'],
    queryFn: async () => {
      // This will need backend endpoints - for now return mock data structure
      return {
        totalUsers: 0,
        todayAttendance: 0,
        currentCheckedIn: 0,
        failedRecognitionToday: 0,
        failedLivenessToday: 0,
        systemStatus: 'online' as 'online' | 'degraded' | 'offline',
        recentActivity: []
      }
    }
  })

  const statsCards = [
    {
      title: 'Total Registered Users',
      value: stats?.totalUsers || 0,
      icon: Users,
      color: 'bg-blue-500',
      textColor: 'text-blue-600',
      bgColor: 'bg-blue-50',
    },
    {
      title: "Today's Attendance",
      value: stats?.todayAttendance || 0,
      icon: Calendar,
      color: 'bg-green-500',
      textColor: 'text-green-600',
      bgColor: 'bg-green-50',
    },
    {
      title: 'Currently Checked In',
      value: stats?.currentCheckedIn || 0,
      icon: CheckCircle,
      color: 'bg-purple-500',
      textColor: 'text-purple-600',
      bgColor: 'bg-purple-50',
    },
    {
      title: 'Failed Recognition (Today)',
      value: stats?.failedRecognitionToday || 0,
      icon: XCircle,
      color: 'bg-red-500',
      textColor: 'text-red-600',
      bgColor: 'bg-red-50',
    },
    {
      title: 'Failed Liveness (Today)',
      value: stats?.failedLivenessToday || 0,
      icon: AlertCircle,
      color: 'bg-orange-500',
      textColor: 'text-orange-600',
      bgColor: 'bg-orange-50',
    },
    {
      title: 'System Status',
      value: stats?.systemStatus || 'online',
      icon: Activity,
      color: stats?.systemStatus === 'online' ? 'bg-green-500' : stats?.systemStatus === 'degraded' ? 'bg-yellow-500' : 'bg-red-500',
      textColor: stats?.systemStatus === 'online' ? 'text-green-600' : stats?.systemStatus === 'degraded' ? 'text-yellow-600' : 'text-red-600',
      bgColor: stats?.systemStatus === 'online' ? 'bg-green-50' : stats?.systemStatus === 'degraded' ? 'bg-yellow-50' : 'bg-red-50',
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
          <button className="btn btn-secondary">
            Export Today's Report
          </button>
        </div>
      </div>

      {/* Stats Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
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
          <button className="text-sm text-primary-600 hover:text-primary-700 font-medium">
            View All
          </button>
        </div>
        <div className="space-y-4">
          {stats?.recentActivity && stats.recentActivity.length > 0 ? (
            stats.recentActivity.map((activity: any, index: number) => (
              <div key={index} className="flex items-center space-x-4 p-4 bg-gray-50 rounded-lg">
                <div className="flex-shrink-0">
                  <div className="w-10 h-10 bg-primary-100 rounded-full flex items-center justify-center">
                    <Activity className="w-5 h-5 text-primary-600" />
                  </div>
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium text-gray-900">{activity.title}</p>
                  <p className="text-xs text-gray-500">{activity.timestamp}</p>
                </div>
                <div className="flex-shrink-0">
                  <span className={`badge badge-${activity.type || 'info'}`}>
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
        <button className="card hover:shadow-lg transition-shadow text-left group">
          <Users className="w-8 h-8 text-primary-600 mb-3 group-hover:scale-110 transition-transform" />
          <h3 className="text-lg font-semibold text-gray-900 mb-2">Register New User</h3>
          <p className="text-sm text-gray-600">Add a new user to the system</p>
        </button>
        <button className="card hover:shadow-lg transition-shadow text-left group">
          <Calendar className="w-8 h-8 text-green-600 mb-3 group-hover:scale-110 transition-transform" />
          <h3 className="text-lg font-semibold text-gray-900 mb-2">View Today's Attendance</h3>
          <p className="text-sm text-gray-600">See all attendance records for today</p>
        </button>
        <button className="card hover:shadow-lg transition-shadow text-left group">
          <AlertCircle className="w-8 h-8 text-orange-600 mb-3 group-hover:scale-110 transition-transform" />
          <h3 className="text-lg font-semibold text-gray-900 mb-2">Send Announcement</h3>
          <p className="text-sm text-gray-600">Broadcast a message to all users</p>
        </button>
      </div>
    </div>
  )
}