import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuthStore } from '@/store/authStore'
import { api } from '@/lib/api'
import { User, Lock, ArrowRight } from 'lucide-react'

type LoginStep = 'user_id' | 'password_setup' | 'password'

export default function Login() {
  const [step, setStep] = useState<LoginStep>('user_id')
  const [userId, setUserId] = useState('')
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const navigate = useNavigate()
  const { setAuth } = useAuthStore()

  const handleUserIdSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    setLoading(true)

    try {
      // Check if user exists and if password is set
      const userInfo = await api.checkUser(userId)
      
      if (userInfo.password_set) {
        // User has password, go to password step
        setStep('password')
      } else {
        // User exists but no password set, go to password setup
        setStep('password_setup')
      }
    } catch (err: any) {
      const errorDetail = err.response?.data?.detail || ''
      if (err.response?.status === 404) {
        setError('User not found. Please check your User ID.')
      } else if (err.response?.status === 403) {
        setError('User account is not active. Please contact administrator.')
      } else {
        setError(errorDetail || 'Unable to verify user. Please check your User ID.')
      }
    } finally {
      setLoading(false)
    }
  }

  const handlePasswordSetup = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')

    if (password.length < 8) {
      setError('Password must be at least 8 characters long')
      return
    }

    if (password !== confirmPassword) {
      setError('Passwords do not match')
      return
    }

    setLoading(true)

    try {
      await api.setupPassword({
        user_id: userId,
        password,
        confirm_password: confirmPassword,
      })
      
      // After setup, login automatically
      const loginResponse = await api.login({ user_id: userId, password })
      if (loginResponse.success) {
        setAuth(loginResponse.token, loginResponse.user)
        navigate('/dashboard')
      }
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to setup password')
    } finally {
      setLoading(false)
    }
  }

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    setLoading(true)

    try {
      const response = await api.login({ user_id: userId, password })
      if (response.success) {
        setAuth(response.token, response.user)
        navigate('/dashboard')
      }
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Invalid credentials')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-primary-50 to-primary-100 px-4">
      <div className="max-w-md w-full">
        <div className="bg-white rounded-2xl shadow-xl p-8">
          <div className="text-center mb-8">
            <h1 className="text-3xl font-bold text-gray-900 mb-2">User Portal</h1>
            <p className="text-gray-600">Access your attendance and messages</p>
          </div>

          {step === 'user_id' && (
            <form onSubmit={handleUserIdSubmit} className="space-y-6">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  User ID / Employee ID
                </label>
                <div className="relative">
                  <User className="absolute left-3 top-1/2 transform -translate-y-1/2 w-5 h-5 text-gray-400" />
                  <input
                    type="text"
                    value={userId}
                    onChange={(e) => setUserId(e.target.value)}
                    className="input pl-10"
                    placeholder="Enter your User ID"
                    required
                    autoFocus
                  />
                </div>
              </div>

              {error && (
                <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg text-sm">
                  {error}
                </div>
              )}

              <button
                type="submit"
                disabled={loading || !userId.trim()}
                className="btn btn-primary w-full flex items-center justify-center space-x-2"
              >
                <span>{loading ? 'Checking...' : 'Continue'}</span>
                <ArrowRight className="w-4 h-4" />
              </button>
            </form>
          )}

          {step === 'password_setup' && (
            <form onSubmit={handlePasswordSetup} className="space-y-6">
              <div className="bg-blue-50 border border-blue-200 rounded-lg p-4 mb-4">
                <p className="text-sm text-blue-800">
                  Welcome! Please create a password for your account.
                </p>
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  Create Password
                </label>
                <div className="relative">
                  <Lock className="absolute left-3 top-1/2 transform -translate-y-1/2 w-5 h-5 text-gray-400" />
                  <input
                    type="password"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    className="input pl-10"
                    placeholder="Minimum 8 characters"
                    required
                    minLength={8}
                    autoFocus
                  />
                </div>
                <p className="mt-1 text-xs text-gray-500">
                  Must be at least 8 characters with a number or symbol
                </p>
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  Confirm Password
                </label>
                <div className="relative">
                  <Lock className="absolute left-3 top-1/2 transform -translate-y-1/2 w-5 h-5 text-gray-400" />
                  <input
                    type="password"
                    value={confirmPassword}
                    onChange={(e) => setConfirmPassword(e.target.value)}
                    className="input pl-10"
                    placeholder="Confirm your password"
                    required
                  />
                </div>
              </div>

              {error && (
                <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg text-sm">
                  {error}
                </div>
              )}

              <div className="flex space-x-3">
                <button
                  type="button"
                  onClick={() => {
                    setStep('user_id')
                    setPassword('')
                    setConfirmPassword('')
                    setError('')
                  }}
                  className="btn btn-secondary flex-1"
                >
                  Back
                </button>
                <button
                  type="submit"
                  disabled={loading || !password || !confirmPassword}
                  className="btn btn-primary flex-1"
                >
                  {loading ? 'Setting up...' : 'Create Password'}
                </button>
              </div>
            </form>
          )}

          {step === 'password' && (
            <form onSubmit={handleLogin} className="space-y-6">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  Password
                </label>
                <div className="relative">
                  <Lock className="absolute left-3 top-1/2 transform -translate-y-1/2 w-5 h-5 text-gray-400" />
                  <input
                    type="password"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    className="input pl-10"
                    placeholder="Enter your password"
                    required
                    autoFocus
                  />
                </div>
              </div>

              {error && (
                <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg text-sm">
                  {error}
                </div>
              )}

              <div className="flex space-x-3">
                <button
                  type="button"
                  onClick={() => {
                    setStep('user_id')
                    setPassword('')
                    setError('')
                  }}
                  className="btn btn-secondary flex-1"
                >
                  Back
                </button>
                <button
                  type="submit"
                  disabled={loading || !password}
                  className="btn btn-primary flex-1"
                >
                  {loading ? 'Logging in...' : 'Login'}
                </button>
              </div>
            </form>
          )}
        </div>
      </div>
    </div>
  )
}
