import { useState, useEffect, useRef } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Bell, MessageSquare } from 'lucide-react'
import { api } from '@/lib/api'

export default function NotificationBell() {
  const [isOpen, setIsOpen] = useState(false)
  const dropdownRef = useRef<HTMLDivElement>(null)

  // Fetch messages to compute unread count (same source as Dashboard & Messages page)
  const { data: messages = [] } = useQuery({
    queryKey: ['messages'],
    queryFn: () => api.getMessages({ limit: 50 }),
  })

  const unreadCount = messages.filter((m: any) => !m.read).length

  // Close dropdown when clicking outside
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setIsOpen(false)
      }
    }

    if (isOpen) {
      document.addEventListener('mousedown', handleClickOutside)
    }

    return () => {
      document.removeEventListener('mousedown', handleClickOutside)
    }
  }, [isOpen])

  return (
    <div className="relative" ref={dropdownRef}>
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="relative p-2 text-gray-600 hover:text-gray-900 hover:bg-gray-100 rounded-lg transition-colors"
      >
        <Bell className="w-6 h-6" />
        {unreadCount > 0 && (
          <span className="absolute top-0 right-0 flex items-center justify-center w-5 h-5 text-xs font-bold text-white bg-red-600 rounded-full">
            {unreadCount > 9 ? '9+' : unreadCount}
          </span>
        )}
      </button>

      {isOpen && (
        <div className="absolute right-0 mt-2 w-80 bg-white rounded-lg shadow-xl border border-gray-200 z-50">
          <div className="p-4 border-b border-gray-200">
            <h3 className="text-lg font-semibold text-gray-900">Notifications</h3>
          </div>
          <div className="p-4 max-h-80 overflow-y-auto">
            {messages.length === 0 ? (
              <div className="py-6 text-center text-gray-500">
                <Bell className="w-12 h-12 mx-auto mb-3 text-gray-400" />
                <p>No notifications</p>
              </div>
            ) : (
              <div className="space-y-3">
                {messages.slice(0, 10).map((message: any) => (
                  <div
                    key={message.id}
                    className={`p-3 rounded-lg border text-sm ${
                      !message.read
                        ? 'bg-blue-50 border-blue-200'
                        : 'bg-white border-gray-200'
                    }`}
                  >
                    <div className="flex items-start space-x-2">
                      <MessageSquare className="w-4 h-4 text-blue-500 mt-1" />
                      <div className="flex-1">
                        <div className="font-medium text-gray-900 line-clamp-1">
                          {message.title}
                        </div>
                        <div className="text-xs text-gray-600 line-clamp-2 mt-1">
                          {message.content}
                        </div>
                        {!message.read && (
                          <div className="mt-1 text-xs text-primary-600 font-medium">
                            New
                          </div>
                        )}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
