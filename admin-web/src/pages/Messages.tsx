import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Plus, Send, Eye, X, Users, User, Building, Info, AlertTriangle, MessageSquare } from 'lucide-react'
import { api } from '@/lib/api'
import { format } from 'date-fns'

interface Message {
  id: string
  title: string
  content: string
  message_type: 'info' | 'warning' | 'instruction'
  target_type: 'all_users' | 'group' | 'single_user'
  target_ids: string[]
  sender_name: string
  total_recipients: number
  delivered_count: number
  read_count: number
  status: string
  created_at: string
  sent_at?: string
}

export default function Messages() {
  const [showNewMessageModal, setShowNewMessageModal] = useState(false)
  const [selectedMessage, setSelectedMessage] = useState<Message | null>(null)
  const [showDeliveryStatus, setShowDeliveryStatus] = useState(false)
  const [deliveryStatusData, setDeliveryStatusData] = useState<any>(null)
  
  const [messageForm, setMessageForm] = useState({
    title: '',
    content: '',
    message_type: 'info' as 'info' | 'warning' | 'instruction',
    target_type: 'all_users' as 'all_users' | 'group' | 'single_user',
    target_ids: [] as string[],
    selectedUser: '',
    selectedGroup: '',
  })

  const queryClient = useQueryClient()

  // Get users for single user/group selection
  const { data: users = [] } = useQuery({
    queryKey: ['users'],
    queryFn: () => api.getUsers(),
  })

  // Get messages
  const { data: messages = [], isLoading } = useQuery({
    queryKey: ['messages'],
    queryFn: () => api.getMessages({ limit: 100 }),
  })

  // Send message mutation
  const sendMessageMutation = useMutation({
    mutationFn: (data: any) => api.sendMessage(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['messages'] })
      setShowNewMessageModal(false)
      setMessageForm({
        title: '',
        content: '',
        message_type: 'info',
        target_type: 'all_users',
        target_ids: [],
        selectedUser: '',
        selectedGroup: '',
      })
    },
    onError: (error: any) => {
      alert(error.response?.data?.detail || 'Failed to send message')
    },
  })

  const handleSendMessage = async (e: React.FormEvent) => {
    e.preventDefault()
    
    let targetIds: string[] = []
    if (messageForm.target_type === 'single_user') {
      if (!messageForm.selectedUser) {
        alert('Please select a user')
        return
      }
      targetIds = [messageForm.selectedUser]
    } else if (messageForm.target_type === 'group') {
      if (!messageForm.selectedGroup) {
        alert('Please select a group')
        return
      }
      targetIds = [messageForm.selectedGroup]
    }

    sendMessageMutation.mutate({
      title: messageForm.title,
      content: messageForm.content,
      message_type: messageForm.message_type,
      target_type: messageForm.target_type,
      target_ids: targetIds,
    })
  }

  const handleViewDeliveryStatus = async (messageId: string) => {
    try {
      const status = await api.getMessageDeliveryStatus(messageId)
      setDeliveryStatusData(status)
      setShowDeliveryStatus(true)
    } catch (error) {
      console.error('Error fetching delivery status:', error)
      alert('Failed to load delivery status')
    }
  }

  const getMessageTypeIcon = (type: string) => {
    switch (type) {
      case 'warning':
        return <AlertTriangle className="w-5 h-5 text-orange-600" />
      case 'instruction':
        return <MessageSquare className="w-5 h-5 text-blue-600" />
      default:
        return <Info className="w-5 h-5 text-green-600" />
    }
  }

  const getMessageTypeBadge = (type: string) => {
    switch (type) {
      case 'warning':
        return <span className="badge badge-warning">Warning</span>
      case 'instruction':
        return <span className="badge badge-info">Instruction</span>
      default:
        return <span className="badge badge-success">Info</span>
    }
  }

  // Get unique groups from users
  const groups = Array.from(new Set(users.map((u: any) => u.access_level).filter(Boolean)))

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold text-gray-900">Messages</h1>
          <p className="mt-1 text-sm text-gray-600">
            Send messages and announcements to users
          </p>
        </div>
        <button
          onClick={() => setShowNewMessageModal(true)}
          className="btn btn-primary"
        >
          <Plus className="w-4 h-4 mr-2" />
          New Message
        </button>
      </div>

      {/* Messages List */}
      <div className="card">
        {isLoading ? (
          <div className="text-center py-12">
            <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary-600 mx-auto"></div>
          </div>
        ) : messages.length === 0 ? (
          <div className="text-center py-12 text-gray-500">
            <MessageSquare className="w-12 h-12 mx-auto mb-3 text-gray-400" />
            <p>No messages sent yet</p>
          </div>
        ) : (
          <div className="table-container">
            <table className="table">
              <thead>
                <tr>
                  <th>Title</th>
                  <th>Type</th>
                  <th>Target</th>
                  <th>Recipients</th>
                  <th>Status</th>
                  <th>Sent At</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {messages.map((message: Message) => (
                  <tr key={message.id}>
                    <td className="font-medium">{message.title}</td>
                    <td>{getMessageTypeBadge(message.message_type)}</td>
                    <td>
                      {message.target_type === 'all_users' && (
                        <span className="badge badge-info">All Users</span>
                      )}
                      {message.target_type === 'group' && (
                        <span className="badge badge-info">Group</span>
                      )}
                      {message.target_type === 'single_user' && (
                        <span className="badge badge-info">Single User</span>
                      )}
                    </td>
                    <td>
                      <div className="text-sm">
                        <div>Total: {message.total_recipients}</div>
                        <div className="text-green-600">Delivered: {message.delivered_count}</div>
                        <div className="text-blue-600">Read: {message.read_count}</div>
                      </div>
                    </td>
                    <td>
                      <span className={`badge ${
                        message.status === 'sent' ? 'badge-success' : 'badge-warning'
                      }`}>
                        {message.status}
                      </span>
                    </td>
                    <td>
                      {message.sent_at
                        ? format(new Date(message.sent_at), 'PPp')
                        : format(new Date(message.created_at), 'PPp')}
                    </td>
                    <td>
                      <button
                        onClick={() => handleViewDeliveryStatus(message.id)}
                        className="text-primary-600 hover:text-primary-700"
                        title="View Delivery Status"
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

      {/* New Message Modal */}
      {showNewMessageModal && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-white rounded-lg shadow-xl max-w-2xl w-full mx-4 max-h-[90vh] overflow-y-auto">
            <div className="p-6">
              <div className="flex items-center justify-between mb-4">
                <h2 className="text-2xl font-bold text-gray-900">New Message</h2>
                <button
                  onClick={() => setShowNewMessageModal(false)}
                  className="text-gray-400 hover:text-gray-600"
                >
                  <X className="w-6 h-6" />
                </button>
              </div>

              <form onSubmit={handleSendMessage} className="space-y-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-2">
                    Title *
                  </label>
                  <input
                    type="text"
                    value={messageForm.title}
                    onChange={(e) => setMessageForm({ ...messageForm, title: e.target.value })}
                    className="input"
                    required
                  />
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-2">
                    Content *
                  </label>
                  <textarea
                    value={messageForm.content}
                    onChange={(e) => setMessageForm({ ...messageForm, content: e.target.value })}
                    className="input"
                    rows={5}
                    required
                  />
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-2">
                    Message Type *
                  </label>
                  <select
                    value={messageForm.message_type}
                    onChange={(e) => setMessageForm({ ...messageForm, message_type: e.target.value as any })}
                    className="input"
                  >
                    <option value="info">Info</option>
                    <option value="warning">Warning</option>
                    <option value="instruction">Instruction</option>
                  </select>
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-2">
                    Target *
                  </label>
                  <select
                    value={messageForm.target_type}
                    onChange={(e) => setMessageForm({ ...messageForm, target_type: e.target.value as any, selectedUser: '', selectedGroup: '' })}
                    className="input"
                  >
                    <option value="all_users">All Users</option>
                    <option value="group">Group</option>
                    <option value="single_user">Single User</option>
                  </select>
                </div>

                {messageForm.target_type === 'single_user' && (
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-2">
                      Select User *
                    </label>
                    <select
                      value={messageForm.selectedUser}
                      onChange={(e) => setMessageForm({ ...messageForm, selectedUser: e.target.value })}
                      className="input"
                      required
                    >
                      <option value="">Select a user...</option>
                      {users.map((user: any) => (
                        <option key={user.id} value={user.id}>
                          {user.name} ({user.employee_id})
                        </option>
                      ))}
                    </select>
                  </div>
                )}

                {messageForm.target_type === 'group' && (
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-2">
                      Select Group *
                    </label>
                    <select
                      value={messageForm.selectedGroup}
                      onChange={(e) => setMessageForm({ ...messageForm, selectedGroup: e.target.value })}
                      className="input"
                      required
                    >
                      <option value="">Select a group...</option>
                      {groups.map((group) => (
                        <option key={group} value={group}>
                          {group}
                        </option>
                      ))}
                    </select>
                  </div>
                )}

                <div className="flex justify-end space-x-3 pt-4">
                  <button
                    type="button"
                    onClick={() => setShowNewMessageModal(false)}
                    className="btn btn-secondary"
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    className="btn btn-primary"
                    disabled={sendMessageMutation.isPending}
                  >
                    <Send className="w-4 h-4 mr-2" />
                    {sendMessageMutation.isPending ? 'Sending...' : 'Send Message'}
                  </button>
                </div>
              </form>
            </div>
          </div>
        </div>
      )}

      {/* Delivery Status Modal */}
      {showDeliveryStatus && deliveryStatusData && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-white rounded-lg shadow-xl max-w-4xl w-full mx-4 max-h-[90vh] overflow-y-auto">
            <div className="p-6">
              <div className="flex items-center justify-between mb-4">
                <h2 className="text-2xl font-bold text-gray-900">Delivery Status</h2>
                <button
                  onClick={() => setShowDeliveryStatus(false)}
                  className="text-gray-400 hover:text-gray-600"
                >
                  <X className="w-6 h-6" />
                </button>
              </div>

              <div className="space-y-4">
                <div className="grid grid-cols-3 gap-4 mb-6">
                  <div className="bg-blue-50 p-4 rounded-lg">
                    <div className="text-sm text-gray-600">Total Recipients</div>
                    <div className="text-2xl font-bold text-blue-600">{deliveryStatusData.stats.total}</div>
                  </div>
                  <div className="bg-green-50 p-4 rounded-lg">
                    <div className="text-sm text-gray-600">Delivered</div>
                    <div className="text-2xl font-bold text-green-600">{deliveryStatusData.stats.delivered}</div>
                    <div className="text-xs text-gray-500 mt-1">
                      {deliveryStatusData.stats.delivery_rate.toFixed(1)}%
                    </div>
                  </div>
                  <div className="bg-purple-50 p-4 rounded-lg">
                    <div className="text-sm text-gray-600">Read</div>
                    <div className="text-2xl font-bold text-purple-600">{deliveryStatusData.stats.read}</div>
                    <div className="text-xs text-gray-500 mt-1">
                      {deliveryStatusData.stats.read_rate.toFixed(1)}%
                    </div>
                  </div>
                </div>

                <div className="table-container">
                  <table className="table">
                    <thead>
                      <tr>
                        <th>User ID</th>
                        <th>Delivered</th>
                        <th>Read</th>
                        <th>Delivered At</th>
                        <th>Read At</th>
                      </tr>
                    </thead>
                    <tbody>
                      {deliveryStatusData.deliveries.map((delivery: any) => (
                        <tr key={delivery.id}>
                          <td className="font-mono text-sm">{delivery.user_id}</td>
                          <td>
                            {delivery.delivered ? (
                              <span className="badge badge-success">Yes</span>
                            ) : (
                              <span className="badge badge-warning">No</span>
                            )}
                          </td>
                          <td>
                            {delivery.read ? (
                              <span className="badge badge-success">Yes</span>
                            ) : (
                              <span className="badge badge-warning">No</span>
                            )}
                          </td>
                          <td>
                            {delivery.delivered_at
                              ? format(new Date(delivery.delivered_at), 'PPp')
                              : '-'}
                          </td>
                          <td>
                            {delivery.read_at
                              ? format(new Date(delivery.read_at), 'PPp')
                              : '-'}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>

              <div className="mt-6 flex justify-end">
                <button
                  onClick={() => setShowDeliveryStatus(false)}
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
