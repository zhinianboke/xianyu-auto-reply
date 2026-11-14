/** 注册状态读取完成前阻止表单操作；读取失败时允许重试。 */
import { Link } from 'react-router-dom'
import { AuthNavbar } from '@/components/common/AuthNavbar'
import { Loading } from '@/components/common/Loading'

interface RegistrationGateProps {
  error: string | null
  reload: () => void
}

export function RegistrationGate({ error, reload }: RegistrationGateProps) {
  return (
    <div className="min-h-screen bg-slate-50 dark:bg-slate-900">
      <AuthNavbar />
      {error ? (
        <div className="min-h-screen flex items-center justify-center p-4">
          <div className="w-full max-w-sm rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 p-6 shadow-sm text-center">
            <h1 className="text-lg vben-card-title text-slate-900 dark:text-slate-100 mb-3">读取注册状态失败</h1>
            <p className="text-sm text-slate-600 dark:text-slate-300 mb-5" role="alert">{error}</p>
            <button type="button" className="btn-ios-primary w-full" onClick={reload}>重新加载</button>
            <Link to="/login" className="mt-4 inline-block text-sm text-slate-600 dark:text-slate-300">返回登录</Link>
          </div>
        </div>
      ) : <Loading fullScreen text="正在读取注册状态..." />}
    </div>
  )
}
