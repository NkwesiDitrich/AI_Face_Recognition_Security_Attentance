import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api'
import { format } from 'date-fns'
import { MessageSquare, Info, AlertTriangle, FileText, Check, Eye } from 'lucide-react'
import type { Message } from '@/types'

export default function Messages() {
  const [selectedMessage, setSelectedMessage] = useState<Message | null>(null)
  const queryClient = useQueryClient()

  const { data: messages = [], isLoading } = useQuery({
    queryKey: ['messages'],
    queryFn: () => api.getMessages({ limit: 100 }),
  })

  const markAsReadMutation = useMutation({
    mutationFn: (messageId: string) => api.markMessageAsRead(messageId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['messages'] })
    },
  })

  const getMessageIcon = (type: string) => {
    switch (type) {
      case 'warning':
        return <AlertTriangle className="w-5 h-5 text-orange-600" />
      case 'instruction':
        return <FileText className="w-5 h-5 text-blue-600" />
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

  const unreadCount = messages.filter((m: Message) => !m.read).length

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold text-gray-900">Messages</h1>
          <p className="mt-1 text-sm text-gray-600">
            Messages and announcements from admins
            {unreadCount > 0 && (
              <span className="ml-2 text-primary-600 font-medium">
                ({unreadCount} unread)
              </span>
            )}
          </p>
        </div>
      </div>

      {/* Messages List */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Messages List */}
        <div className="lg:col-span-2">
          <div className="card">
            {isLoading ? (
              <div className="text-center py-12">
                <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary-600 mx-auto"></div>
              </div>
            ) : messages.length === 0 ? (
              <div className="text-center py-12 text-gray-500">
                <MessageSquare className="w-12 h-12 mx-auto mb-3 text-gray-400" />
                <p>No messages</p>
              </div>
            ) : (
              <div className="space-y-3">
                {messages.map((message: Message) => (
                  <div
                    key={message.id}
                    className={`p-4 rounded-lg border cursor-pointer transition-colors ${
                      !message.read
                        ? 'bg-blue-50 border-blue-200 hover:bg-blue-100'
                        : 'bg-white border-gray-200 hover:bg-gray-50'
                    }`}
                    onClick={() => {
                      setSelectedMessage(message)
                      if (!message.read) {
                        markAsReadMutation.mutate(message.id)
                      }
                    }}
                  >
                    <div className="flex items-start justify-between">
                      <div className="flex items-start space-x-3 flex-1">
                        <div className="flex-shrink-0 mt-1">
                          {getMessageIcon(message.message_type)}
                        </div>
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center space-x-2 mb-1">
                            <h3 className={`font-medium ${
                              !message.read ? 'text-gray-900' : 'text-gray-700'
                            }`}>
                              {message.title}
                            </h3>
                            {getMessageTypeBadge(message.message_type)}
                          </div>
                          <p className="text-sm text-gray-600 line-clamp-2">
                            {message.content}
                          </p>
                          <div className="flex items-center space-x-4 mt-2 text-xs text-gray-500">
                            <span>From: {message.sender_name}</span>
                            <span>{format(new Date(message.created_at), 'PPp')}</span>
                          </div>
                        </div>
                      </div>
                      {!message.read && (
                        <div className="flex-shrink-0 ml-2">
                          <span className="w-2 h-2 bg-blue-600 rounded-full block"></span>
                        </div>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* Message Detail */}
        <div className="lg:col-span-1">
          {selectedMessage ? (
            <div className="card sticky top-4">
              <div className="flex items-center justify-between mb-4">
                <div className="flex items-center space-x-2">
                  {getMessageIcon(selectedMessage.message_type)}
                  {getMessageTypeBadge(selectedMessage.message_type)}
                </div>
                {selectedMessage.read && (
                  <div className="flex items-center space-x-1 text-green-600 text-sm">
                    <Check className="w-4 h-4" />
                    <span>Read</span>
                  </div>
                )}
              </div>
              <h2 className="text-xl font-bold text-gray-900 mb-2">
                {selectedMessage.title}
              </h2>
              <div className="text-sm text-gray-600 mb-4">
                <p>From: {selectedMessage.sender_name}</p>
                <p>{format(new Date(selectedMessage.created_at), 'PPp')}</p>
              </div>
              <div className="prose max-w-none">
                <p className="text-gray-700 whitespace-pre-wrap">
                  {selectedMessage.content}
                </p>
              </div>
              <button
                onClick={() => setSelectedMessage(null)}
                className="mt-4 btn btn-secondary w-full"
              >
                Close
              </button>
            </div>
          ) : (
            <div className="card">
              <div className="text-center py-12 text-gray-500">
                <Eye className="w-12 h-12 mx-auto mb-3 text-gray-400" />
                <p>Select a message to view details</p>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
