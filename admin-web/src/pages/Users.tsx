import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { Plus, Search, Upload, Edit, Trash2, Eye, UserX, UserCheck, X } from 'lucide-react'
import { api } from '@/lib/api'
import type { User } from '@/types'

export default function Users() {
  const [searchTerm, setSearchTerm] = useState('')
  const [statusFilter, setStatusFilter] = useState<string>('all')
  const [roleFilter, setRoleFilter] = useState<string>('all')
  const [showCreateModal, setShowCreateModal] = useState(false)
  const [showEditModal, setShowEditModal] = useState<User | null>(null)
  const [showDeleteModal, setShowDeleteModal] = useState<string | null>(null)
  const [showBulkImportModal, setShowBulkImportModal] = useState(false)
  const [createError, setCreateError] = useState('')
  const [editError, setEditError] = useState('')
  const queryClient = useQueryClient()

  // Form states
  const [createForm, setCreateForm] = useState({ name: '', employee_id: '', access_level: 'employee' })
  const [editForm, setEditForm] = useState({ name: '', employee_id: '', access_level: 'employee', status: 'active' })
  const [bulkImportFile, setBulkImportFile] = useState<File | null>(null)

  const { data: users, isLoading } = useQuery({
    queryKey: ['users', { search: searchTerm, status: statusFilter, role: roleFilter }],
    queryFn: () => api.getUsers({ 
      search: searchTerm || undefined, 
      status: statusFilter !== 'all' ? statusFilter : undefined, 
      role: roleFilter !== 'all' ? roleFilter : undefined 
    }),
  })

  const createMutation = useMutation({
    mutationFn: (data: { name: string; employee_id: string; access_level: string }) => api.createUser(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['users'] })
      setShowCreateModal(false)
      setCreateForm({ name: '', employee_id: '', access_level: 'employee' })
      setCreateError('')
    },
    onError: (error: any) => {
      setCreateError(error.response?.data?.detail || 'Failed to create user')
    },
  })

  const updateMutation = useMutation({
    mutationFn: ({ id, data }: { id: string; data: any }) => api.updateUser(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['users'] })
      queryClient.invalidateQueries({ queryKey: ['user'] })
      setShowEditModal(null)
      setEditForm({ name: '', employee_id: '', access_level: 'employee', status: 'active' })
      setEditError('')
    },
    onError: (error: any) => {
      setEditError(error.response?.data?.detail || 'Failed to update user')
    },
  })

  const deleteMutation = useMutation({
    mutationFn: (id: string) => api.deleteUser(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['users'] })
      setShowDeleteModal(null)
    },
  })

  const toggleStatusMutation = useMutation({
    mutationFn: ({ id, status }: { id: string; status: string }) => api.updateUser(id, { status }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['users'] })
    },
  })

  const bulkImportMutation = useMutation({
    mutationFn: (file: File) => api.bulkImportUsers(file),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['users'] })
      setShowBulkImportModal(false)
      setBulkImportFile(null)
    },
    onError: (error: any) => {
      alert(error.response?.data?.detail || 'Failed to import users')
    },
  })

  const handleCreate = (e: React.FormEvent) => {
    e.preventDefault()
    setCreateError('')
    if (!createForm.name.trim() || !createForm.employee_id.trim()) {
      setCreateError('Name and Employee ID are required')
      return
    }
    createMutation.mutate(createForm)
  }

  const handleEdit = (e: React.FormEvent) => {
    e.preventDefault()
    setEditError('')
    if (!editForm.name.trim() || !editForm.employee_id.trim()) {
      setEditError('Name and Employee ID are required')
      return
    }
    if (!showEditModal) return
    updateMutation.mutate({ id: showEditModal.id, data: editForm })
  }

  const handleDelete = (id: string) => {
    deleteMutation.mutate(id)
  }

  const handleToggleStatus = (user: User) => {
    const newStatus = user.status === 'active' ? 'inactive' : 'active'
    toggleStatusMutation.mutate({ id: user.id, status: newStatus })
  }

  const handleEditClick = (user: User) => {
    setEditForm({
      name: user.name,
      employee_id: user.employee_id,
      access_level: user.access_level,
      status: user.status || 'active'
    })
    setEditError('')
    setShowEditModal(user)
  }

  const handleBulkImport = (e: React.FormEvent) => {
    e.preventDefault()
    if (!bulkImportFile) {
      alert('Please select a CSV file')
      return
    }
    bulkImportMutation.mutate(bulkImportFile)
  }

  const getEnrollmentBadge = (status?: string) => {
    switch (status) {
      case 'enrolled':
        return <span className="badge badge-success">Enrolled</span>
      case 'needs_re_enrollment':
        return <span className="badge badge-warning">Needs Re-enrollment</span>
      default:
        return <span className="badge badge-info">Not Enrolled</span>
    }
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold text-gray-900">Users Management</h1>
          <p className="mt-1 text-sm text-gray-600">Manage registered users and their enrollment status</p>
        </div>
        <div className="flex space-x-3">
          <button onClick={() => setShowBulkImportModal(true)} className="btn btn-secondary">
            <Upload className="w-4 h-4 mr-2" />
            Bulk Import
          </button>
          <button onClick={() => setShowCreateModal(true)} className="btn btn-primary">
            <Plus className="w-4 h-4 mr-2" />
            Add User
          </button>
        </div>
      </div>

      {/* Filters */}
      <div className="card">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">Search</label>
            <div className="relative">
              <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 w-5 h-5 text-gray-400" />
              <input
                type="text"
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                placeholder="Search by name or ID..."
                className="input pl-10"
              />
            </div>
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">Status</label>
            <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)} className="input">
              <option value="all">All Status</option>
              <option value="active">Active</option>
              <option value="inactive">Inactive</option>
            </select>
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">Role</label>
            <select value={roleFilter} onChange={(e) => setRoleFilter(e.target.value)} className="input">
              <option value="all">All Roles</option>
              <option value="employee">Employee</option>
              <option value="admin">Admin</option>
              <option value="manager">Manager</option>
            </select>
          </div>
        </div>
      </div>

      {/* Users Table */}
      <div className="card">
        {isLoading ? (
          <div className="text-center py-12">
            <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary-600 mx-auto"></div>
          </div>
        ) : users?.length === 0 ? (
          <div className="text-center py-12 text-gray-500">
            <p>No users found</p>
          </div>
        ) : (
          <div className="table-container">
            <table className="table">
              <thead>
                <tr>
                  <th>Name</th>
                  <th>Employee ID</th>
                  <th>Role</th>
                  <th>Status</th>
                  <th>Enrollment</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {users?.map((user: User) => (
                  <tr key={user.id}>
                    <td className="font-medium">{user.name}</td>
                    <td>{user.employee_id}</td>
                    <td>
                      <span className="badge badge-info">{user.access_level}</span>
                    </td>
                    <td>
                      {user.status === 'active' ? (
                        <span className="badge badge-success">Active</span>
                      ) : (
                        <span className="badge badge-danger">Inactive</span>
                      )}
                    </td>
                    <td>{getEnrollmentBadge(user.enrollment_status)}</td>
                    <td>
                      <div className="flex items-center space-x-2">
                        <Link to={`/users/${user.id}`} className="text-primary-600 hover:text-primary-700" title="View Profile">
                          <Eye className="w-4 h-4" />
                        </Link>
                        <button onClick={() => handleEditClick(user)} className="text-blue-600 hover:text-blue-700" title="Edit User">
                          <Edit className="w-4 h-4" />
                        </button>
                        <button onClick={() => handleToggleStatus(user)} className="text-gray-600 hover:text-gray-700" title={user.status === 'active' ? 'Deactivate' : 'Activate'}>
                          {user.status === 'active' ? <UserX className="w-4 h-4" /> : <UserCheck className="w-4 h-4" />}
                        </button>
                        <button onClick={() => setShowDeleteModal(user.id)} className="text-red-600 hover:text-red-700" title="Delete User">
                          <Trash2 className="w-4 h-4" />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Create User Modal */}
      {showCreateModal && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-lg p-6 max-w-md w-full">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-lg font-bold text-gray-900">Create New User</h3>
              <button onClick={() => setShowCreateModal(false)} className="text-gray-400 hover:text-gray-600">
                <X className="w-5 h-5" />
              </button>
            </div>
            <form onSubmit={handleCreate} className="space-y-4">
              {createError && (
                <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg text-sm">
                  {createError}
                </div>
              )}
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">Name *</label>
                <input
                  type="text"
                  required
                  value={createForm.name}
                  onChange={(e) => setCreateForm({ ...createForm, name: e.target.value })}
                  className="input w-full"
                  placeholder="Full Name"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">Employee ID *</label>
                <input
                  type="text"
                  required
                  value={createForm.employee_id}
                  onChange={(e) => setCreateForm({ ...createForm, employee_id: e.target.value })}
                  className="input w-full"
                  placeholder="EMP001"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">Role</label>
                <select
                  value={createForm.access_level}
                  onChange={(e) => setCreateForm({ ...createForm, access_level: e.target.value })}
                  className="input w-full"
                >
                  <option value="employee">Employee</option>
                  <option value="admin">Admin</option>
                  <option value="manager">Manager</option>
                </select>
              </div>
              <div className="flex justify-end space-x-3 pt-4">
                <button type="button" onClick={() => setShowCreateModal(false)} className="btn btn-secondary">
                  Cancel
                </button>
                <button type="submit" className="btn btn-primary" disabled={createMutation.isPending}>
                  {createMutation.isPending ? 'Creating...' : 'Create User'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Edit User Modal */}
      {showEditModal && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-lg p-6 max-w-md w-full">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-lg font-bold text-gray-900">Edit User</h3>
              <button onClick={() => setShowEditModal(null)} className="text-gray-400 hover:text-gray-600">
                <X className="w-5 h-5" />
              </button>
            </div>
            <form onSubmit={handleEdit} className="space-y-4">
              {editError && (
                <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg text-sm">
                  {editError}
                </div>
              )}
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">Name *</label>
                <input
                  type="text"
                  required
                  value={editForm.name}
                  onChange={(e) => setEditForm({ ...editForm, name: e.target.value })}
                  className="input w-full"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">Employee ID *</label>
                <input
                  type="text"
                  required
                  value={editForm.employee_id}
                  onChange={(e) => setEditForm({ ...editForm, employee_id: e.target.value })}
                  className="input w-full"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">Role</label>
                <select
                  value={editForm.access_level}
                  onChange={(e) => setEditForm({ ...editForm, access_level: e.target.value })}
                  className="input w-full"
                >
                  <option value="employee">Employee</option>
                  <option value="admin">Admin</option>
                  <option value="manager">Manager</option>
                </select>
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">Status</label>
                <select
                  value={editForm.status}
                  onChange={(e) => setEditForm({ ...editForm, status: e.target.value })}
                  className="input w-full"
                >
                  <option value="active">Active</option>
                  <option value="inactive">Inactive</option>
                </select>
              </div>
              <div className="flex justify-end space-x-3 pt-4">
                <button type="button" onClick={() => setShowEditModal(null)} className="btn btn-secondary">
                  Cancel
                </button>
                <button type="submit" className="btn btn-primary" disabled={updateMutation.isPending}>
                  {updateMutation.isPending ? 'Updating...' : 'Update User'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Delete Confirmation Modal */}
      {showDeleteModal && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-lg p-6 max-w-md w-full">
            <h3 className="text-lg font-bold text-gray-900 mb-4">Delete User</h3>
            <p className="text-gray-600 mb-6">Are you sure you want to delete this user? This action cannot be undone.</p>
            <div className="flex justify-end space-x-3">
              <button onClick={() => setShowDeleteModal(null)} className="btn btn-secondary">Cancel</button>
              <button onClick={() => handleDelete(showDeleteModal)} className="btn btn-danger" disabled={deleteMutation.isPending}>
                {deleteMutation.isPending ? 'Deleting...' : 'Delete'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Bulk Import Modal */}
      {showBulkImportModal && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-lg p-6 max-w-md w-full">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-lg font-bold text-gray-900">Bulk Import Users</h3>
              <button onClick={() => setShowBulkImportModal(false)} className="text-gray-400 hover:text-gray-600">
                <X className="w-5 h-5" />
              </button>
            </div>
            <form onSubmit={handleBulkImport} className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">CSV File</label>
                <input
                  type="file"
                  accept=".csv"
                  onChange={(e) => setBulkImportFile(e.target.files?.[0] || null)}
                  className="input w-full"
                  required
                />
                <p className="mt-2 text-sm text-gray-500">
                  CSV format: name,employee_id,access_level
                </p>
              </div>
              <div className="flex justify-end space-x-3 pt-4">
                <button type="button" onClick={() => setShowBulkImportModal(false)} className="btn btn-secondary">
                  Cancel
                </button>
                <button type="submit" className="btn btn-primary" disabled={bulkImportMutation.isPending || !bulkImportFile}>
                  {bulkImportMutation.isPending ? 'Importing...' : 'Import Users'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  )
}
