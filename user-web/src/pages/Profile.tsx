import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api'
import { User, Lock, CheckCircle, XCircle, Save } from 'lucide-react'

export default function Profile() {
  const [showChangePassword, setShowChangePassword] = useState(false)
  const [passwordForm, setPasswordForm] = useState({
    old_password: '',
    new_password: '',
    confirm_password: '',
  })
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')

  const queryClient = useQueryClient()

  const { data: profile, isLoading } = useQuery({
    queryKey: ['profile'],
    queryFn: () => api.getProfile(),
  })

  const changePasswordMutation = useMutation({
    mutationFn: (data: { old_password: string; new_password: string; confirm_password: string }) =>
      api.changePassword(data),
    onSuccess: () => {
      setSuccess('Password changed successfully')
      setError('')
      setPasswordForm({ old_password: '', new_password: '', confirm_password: '' })
      setShowChangePassword(false)
      setTimeout(() => setSuccess(''), 3000)
    },
    onError: (err: any) => {
      setError(err.response?.data?.detail || 'Failed to change password')
      setSuccess('')
    },
  })

  const handleChangePassword = (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    setSuccess('')

    if (passwordForm.new_password.length < 8) {
      setError('Password must be at least 8 characters long')
      return
    }

    if (passwordForm.new_password !== passwordForm.confirm_password) {
      setError('Passwords do not match')
      return
    }

    changePasswordMutation.mutate(passwordForm)
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-3xl font-bold text-gray-900">Profile</h1>
        <p className="mt-1 text-sm text-gray-600">View and manage your profile information</p>
      </div>

      {isLoading ? (
        <div className="text-center py-12">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary-600 mx-auto"></div>
        </div>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Profile Information */}
          <div className="card">
            <h2 className="text-xl font-semibold text-gray-900 mb-6 flex items-center space-x-2">
              <User className="w-6 h-6" />
              <span>Personal Information</span>
            </h2>

            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Name</label>
                <input
                  type="text"
                  value={profile?.name || ''}
                  className="input bg-gray-50"
                  readOnly
                  disabled
                />
                <p className="mt-1 text-xs text-gray-500">Cannot be edited</p>
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Employee ID</label>
                <input
                  type="text"
                  value={profile?.employee_id || ''}
                  className="input bg-gray-50"
                  readOnly
                  disabled
                />
                <p className="mt-1 text-xs text-gray-500">Cannot be edited</p>
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Role</label>
                <input
                  type="text"
                  value={profile?.access_level || ''}
                  className="input bg-gray-50"
                  readOnly
                  disabled
                />
                <p className="mt-1 text-xs text-gray-500">Cannot be edited</p>
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Status</label>
                <div className="flex items-center space-x-2">
                  {profile?.status === 'active' ? (
                    <>
                      <CheckCircle className="w-5 h-5 text-green-600" />
                      <span className="text-green-600 font-medium">Active</span>
                    </>
                  ) : (
                    <>
                      <XCircle className="w-5 h-5 text-red-600" />
                      <span className="text-red-600 font-medium">Inactive</span>
                    </>
                  )}
                </div>
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Enrollment Status</label>
                <div className="flex items-center space-x-2">
                  {profile?.enrollment_status === 'enrolled' ? (
                    <>
                      <CheckCircle className="w-5 h-5 text-green-600" />
                      <span className="text-green-600 font-medium">Enrolled</span>
                    </>
                  ) : profile?.enrollment_status === 'needs_re_enrollment' ? (
                    <>
                      <XCircle className="w-5 h-5 text-orange-600" />
                      <span className="text-orange-600 font-medium">Needs Re-enrollment</span>
                    </>
                  ) : (
                    <>
                      <XCircle className="w-5 h-5 text-gray-600" />
                      <span className="text-gray-600 font-medium">Not Enrolled</span>
                    </>
                  )}
                </div>
                <p className="mt-1 text-xs text-gray-500">
                  Face enrollment status (managed by admin)
                </p>
              </div>
            </div>
          </div>

          {/* Change Password */}
          <div className="card">
            <h2 className="text-xl font-semibold text-gray-900 mb-6 flex items-center space-x-2">
              <Lock className="w-6 h-6" />
              <span>Security</span>
            </h2>

            {!showChangePassword ? (
              <div>
                <p className="text-gray-600 mb-4">
                  Change your password to keep your account secure.
                </p>
                <button
                  onClick={() => setShowChangePassword(true)}
                  className="btn btn-primary"
                >
                  Change Password
                </button>
              </div>
            ) : (
              <form onSubmit={handleChangePassword} className="space-y-4">
                {error && (
                  <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg text-sm">
                    {error}
                  </div>
                )}

                {success && (
                  <div className="bg-green-50 border border-green-200 text-green-700 px-4 py-3 rounded-lg text-sm">
                    {success}
                  </div>
                )}

                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-2">
                    Current Password
                  </label>
                  <input
                    type="password"
                    value={passwordForm.old_password}
                    onChange={(e) =>
                      setPasswordForm({ ...passwordForm, old_password: e.target.value })
                    }
                    className="input"
                    required
                    autoFocus
                  />
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-2">
                    New Password
                  </label>
                  <input
                    type="password"
                    value={passwordForm.new_password}
                    onChange={(e) =>
                      setPasswordForm({ ...passwordForm, new_password: e.target.value })
                    }
                    className="input"
                    required
                    minLength={8}
                  />
                  <p className="mt-1 text-xs text-gray-500">
                    Must be at least 8 characters with a number or symbol
                  </p>
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-2">
                    Confirm New Password
                  </label>
                  <input
                    type="password"
                    value={passwordForm.confirm_password}
                    onChange={(e) =>
                      setPasswordForm({ ...passwordForm, confirm_password: e.target.value })
                    }
                    className="input"
                    required
                  />
                </div>

                <div className="flex space-x-3">
                  <button
                    type="button"
                    onClick={() => {
                      setShowChangePassword(false)
                      setPasswordForm({ old_password: '', new_password: '', confirm_password: '' })
                      setError('')
                      setSuccess('')
                    }}
                    className="btn btn-secondary flex-1"
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    disabled={changePasswordMutation.isPending}
                    className="btn btn-primary flex-1 flex items-center justify-center space-x-2"
                  >
                    <Save className="w-4 h-4" />
                    <span>{changePasswordMutation.isPending ? 'Changing...' : 'Change Password'}</span>
                  </button>
                </div>
              </form>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
