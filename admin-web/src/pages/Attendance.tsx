import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Search, Calendar, Download, Eye, X } from 'lucide-react'
import { api } from '@/lib/api'
import { format } from 'date-fns'
import type { AttendanceRecord } from '@/types'

export default function Attendance() {
  const [searchTerm, setSearchTerm] = useState('')
  const [statusFilter, setStatusFilter] = useState<string>('all')
  const [userFilter, setUserFilter] = useState<string>('all')
  const [startDate, setStartDate] = useState('')
  const [endDate, setEndDate] = useState('')
  const [selectedRecord, setSelectedRecord] = useState<AttendanceRecord | null>(null)
  const [showDetailsModal, setShowDetailsModal] = useState(false)

  // Helper function to convert date string to ISO format with time
  const formatDateForAPI = (dateStr: string, isEndDate: boolean = false): string | undefined => {
    if (!dateStr) return undefined
    const date = new Date(dateStr)
    if (isEndDate) {
      // Set to end of day (23:59:59.999)
      date.setHours(23, 59, 59, 999)
    } else {
      // Set to start of day (00:00:00.000)
      date.setHours(0, 0, 0, 0)
    }
    return date.toISOString()
  }

  // Helper function to set today's date
  const handleSetToday = () => {
    const today = new Date()
    const todayStr = format(today, 'yyyy-MM-dd')
    setStartDate(todayStr)
    setEndDate(todayStr)
    setStatusFilter('all') // Show all statuses for today
  }

  // Get users for filter dropdown
  const { data: users } = useQuery({
    queryKey: ['users'],
    queryFn: () => api.getUsers(),
  })

  // Get attendance records
  const { data: records, isLoading } = useQuery({
    queryKey: ['attendance', { user_id: userFilter, status: statusFilter, start_date: startDate, end_date: endDate }],
    queryFn: () => {
      const params: any = {
        user_id: userFilter !== 'all' ? userFilter : undefined,
      }
      
      // Convert dates to ISO format
      if (startDate) {
        params.start_date = formatDateForAPI(startDate, false)
      }
      if (endDate) {
        params.end_date = formatDateForAPI(endDate, true)
      }
      
      // Map status filter: 'success' -> 'passed', 'failed' -> 'failed'
      if (statusFilter !== 'all') {
        params.status = statusFilter === 'success' ? 'passed' : 'failed'
      }
      
      return api.getAttendanceRecords(params)
    },
  })

  // Filter records by search term (client-side filtering by user name)
  const filteredRecords = records?.filter((record: AttendanceRecord) => {
    if (!searchTerm) return true
    const userName = record.user_name || ''
    return userName.toLowerCase().includes(searchTerm.toLowerCase())
  }) || []

  const handleViewDetails = async (recordId: string) => {
    try {
      const record = await api.getAttendanceRecordById(recordId)
      setSelectedRecord(record)
      setShowDetailsModal(true)
    } catch (error) {
      console.error('Error fetching record details:', error)
    }
  }

  const handleExportCSV = () => {
    // Create CSV content
    const headers = ['User', 'Date', 'Time', 'Event Type', 'Liveness', 'Status', 'Device', 'Session ID']
    const rows = filteredRecords.map((record: AttendanceRecord) => {
      const date = new Date(record.timestamp)
      return [
        record.user_name || 'Unknown',
        format(date, 'yyyy-MM-dd'),
        format(date, 'HH:mm:ss'),
        record.event_type,
        record.liveness_status === 'passed' ? 'Passed' : record.liveness_status === 'failed' ? 'Failed' : 'N/A',
        record.liveness_status === 'passed' ? 'Success' : 'Failed',
        record.device_id || 'N/A',
        record.session_id || 'N/A'
      ]
    })

    const csvContent = [
      headers.join(','),
      ...rows.map(row => row.map(cell => `"${cell}"`).join(','))
    ].join('\n')

    // Download CSV
    const blob = new Blob([csvContent], { type: 'text/csv' })
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
          <h1 className="text-3xl font-bold text-gray-900">Attendance Records</h1>
          <p className="mt-1 text-sm text-gray-600">View and monitor attendance records (Read-only)</p>
        </div>
        <div className="flex space-x-3">
          <button onClick={handleExportCSV} className="btn btn-secondary">
            <Download className="w-4 h-4 mr-2" />
            Export CSV
          </button>
        </div>
      </div>

      {/* Filters */}
      <div className="card">
        <div className="grid grid-cols-1 md:grid-cols-5 gap-4 mb-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">Search</label>
            <div className="relative">
              <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 w-5 h-5 text-gray-400" />
              <input
                type="text"
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                placeholder="Search by user name..."
                className="input pl-10"
              />
            </div>
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">User</label>
            <select value={userFilter} onChange={(e) => setUserFilter(e.target.value)} className="input">
              <option value="all">All Users</option>
              {users?.map((user: any) => (
                <option key={user.id} value={user.id}>
                  {user.name}
                </option>
              ))}
            </select>
          </div>
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
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">Status</label>
            <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)} className="input">
              <option value="all">All Status</option>
              <option value="success">Success</option>
              <option value="failed">Failed</option>
            </select>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={handleSetToday}
            className="btn btn-secondary text-sm"
          >
            <Calendar className="w-4 h-4 mr-2" />
            Show Today (All Status)
          </button>
          {(startDate || endDate) && (
            <button
              onClick={() => {
                setStartDate('')
                setEndDate('')
              }}
              className="btn btn-secondary text-sm"
            >
              Clear Dates
            </button>
          )}
        </div>
      </div>

      {/* Attendance Table */}
      <div className="card">
        {isLoading ? (
          <div className="text-center py-12">
            <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary-600 mx-auto"></div>
          </div>
        ) : !filteredRecords || filteredRecords.length === 0 ? (
          <div className="text-center py-12 text-gray-500">
            <Calendar className="w-12 h-12 mx-auto mb-3 text-gray-400" />
            <p>No attendance records found</p>
          </div>
        ) : (
          <div className="table-container">
            <table className="table">
              <thead>
                <tr>
                  <th>User</th>
                  <th>Date & Time</th>
                  <th>Event Type</th>
                  <th>Liveness</th>
                  <th>Status</th>
                  <th>Device</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {filteredRecords.map((record: AttendanceRecord) => (
                  <tr key={record.id}>
                    <td className="font-medium">{record.user_name || 'Unknown'}</td>
                    <td>{format(new Date(record.timestamp), 'PPpp')}</td>
                    <td>
                      <span className="badge badge-info">{record.event_type}</span>
                    </td>
                    <td>
                      {record.liveness_status === 'passed' ? (
                        <span className="badge badge-success">Passed</span>
                      ) : record.liveness_status === 'failed' ? (
                        <span className="badge badge-danger">Failed</span>
                      ) : (
                        <span className="badge badge-info">N/A</span>
                      )}
                    </td>
                    <td>
                      {record.liveness_status === 'passed' ? (
                        <span className="badge badge-success">Success</span>
                      ) : (
                        <span className="badge badge-danger">Failed</span>
                      )}
                    </td>
                    <td>{record.device_id || 'N/A'}</td>
                    <td>
                      <button
                        onClick={() => handleViewDetails(record.id)}
                        className="text-primary-600 hover:text-primary-700"
                        title="View Details"
                      >
                        <Eye className="w-4 h-4" />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* View Details Modal */}
      {showDetailsModal && selectedRecord && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-white rounded-lg shadow-xl max-w-2xl w-full mx-4 max-h-[90vh] overflow-y-auto">
            <div className="p-6">
              <div className="flex items-center justify-between mb-4">
                <h2 className="text-2xl font-bold text-gray-900">Attendance Record Details</h2>
                <button
                  onClick={() => setShowDetailsModal(false)}
                  className="text-gray-400 hover:text-gray-600"
                >
                  <X className="w-6 h-6" />
                </button>
              </div>

              <div className="space-y-4">
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className="block text-sm font-medium text-gray-600 mb-1">User</label>
                    <p className="text-gray-900">{selectedRecord.user_name || 'Unknown'}</p>
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-gray-600 mb-1">Date & Time</label>
                    <p className="text-gray-900">{format(new Date(selectedRecord.timestamp), 'PPpp')}</p>
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-gray-600 mb-1">Event Type</label>
                    <p className="text-gray-900">
                      <span className="badge badge-info">{selectedRecord.event_type}</span>
                    </p>
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-gray-600 mb-1">Liveness Check</label>
                    <p className="text-gray-900">
                      {selectedRecord.liveness_status === 'passed' ? (
                        <span className="badge badge-success">Passed</span>
                      ) : selectedRecord.liveness_status === 'failed' ? (
                        <span className="badge badge-danger">Failed</span>
                      ) : (
                        <span className="badge badge-info">N/A</span>
                      )}
                    </p>
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-gray-600 mb-1">Status</label>
                    <p className="text-gray-900">
                      {selectedRecord.liveness_status === 'passed' ? (
                        <span className="badge badge-success">Success</span>
                      ) : (
                        <span className="badge badge-danger">Failed</span>
                      )}
                    </p>
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-gray-600 mb-1">Device</label>
                    <p className="text-gray-900">{selectedRecord.device_id || 'N/A'}</p>
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-gray-600 mb-1">Session ID</label>
                    <p className="text-gray-900 font-mono text-sm">{selectedRecord.session_id || 'N/A'}</p>
                  </div>
                  {selectedRecord.confidence !== undefined && (
                    <div>
                      <label className="block text-sm font-medium text-gray-600 mb-1">Confidence</label>
                      <p className="text-gray-900">{(selectedRecord.confidence * 100).toFixed(2)}%</p>
                    </div>
                  )}
                  {selectedRecord.attempts_used !== undefined && (
                    <div>
                      <label className="block text-sm font-medium text-gray-600 mb-1">Attempts Used</label>
                      <p className="text-gray-900">{selectedRecord.attempts_used}</p>
                    </div>
                  )}
                  {selectedRecord.total_duration_ms !== undefined && (
                    <div>
                      <label className="block text-sm font-medium text-gray-600 mb-1">Duration</label>
                      <p className="text-gray-900">{(selectedRecord.total_duration_ms / 1000).toFixed(2)}s</p>
                    </div>
                  )}
                </div>
              </div>

              <div className="mt-6 flex justify-end">
                <button
                  onClick={() => setShowDetailsModal(false)}
                  className="btn btn-primary"
                >
                  Close
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}