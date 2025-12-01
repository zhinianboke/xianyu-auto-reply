import { create } from 'zustand'
import { persist, createJSONStorage } from 'zustand/middleware'
import type { User } from '@/types'

interface AuthState {
  token: string | null
  user: User | null
  isAuthenticated: boolean
  _hasHydrated: boolean
  setAuth: (token: string, user: User) => void
  clearAuth: () => void
  updateUser: (user: Partial<User>) => void
  setHasHydrated: (state: boolean) => void
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      token: null,
      user: null,
      isAuthenticated: false,
      _hasHydrated: false,

      setAuth: (token, user) => {
        localStorage.setItem('auth_token', token)
        localStorage.setItem('user_info', JSON.stringify(user))
        set({ token, user, isAuthenticated: true })
      },

      clearAuth: () => {
        localStorage.removeItem('auth_token')
        localStorage.removeItem('user_info')
        set({ token: null, user: null, isAuthenticated: false })
      },

      updateUser: (userData) => {
        set((state) => ({
          user: state.user ? { ...state.user, ...userData } : null,
        }))
      },

      setHasHydrated: (hydrated) => {
        set({ _hasHydrated: hydrated })
      },
    }),
    {
      name: 'auth-storage',
      storage: createJSONStorage(() => localStorage),
      partialize: (state) => ({ 
        token: state.token, 
        user: state.user,
        isAuthenticated: state.isAuthenticated 
      }),
      onRehydrateStorage: () => {
        // 返回一个回调函数，在 hydration 完成后执行
        return (state) => {
          // 确保 localStorage 中的 auth_token 与 store 同步
          // axios 拦截器从 localStorage.getItem('auth_token') 读取
          if (state?.token) {
            localStorage.setItem('auth_token', state.token)
          }
          if (state?.user) {
            localStorage.setItem('user_info', JSON.stringify(state.user))
          }
          // 延迟设置，确保 store 已完全初始化
          setTimeout(() => {
            useAuthStore.setState({ _hasHydrated: true })
          }, 0)
        }
      },
    }
  )
)

