import { useState, useEffect, useRef } from 'react'
import { Activity, Pause, Play, Eye, X, AlertCircle, CheckCircle, Wifi, WifiOff } from 'lucide-react'
import { format } from 'date-fns'
import { api } from '@/lib/api'

interface AttendanceEvent {
  id: string
  user_id: string
  user_name: string
  timestamp: string
  status: 'success' | 'failed'
  liveness: 'passed' | 'failed'
  event_type: 'check_in' | 'check_out'
  device_id?: string
  session_id?: string
}

interface WebSocketMessage {
  type: 'connected' | 'attendance_event' | 'paused' | 'resumed' | 'error'
  message?: string
  event?: AttendanceEvent
  timestamp?: string
}

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

export default function AttendanceFeed() {
  const [events, setEvents] = useState<AttendanceEvent[]>([])
  const [isConnected, setIsConnected] = useState(false)
  const [isPaused, setIsPaused] = useState(false)
  const [selectedEvent, setSelectedEvent] = useState<AttendanceEvent | null>(null)
  const [showDetailsModal, setShowDetailsModal] = useState(false)
  const wsRef = useRef<WebSocket | null>(null)
  const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null)

  useEffect(() => {
    connectWebSocket()

    return () => {
      if (wsRef.current) {
        wsRef.current.close()
      }
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current)
      }
    }
  }, [])

  const connectWebSocket = () => {
    try {
      const token = localStorage.getItem('admin_token')
      if (!token) {
        console.error('No auth token found')
        return
      }

      // Convert HTTP URL to WebSocket URL
      let wsUrl = API_BASE_URL.replace('http://', 'ws://').replace('https://', 'wss://')
      // Remove trailing slash if present
      if (wsUrl.endsWith('/')) {
        wsUrl = wsUrl.slice(0, -1)
      }
      const wsEndpoint = `${wsUrl}/api/v1/admin/ws/attendance-feed?token=${encodeURIComponent(token)}`
      
      const ws = new WebSocket(wsEndpoint)
      wsRef.current = ws

      ws.onopen = () => {
        console.log('âœ… WebSocket connected')
        setIsConnected(true)
        if (reconnectTimeoutRef.current) {
          clearTimeout(reconnectTimeoutRef.current)
          reconnectTimeoutRef.current = null
        }
      }

      ws.onmessage = (event) => {
        try {
          const message: WebSocketMessage = JSON.parse(event.data)
          
          if (message.type === 'connected') {
            console.log('WebSocket connection confirmed')
          } else if (message.type === 'attendance_event' && message.event) {
            // Add new event to the top of the list
            setEvents((prev) => [message.event!, ...prev].slice(0, 100)) // Keep last 100 events
          } else if (message.type === 'paused') {
            setIsPaused(true)
          } else if (message.type === 'resumed') {
            setIsPaused(false)
          } else if (message.type === 'error') {
            console.error('WebSocket error:', message.message)
          }
        } catch (error) {
          console.error('Error parsing WebSocket message:', error)
        }
      }

      ws.onerror = (error) => {
        console.error('WebSocket error:', error)
        setIsConnected(false)
      }

      ws.onclose = () => {
        console.log('WebSocket disconnected')
        setIsConnected(false)
        
        // Attempt to reconnect after 3 seconds
        if (!reconnectTimeoutRef.current) {
          reconnectTimeoutRef.current = setTimeout(() => {
            reconnectTimeoutRef.current = null
            connectWebSocket()
          }, 3000)
        }
      }
    } catch (error) {
      console.error('Error connecting WebSocket:', error)
      setIsConnected(false)
    }
  }

  const handlePause = () => {
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ action: 'pause' }))
      setIsPaused(true)
    }
  }

  const handleResume = () => {
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ action: 'resume' }))
      setIsPaused(false)
    }
  }

  const handleViewDetails = async (event: AttendanceEvent) => {
    try {
      // Fetch full record details from API
      const record = await api.getAttendanceRecordById(event.id)
      setSelectedEvent({
        ...event,
        ...record
      } as AttendanceEvent)
      setShowDetailsModal(true)
    } catch (error) {
      console.error('Error fetching event details:', error)
      // Fallback to event data we already have
      setSelectedEvent(event)
      setShowDetailsModal(true)
    }
  }

  const handleClearEvents = () => {
    setEvents([])
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold text-gray-900">Real-Time Attendance Feed</h1>
          <p className="mt-1 text-sm text-gray-600">
            Live monitoring of check-ins and check-outs
          </p>
        </div>
        <div className="flex items-center space-x-3">
          {/* Connection Status */}
          <div className="flex items-center space-x-2">
            {isConnected ? (
              <>
                <Wifi className="w-5 h-5 text-green-600" />
                <span className="text-sm text-green-600 font-medium">Connected</span>
              </>
            ) : (
              <>
                <WifiOff className="w-5 h-5 text-red-600" />
                <span className="text-sm text-red-600 font-medium">Disconnected</span>
              </>
            )}
          </div>
          
          {/* Pause/Resume Button */}
          {isPaused ? (
            <button onClick={handleResume} className="btn btn-secondary">
              <Play className="w-4 h-4 mr-2" />
              Resume Feed
            </button>
          ) : (
            <button onClick={handlePause} className="btn btn-secondary">
              <Pause className="w-4 h-4 mr-2" />
              Pause Feed
            </button>
          )}
          
          {/* Clear Events Button */}
          <button onClick={handleClearEvents} className="btn btn-secondary">
            Clear Events
          </button>
        </div>
      </div>

      {/* Events Feed */}
      <div className="card">
        <div className="mb-4">
          <div className="flex items-center justify-between">
            <h2 className="text-lg font-semibold text-gray-900">
              Live Events ({events.length})
            </h2>
            {isPaused && (
              <span className="badge badge-warning">Paused</span>
            )}
          </div>
        </div>
        
        <div className="space-y-2 max-h-[600px] overflow-y-auto">
          {events.length === 0 ? (
            <div className="text-center py-12 text-gray-500">
              <Activity className="w-12 h-12 mx-auto mb-3 text-gray-400" />
              <p>Waiting for attendance events...</p>
              <p className="text-sm mt-2">
                {!isConnected && 'Reconnecting...'}
              </p>
            </div>
          ) : (
            events.map((event) => (
              <div
                key={event.id}
                className={`p-4 rounded-lg border-2 transition-all ${
                  event.status === 'failed'
                    ? 'bg-red-50 border-red-200 hover:border-red-300'
                    : 'bg-white border-gray-200 hover:border-gray-300'
                }`}
              >
                <div className="flex items-center justify-between">
                  <div className="flex items-center space-x-4 flex-1">
                    {/* Status Icon */}
                    <div className="flex-shrink-0">
                      {event.status === 'success' ? (
                        <div className="w-10 h-10 bg-green-100 rounded-full flex items-center justify-center">
                          <CheckCircle className="w-6 h-6 text-green-600" />
                        </div>
                      ) : (
                        <div className="w-10 h-10 bg-red-100 rounded-full flex items-center justify-center">
                          <AlertCircle className="w-6 h-6 text-red-600" />
                        </div>
                      )}
                    </div>
                    
                    {/* Event Info */}
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center space-x-2">
                        <p className="font-semibold text-gray-900">{event.user_name}</p>
                        <span className={`badge ${
                          event.status === 'success' ? 'badge-success' : 'badge-danger'
                        }`}>
                          {event.status === 'success' ? 'Success' : 'Failed'}
                        </span>
                        <span className="badge badge-info">{event.event_type}</span>
                      </div>
                      <div className="flex items-center space-x-4 mt-1 text-sm text-gray-600">
                        <span>{format(new Date(event.timestamp), 'PPpp')}</span>
                        {event.device_id && (
                          <span>Device: {event.device_id}</span>
                        )}
                      </div>
                    </div>
                  </div>
                  
                  {/* View Details Button */}
                  <div className="flex-shrink-0 ml-4">
                    <button
                      onClick={() => handleViewDetails(event)}
                      className="text-primary-600 hover:text-primary-700"
                      title="View Details"
                    >
                      <Eye className="w-5 h-5" />
                    </button>
                  </div>
                </div>
              </div>
            ))
          )}
        </div>
      </div>

      {/* Event Details Modal */}
      {showDetailsModal && selectedEvent && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-white rounded-lg shadow-xl max-w-2xl w-full mx-4 max-h-[90vh] overflow-y-auto">
            <div className="p-6">
              <div className="flex items-center justify-between mb-4">
                <h2 className="text-2xl font-bold text-gray-900">Event Details</h2>
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
                    <p className="text-gray-900">{selectedEvent.user_name || 'Unknown'}</p>
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-gray-600 mb-1">Date & Time</label>
                    <p className="text-gray-900">{format(new Date(selectedEvent.timestamp), 'PPpp')}</p>
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-gray-600 mb-1">Event Type</label>
                    <p className="text-gray-900">
                      <span className="badge badge-info">{selectedEvent.event_type}</span>
                    </p>
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-gray-600 mb-1">Status</label>
                    <p className="text-gray-900">
                      {selectedEvent.status === 'success' ? (
                        <span className="badge badge-success">Success</span>
                      ) : (
                        <span className="badge badge-danger">Failed</span>
                      )}
                    </p>
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-gray-600 mb-1">Liveness Result</label>
                    <p className="text-gray-900">
                      {selectedEvent.liveness === 'passed' ? (
                        <span className="badge badge-success">Passed</span>
                      ) : (
                        <span className="badge badge-danger">Failed</span>
                      )}
                    </p>
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-gray-600 mb-1">Device</label>
                    <p className="text-gray-900">{selectedEvent.device_id || 'N/A'}</p>
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-gray-600 mb-1">Session ID</label>
                    <p className="text-gray-900 font-mono text-sm">{selectedEvent.session_id || 'N/A'}</p>
                  </div>
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
