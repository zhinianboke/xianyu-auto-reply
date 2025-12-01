import React, { useEffect, useState, useRef } from 'react'
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { useAuthStore } from '@/store/authStore'
import { MainLayout } from '@/components/layout/MainLayout'
import { Login } from '@/pages/auth/Login'
import { Register } from '@/pages/auth/Register'
import { Dashboard } from '@/pages/dashboard/Dashboard'
import { Accounts } from '@/pages/accounts/Accounts'
import { Items } from '@/pages/items/Items'
import { Orders } from '@/pages/orders/Orders'
import { Keywords } from '@/pages/keywords/Keywords'
import { About } from '@/pages/about/About'
import { Cards } from '@/pages/cards/Cards'
import { Delivery } from '@/pages/delivery/Delivery'
import { NotificationChannels } from '@/pages/notifications/NotificationChannels'
import { MessageNotifications } from '@/pages/notifications/MessageNotifications'
import { Settings } from '@/pages/settings/Settings'
import { ItemReplies } from '@/pages/item-replies/ItemReplies'
import { ItemSearch } from '@/pages/search/ItemSearch'
import { Users } from '@/pages/admin/Users'
import { Logs } from '@/pages/admin/Logs'
import { RiskLogs } from '@/pages/admin/RiskLogs'
import { DataManagement } from '@/pages/admin/DataManagement'
import { verifyToken } from '@/api/auth'

// Protected route wrapper
function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const { isAuthenticated, setAuth, clearAuth, token: storeToken, _hasHydrated } = useAuthStore()
  const [authState, setAuthState] = useState<'checking' | 'authenticated' | 'unauthenticated'>('checking')
  const checkingRef = useRef(false)

  useEffect(() => {
    // 等待 zustand persist 完成 hydration
    if (!_hasHydrated) {
      return
    }
    
    // 防止并发检查
    if (checkingRef.current) {
      return
    }
    
    const checkAuth = async () => {
      checkingRef.current = true
      
      // 优先使用 store 中的 token，其次是 localStorage
      const token = storeToken || localStorage.getItem('auth_token')
      
      if (!token) {
        setAuthState('unauthenticated')
        checkingRef.current = false
        return
      }

      // 验证 token 有效性（不再单纯相信本地 isAuthenticated 状态）
      try {
        const result = await verifyToken()
        if (result.authenticated && result.user_id) {
          setAuth(token, {
            user_id: result.user_id,
            username: result.username || '',
            is_admin: result.is_admin || false,
          })
          setAuthState('authenticated')
        } else {
          clearAuth()
          setAuthState('unauthenticated')
        }
      } catch {
        clearAuth()
        setAuthState('unauthenticated')
      } finally {
        checkingRef.current = false
      }
    }

    checkAuth()
  }, [_hasHydrated, isAuthenticated, storeToken, setAuth, clearAuth])

  // 等待 hydration 或检查完成
  if (!_hasHydrated || authState === 'checking') {
    return (
      <div className="min-h-screen flex items-center justify-center bg-slate-50 dark:bg-slate-900">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500"></div>
      </div>
    )
  }

  if (authState === 'unauthenticated') {
    return <Navigate to="/login" replace />
  }

  return <>{children}</>
}

function App() {
  return (
    <BrowserRouter>
      <Routes>
        {/* Public routes */}
        <Route path="/login" element={<Login />} />
        <Route path="/register" element={<Register />} />

        {/* Protected routes */}
        <Route
          path="/"
          element={
            <ProtectedRoute>
              <MainLayout />
            </ProtectedRoute>
          }
        >
          <Route index element={<Navigate to="/dashboard" replace />} />
          <Route path="dashboard" element={<Dashboard />} />
          <Route path="accounts" element={<Accounts />} />
          <Route path="items" element={<Items />} />
          <Route path="orders" element={<Orders />} />
          <Route path="keywords" element={<Keywords />} />
          <Route path="item-replies" element={<ItemReplies />} />
          <Route path="cards" element={<Cards />} />
          <Route path="delivery" element={<Delivery />} />
          <Route path="notification-channels" element={<NotificationChannels />} />
          <Route path="message-notifications" element={<MessageNotifications />} />
          <Route path="item-search" element={<ItemSearch />} />
          <Route path="settings" element={<Settings />} />
          <Route path="about" element={<About />} />

          {/* Admin routes */}
          <Route path="admin/users" element={<Users />} />
          <Route path="admin/logs" element={<Logs />} />
          <Route path="admin/risk-logs" element={<RiskLogs />} />
          <Route path="admin/data" element={<DataManagement />} />
        </Route>

        {/* Catch all */}
        <Route path="*" element={<Navigate to="/dashboard" replace />} />
      </Routes>
    </BrowserRouter>
  )
}

export default App
