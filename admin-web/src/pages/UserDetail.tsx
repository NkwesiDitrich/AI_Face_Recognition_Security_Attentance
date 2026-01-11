import { useParams, Link, Navigate, useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { ArrowLeft, Edit, Calendar, Clock, CheckCircle, XCircle, AlertCircle } from 'lucide-react'
import { api } from '@/lib/api'
import { format } from 'date-fns'
import { useState } from 'react'

export default function UserDetail() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [showReEnrollConfirm, setShowReEnrollConfirm] = useState(false)
  
  if (!id) return <Navigate to="/users" />

  const { data: user, isLoading } = useQuery({
    queryKey: ['user', id],
    queryFn: () => api.getUserById(id),
  })

  const { data: enrollmentStatus, isLoading: enrollmentLoading } = useQuery({
    queryKey: ['user-enrollment', id],
    queryFn: () => api.getUserEnrollmentStatus(id),
    enabled: !!id,
  })

  const { data: attendanceHistory } = useQuery({
    queryKey: ['user-attendance', id],
    queryFn: () => api.getAttendanceRecords({ user_id: id, limit: 10 }),
    enabled: !!id,
  })

  const reEnrollMutation = useMutation({
    mutationFn: (userId: string) => api.forceReEnrollment(userId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['user', id] })
      queryClient.invalidateQueries({ queryKey: ['user-enrollment', id] })
      setShowReEnrollConfirm(false)
    },
  })

  const handleReEnroll = () => {
    if (id) {
      reEnrollMutation.mutate(id)
    }
  }

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-12">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary-600"></div>
      </div>
    )
  }

  if (!user) {
    return (
      <div className="text-center py-12">
        <p className="text-gray-600">User not found</p>
        <Link to="/users" className="text-primary-600 hover:text-primary-700 mt-4 inline-block">
          Back to Users
        </Link>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center space-x-4">
          <Link to="/users" className="text-gray-600 hover:text-gray-900">
            <ArrowLeft className="w-5 h-5" />
          </Link>
          <div>
            <h1 className="text-3xl font-bold text-gray-900">{user.name}</h1>
            <p className="mt-1 text-sm text-gray-600">Employee ID: {user.employee_id}</p>
          </div>
        </div>
      </div>

      {/* User Info Cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <div className="card">
          <h3 className="text-sm font-medium text-gray-600 mb-2">Status</h3>
          <p className="text-2xl font-bold">
            {user.status === 'active' ? (
              <span className="badge badge-success">Active</span>
            ) : (
              <span className="badge badge-danger">Inactive</span>
            )}
          </p>
        </div>
        <div className="card">
          <h3 className="text-sm font-medium text-gray-600 mb-2">Role</h3>
          <p className="text-2xl font-bold">
            <span className="badge badge-info">{user.access_level}</span>
          </p>
        </div>
        <div className="card">
          <h3 className="text-sm font-medium text-gray-600 mb-2">Enrollment Status</h3>
          <p className="text-2xl font-bold">
            {user.enrollment_status === 'enrolled' ? (
              <span className="badge badge-success">Enrolled</span>
            ) : user.enrollment_status === 'needs_re_enrollment' ? (
              <span className="badge badge-warning">Needs Re-enrollment</span>
            ) : (
              <span className="badge badge-info">Not Enrolled</span>
            )}
          </p>
        </div>
      </div>

      {/* Enrollment Details */}
      <div className="card">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-xl font-bold text-gray-900">Enrollment Details</h2>
          {user.enrollment_status === 'enrolled' && (
            <button 
              onClick={() => setShowReEnrollConfirm(true)}
              className="btn btn-warning"
              disabled={reEnrollMutation.isPending}
            >
              {reEnrollMutation.isPending ? 'Processing...' : 'Force Re-enrollment'}
            </button>
          )}
        </div>
        
        {enrollmentLoading ? (
          <div className="text-center py-8">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary-600 mx-auto"></div>
          </div>
        ) : enrollmentStatus ? (
          <div className="space-y-4">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <p className="text-sm text-gray-600 mb-1">Enrollment Status</p>
                <p className="font-medium">
                  {enrollmentStatus.is_enrolled ? (
                    <span className="badge badge-success">Enrolled</span>
                  ) : (
                    <span className="badge badge-info">Not Enrolled</span>
                  )}
                </p>
              </div>
              <div>
                <p className="text-sm text-gray-600 mb-1">Face Encodings Count</p>
                <p className="font-medium">{enrollmentStatus.face_encodings_count || 0}</p>
              </div>
              {enrollmentStatus.latest_enrollment && (
                <>
                  <div>
                    <p className="text-sm text-gray-600 mb-1 flex items-center">
                      <Calendar className="w-4 h-4 mr-1" />
                      Enrollment Date
                    </p>
                    <p className="font-medium">
                      {enrollmentStatus.latest_enrollment.timestamp 
                        ? format(new Date(enrollmentStatus.latest_enrollment.timestamp), 'PPpp') 
                        : 'N/A'}
                    </p>
                  </div>
                  <div>
                    <p className="text-sm text-gray-600 mb-1 flex items-center">
                      <Clock className="w-4 h-4 mr-1" />
                      Device Used
                    </p>
                    <p className="font-medium">{enrollmentStatus.latest_enrollment.device_id || 'N/A'}</p>
                  </div>
                </>
              )}
            </div>
            
            {/* Enrollment History */}
            {enrollmentStatus.enrollment_history && enrollmentStatus.enrollment_history.length > 0 && (
              <div className="mt-6">
                <h3 className="text-sm font-medium text-gray-700 mb-3">Enrollment History</h3>
                <div className="space-y-2">
                  {enrollmentStatus.enrollment_history.slice(0, 10).map((entry: any, index: number) => (
                    <div key={index} className="flex items-center justify-between p-3 bg-gray-50 rounded-lg">
                      <div className="flex items-center space-x-3">
                        {entry.stage === 'completed' ? (
                          <CheckCircle className="w-5 h-5 text-green-600" />
                        ) : (
                          <AlertCircle className="w-5 h-5 text-yellow-600" />
                        )}
                        <div>
                          <p className="font-medium text-sm">{entry.stage}</p>
                          <p className="text-xs text-gray-500">
                            {entry.timestamp ? format(new Date(entry.timestamp), 'PPpp') : 'N/A'}
                          </p>
                        </div>
                      </div>
                      <div className="text-right">
                        <p className="text-xs text-gray-500">{entry.device_id || 'N/A'}</p>
                        {entry.reason && (
                          <p className="text-xs text-gray-400">{entry.reason}</p>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        ) : (
          <p className="text-center py-8 text-gray-500">No enrollment data available</p>
        )}
      </div>

      {/* Attendance History */}
      <div className="card">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-xl font-bold text-gray-900">Recent Attendance</h2>
          <Link to={`/attendance?user_id=${id}`} className="text-sm text-primary-600 hover:text-primary-700">
            View All
          </Link>
        </div>
        {attendanceHistory && attendanceHistory.length > 0 ? (
          <div className="table-container">
            <table className="table">
              <thead>
                <tr>
                  <th>Date & Time</th>
                  <th>Event Type</th>
                  <th>Status</th>
                  <th>Liveness</th>
                </tr>
              </thead>
              <tbody>
                {attendanceHistory.map((record: any) => (
                  <tr key={record.id}>
                    <td>{format(new Date(record.timestamp), 'PPpp')}</td>
                    <td>
                      <span className="badge badge-info">{record.event_type}</span>
                    </td>
                    <td>
                      {record.status === 'success' ? (
                        <span className="badge badge-success">Success</span>
                      ) : (
                        <span className="badge badge-danger">Failed</span>
                      )}
                    </td>
                    <td>
                      {record.liveness_status === 'passed' ? (
                        <CheckCircle className="w-5 h-5 text-green-600" />
                      ) : (
                        <XCircle className="w-5 h-5 text-red-600" />
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="text-center py-8 text-gray-500">No attendance records found</p>
        )}
      </div>

      {/* Re-enrollment Confirmation Modal */}
      {showReEnrollConfirm && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-lg p-6 max-w-md w-full">
            <h3 className="text-lg font-bold text-gray-900 mb-4">Force Re-enrollment</h3>
            <p className="text-gray-600 mb-6">
              Are you sure you want to force re-enrollment for this user? This will clear their face encodings and they will need to re-enroll.
            </p>
            <div className="flex justify-end space-x-3">
              <button 
                onClick={() => setShowReEnrollConfirm(false)} 
                className="btn btn-secondary"
                disabled={reEnrollMutation.isPending}
              >
                Cancel
              </button>
              <button 
                onClick={handleReEnroll} 
                className="btn btn-warning"
                disabled={reEnrollMutation.isPending}
              >
                {reEnrollMutation.isPending ? 'Processing...' : 'Confirm Re-enrollment'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
