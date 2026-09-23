import axios, { AxiosError, AxiosInstance, AxiosRequestConfig, AxiosResponse, InternalAxiosRequestConfig } from 'axios'
import { useAuthStore } from '@/store/authStore'

type RetriableRequestConfig = InternalAxiosRequestConfig & { _retry?: boolean }

interface StandardApiErrorResponse {
  success?: boolean
  code?: number
  message?: string
}

// 创建 axios 实例
const request: AxiosInstance = axios.create({
  baseURL: '',
  timeout: 90000,
  headers: {
    'Content-Type': 'application/json',
  },
})

// 是否正在刷新Token
let isRefreshing = false
// 等待刷新完成的请求队列
let refreshSubscribers: Array<{
  resolve: (token: string) => void
  reject: (error: Error) => void
}> = []

/** 判断后端统一响应体是否表示认证失败。 */
const isUnauthorizedBusinessResponse = (data: unknown): boolean => {
  if (!data || typeof data !== 'object') return false
  const response = data as StandardApiErrorResponse
  return response.success === false && response.code === 401
}

/** 从统一响应中提取面向用户的认证失败提示。 */
const createAuthenticationError = (data?: unknown): Error => {
  if (data && typeof data === 'object') {
    const response = data as StandardApiErrorResponse
    if (response.code === 401) return new Error('登录状态已过期，请重新登录')
    const message = response.message
    if (message) return new Error(message)
  }
  return new Error('登录状态已失效，请重新登录')
}

/** 将请求加入当前刷新令牌任务的等待队列。 */
const waitForTokenRefresh = () => new Promise<string>((resolve, reject) => {
  refreshSubscribers.push({ resolve, reject })
})

/** 通知所有等待请求使用新令牌重试。 */
const onRefreshed = (token: string) => {
  refreshSubscribers.forEach(({ resolve }) => resolve(token))
  refreshSubscribers = []
}

/** 通知所有等待请求刷新失败，避免请求永久卡住。 */
const onRefreshFailed = (error: Error) => {
  refreshSubscribers.forEach(({ reject }) => reject(error))
  refreshSubscribers = []
}

/** 用刷新令牌获取新的访问令牌；并发请求共用同一次刷新。 */
const refreshAccessToken = async (): Promise<string> => {
  if (isRefreshing) return waitForTokenRefresh()

  const refreshToken = localStorage.getItem('refresh_token')
  if (!refreshToken) {
    const error = new Error('登录已过期，请重新登录')
    useAuthStore.getState().clearAuth()
    throw error
  }

  isRefreshing = true
  try {
    // 刷新接口使用独立 axios 调用，避免再次进入本实例的鉴权拦截器。
    const response = await axios.post('/api/v1/auth/refresh', {}, {
      headers: { Authorization: `Bearer ${refreshToken}` },
    })
    const data = response.data
    if (!data?.success || !data.token || !data.refresh_token) {
      throw createAuthenticationError(data)
    }

    const authStore = useAuthStore.getState()
    authStore.updateTokens(data.token, data.refresh_token)
    if (data.user_id && data.username !== undefined && data.is_admin !== undefined) {
      authStore.updateUser({
        user_id: data.user_id,
        username: data.username,
        is_admin: data.is_admin,
        account_limit: data.account_limit,
      })
    }
    onRefreshed(data.token)
    return data.token
  } catch (reason) {
    const error = reason instanceof Error
      ? reason
      : new Error('登录已过期，请重新登录')
    useAuthStore.getState().clearAuth()
    onRefreshFailed(error)
    throw error
  } finally {
    isRefreshing = false
  }
}

/** 统一处理 HTTP 401 与项目统一响应体中的 code=401。 */
const retryAfterTokenRefresh = async (
  originalRequest: RetriableRequestConfig,
  failureData?: unknown,
): Promise<AxiosResponse> => {
  if (originalRequest._retry || originalRequest.url?.includes('/auth/refresh')) {
    const error = createAuthenticationError(failureData)
    useAuthStore.getState().clearAuth()
    throw error
  }

  originalRequest._retry = true
  const token = await refreshAccessToken()
  if (originalRequest.headers) {
    originalRequest.headers.Authorization = `Bearer ${token}`
  }
  return request(originalRequest)
}

// 请求拦截器
request.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem('auth_token')
    if (token) {
      config.headers.Authorization = `Bearer ${token}`
    }
    // FormData 需要让浏览器自动设置 multipart/form-data + boundary，不能强制指定 JSON
    if (config.data instanceof FormData) {
      delete config.headers['Content-Type']
    }
    return config
  },
  (error) => {
    return Promise.reject(error)
  }
)

// 响应拦截器
request.interceptors.response.use(
  async (response: AxiosResponse) => {
    // 后端按项目规范将鉴权异常也包装为 HTTP 200，因此需同时检查响应体 code。
    if (isUnauthorizedBusinessResponse(response.data)) {
      return retryAfterTokenRefresh(response.config as RetriableRequestConfig, response.data)
    }
    return response
  },
  async (error: AxiosError) => {
    const originalRequest = error.config as RetriableRequestConfig | undefined
    if (error.response?.status === 401 && originalRequest) {
      return retryAfterTokenRefresh(originalRequest, error.response.data)
    }
    return Promise.reject(error)
  }
)

// 封装 GET 请求
export const get = async <T = unknown>(
  url: string,
  config?: AxiosRequestConfig
): Promise<T> => {
  const response = await request.get<T>(url, config)
  return response.data
}

// 封装 POST 请求
export const post = async <T = unknown>(
  url: string,
  data?: unknown,
  config?: AxiosRequestConfig
): Promise<T> => {
  const response = await request.post<T>(url, data, config)
  return response.data
}

// 封装 PUT 请求
export const put = async <T = unknown>(
  url: string,
  data?: unknown,
  config?: AxiosRequestConfig
): Promise<T> => {
  const response = await request.put<T>(url, data, config)
  return response.data
}

// 封装 DELETE 请求
export const del = async <T = unknown>(
  url: string,
  config?: AxiosRequestConfig
): Promise<T> => {
  const response = await request.delete<T>(url, config)
  return response.data
}

// 封装 PATCH 请求
export const patch = async <T = unknown>(
  url: string,
  data?: unknown,
  config?: AxiosRequestConfig
): Promise<T> => {
  const response = await request.patch<T>(url, data, config)
  return response.data
}

// 复用 utils/apiError.ts 的实现，保留 re-export 以兼容 `import { getApiErrorMessage } from '@/utils/request'` 的旧调用点
export { getApiErrorMessage } from './apiError'

export default request
