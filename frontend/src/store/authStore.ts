import { create } from 'zustand'
import { persist, createJSONStorage } from 'zustand/middleware'
import type { User } from '@/types'

interface AuthState {
  token: string | null
  refreshToken: string | null
  user: User | null
  isAuthenticated: boolean
  _hasHydrated: boolean
  setAuth: (token: string, refreshToken: string, user: User) => void
  clearAuth: () => void
  updateUser: (user: Partial<User>) => void
  setHasHydrated: (state: boolean) => void
  updateTokens: (token: string, refreshToken: string) => void
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      token: null,
      refreshToken: null,
      user: null,
      isAuthenticated: false,
      _hasHydrated: false,

      setAuth: (token, refreshToken, user) => {
        localStorage.setItem('auth_token', token)
        localStorage.setItem('refresh_token', refreshToken)
        localStorage.setItem('user_info', JSON.stringify(user))
        // 注意：此处不清除弹窗公告会话标记。
        // setAuth 在每次刷新页面验证 token 后也会被调用，若在此清除标记，
        // 会导致刷新后公告重复弹出。清除标记的逻辑放在真正的登录成功处（Login.tsx）。
        set({ token, refreshToken, user, isAuthenticated: true })
      },

      clearAuth: () => {
        localStorage.removeItem('auth_token')
        localStorage.removeItem('refresh_token')
        localStorage.removeItem('user_info')
        set({ token: null, refreshToken: null, user: null, isAuthenticated: false })
      },

      updateUser: (userData) => {
        set((state) => {
          const newUser = state.user ? { ...state.user, ...userData } : null
          if (newUser) {
            localStorage.setItem('user_info', JSON.stringify(newUser))
          }
          return { user: newUser }
        })
      },

      setHasHydrated: (hydrated) => {
        set({ _hasHydrated: hydrated })
      },

      updateTokens: (token, refreshToken) => {
        localStorage.setItem('auth_token', token)
        localStorage.setItem('refresh_token', refreshToken)
        set({ token, refreshToken })
      },
    }),
    {
      name: 'auth-storage',
      storage: createJSONStorage(() => localStorage),
      // 只持久化token和refreshToken，user从localStorage单独读取
      partialize: (state) => ({ 
        token: state.token,
        refreshToken: state.refreshToken,
        isAuthenticated: state.isAuthenticated 
      }),
      onRehydrateStorage: () => {
        return (state, error) => {
          if (error) {
            console.error('Failed to rehydrate auth store:', error)
            return
          }
          if (state?.token) {
            localStorage.setItem('auth_token', state.token)
          }
          if (state?.refreshToken) {
            localStorage.setItem('refresh_token', state.refreshToken)
          }
          // 从localStorage读取user信息，使用setTimeout避免循环引用
          setTimeout(() => {
            const userInfoStr = localStorage.getItem('user_info')
            if (userInfoStr) {
              try {
                const user = JSON.parse(userInfoStr)
                useAuthStore.setState({ user, _hasHydrated: true })
              } catch (e) {
                console.error('Failed to parse user_info:', e)
                useAuthStore.setState({ _hasHydrated: true })
              }
            } else {
              useAuthStore.setState({ _hasHydrated: true })
            }
          }, 0)
        }
      },
      version: 2,
      migrate: (persistedState: any, version: number) => {
        if (version < 2) {
          // 清除旧版本数据
          localStorage.removeItem('user_info')
          return {
            token: null,
            refreshToken: null,
            isAuthenticated: false,
            _hasHydrated: false,
          }
        }
        return persistedState
      },
    }
  )
)


