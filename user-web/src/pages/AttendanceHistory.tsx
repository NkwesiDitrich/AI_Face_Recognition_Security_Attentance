import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api } from '@/lib/api'
import { format, startOfWeek, endOfWeek, startOfMonth, endOfMonth } from 'date-fns'
import { Calendar, Download, RefreshCw, CheckCircle, XCircle } from 'lucide-react'

export default function AttendanceHistory() {
  const [dateFilter, setDateFilter] = useState<'all' | 'today' | 'week' | 'month' | 'custom'>('all')
  const [startDate, setStartDate] = useState('')
  const [endDate, setEndDate] = useState('')

  const getDateRange = () => {
    const now = new Date()
    switch (dateFilter) {
      case 'today':
        const today = format(now, 'yyyy-MM-dd')
        return { start_date: today, end_date: today }
      case 'week':
        const weekStart = format(startOfWeek(now, { weekStartsOn: 1 }), 'yyyy-MM-dd')
        const weekEnd = format(endOfWeek(now, { weekStartsOn: 1 }), 'yyyy-MM-dd')
        return { start_date: weekStart, end_date: weekEnd }
      case 'month':
        const monthStart = format(startOfMonth(now), 'yyyy-MM-dd')
        const monthEnd = format(endOfMonth(now), 'yyyy-MM-dd')
        return { start_date: monthStart, end_date: monthEnd }
      case 'custom':
        return { start_date: startDate, end_date: endDate }
      default:
        return {}
    }
  }

  const { data: attendance = [], isLoading, refetch } = useQuery({
    queryKey: ['attendance', dateFilter, startDate, endDate],
    queryFn: () => api.getAttendance({ ...getDateRange(), limit: 200 }),
  })

  const handleExport = () => {
    // Simple CSV export
    const headers = ['Date', 'Check-in Time', 'Check-out Time', 'Status']
    const rows = attendance.map((record: any) => [
      format(new Date(record.date), 'yyyy-MM-dd'),
      record.check_in_time ? format(new Date(record.check_in_time), 'HH:mm:ss') : '-',
      record.check_out_time ? format(new Date(record.check_out_time), 'HH:mm:ss') : '-',
      record.status,
    ])

    const csv = [headers, ...rows].map(row => row.join(',')).join('\n')
    const blob = new Blob([csv], { type: 'text/csv' })
    const url = window.URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `attendance-${format(new Date(), 'yyyy-MM-dd')}.csv`
    a.click()
    window.URL.revokeObjectURL(url)
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold text-gray-900">Attendance History</h1>
          <p className="mt-1 text-sm text-gray-600">View your attendance records (read-only)</p>
        </div>
        <div className="flex items-center space-x-3">
          <button
            onClick={() => refetch()}
            className="btn btn-secondary flex items-center space-x-2"
          >
            <RefreshCw className="w-4 h-4" />
            <span>Refresh</span>
          </button>
          <button
            onClick={handleExport}
            className="btn btn-primary flex items-center space-x-2"
          >
            <Download className="w-4 h-4" />
            <span>Export PDF</span>
          </button>
        </div>
      </div>

      {/* Filters */}
      <div className="card">
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">Filter</label>
            <select
              value={dateFilter}
              onChange={(e) => setDateFilter(e.target.value as any)}
              className="input"
            >
              <option value="all">All Time</option>
              <option value="today">Today</option>
              <option value="week">This Week</option>
              <option value="month">This Month</option>
              <option value="custom">Custom Range</option>
            </select>
          </div>

          {dateFilter === 'custom' && (
            <>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">Start Date</label>
                <input
                  type="date"
                  value={startDate}
                  onChange={(e) => setStartDate(e.target.value)}
                  className="input"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">End Date</label>
                <input
                  type="date"
                  value={endDate}
                  onChange={(e) => setEndDate(e.target.value)}
                  className="input"
                />
              </div>
            </>
          )}
        </div>
      </div>

      {/* Attendance Table */}
      <div className="card">
        {isLoading ? (
          <div className="text-center py-12">
            <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary-600 mx-auto"></div>
          </div>
        ) : attendance.length === 0 ? (
          <div className="text-center py-12 text-gray-500">
            <Calendar className="w-12 h-12 mx-auto mb-3 text-gray-400" />
            <p>No attendance records found</p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="table">
              <thead>
                <tr>
                  <th>Date</th>
                  <th>Check-in Time</th>
                  <th>Check-out Time</th>
                  <th>Status</th>
                  <th>Event Type</th>
                </tr>
              </thead>
              <tbody>
                {attendance.map((record: any) => (
                  <tr key={record.id}>
                    <td className="font-medium">
                      {format(new Date(record.date), 'PP')}
                    </td>
                    <td>
                      {record.check_in_time ? (
                        <div className="flex items-center space-x-2">
                          <CheckCircle className="w-4 h-4 text-green-500" />
                          <span>{format(new Date(record.check_in_time), 'h:mm a')}</span>
                        </div>
                      ) : (
                        <span className="text-gray-400">-</span>
                      )}
                    </td>
                    <td>
                      {record.check_out_time ? (
                        <div className="flex items-center space-x-2">
                          <XCircle className="w-4 h-4 text-orange-500" />
                          <span>{format(new Date(record.check_out_time), 'h:mm a')}</span>
                        </div>
                      ) : (
                        <span className="text-gray-400">-</span>
                      )}
                    </td>
                    <td>
                      <span className={`badge ${
                        record.status === 'present' ? 'badge-success' :
                        record.status === 'failed' ? 'badge-danger' :
                        'badge-warning'
                      }`}>
                        {record.status}
                      </span>
                    </td>
                    <td className="text-sm text-gray-600">
                      {record.event_type === 'check_in' ? 'Check-in' : 'Check-out'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}
