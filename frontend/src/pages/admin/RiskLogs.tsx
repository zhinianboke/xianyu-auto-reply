/**
 * 风控日志页面
 * 
 * 功能：
 * 1. 显示风控日志列表
 * 2. 支持按账号筛选
 * 3. 支持按时间范围筛选
 * 4. 支持按处理状态筛选
 * 5. 支持分页
 * 6. 支持清空日志
 */
import { useState, useEffect } from 'react'
import { ShieldAlert, RefreshCw, Trash2, ChevronLeft, ChevronRight, Loader2, Calendar, Info, TrendingUp } from 'lucide-react'
import { getRiskLogs, clearRiskLogs, testRemoteSliderSolve, getRemoteCaptchaConfig, saveRemoteCaptchaConfig, getRiskTodaySuccessRate, type RiskLog, type RiskTodaySuccessRate } from '@/api/admin'
import { getAccountDetails } from '@/api/accounts'
import { useUIStore } from '@/store/uiStore'
import { useAuthStore } from '@/store/authStore'
import { PageLoading } from '@/components/common/Loading'
import { Select } from '@/components/common/Select'
import { ConfirmModal } from '@/components/common/ConfirmModal'
import { getApiErrorMessage } from '@/utils/request'
import type { Account } from '@/types'

export function RiskLogs() {
  const { addToast } = useUIStore()
  const { isAuthenticated, token, _hasHydrated, user } = useAuthStore()
  const [loading, setLoading] = useState(true)
  const [logs, setLogs] = useState<RiskLog[]>([])
  const [accounts, setAccounts] = useState<Account[]>([])
  const [selectedAccount, setSelectedAccount] = useState('')

  // 时间筛选 - 默认当天
  const today = new Date().toISOString().split('T')[0]
  const [startDate, setStartDate] = useState(today)
  const [endDate, setEndDate] = useState(today)

  // 状态筛选
  const [selectedStatus, setSelectedStatus] = useState('')

  // 调用类型筛选（''-全部 / local-本机 / remote-远程）
  const [selectedCallType, setSelectedCallType] = useState('')

  // 分页状态
  const [currentPage, setCurrentPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)
  const [total, setTotal] = useState(0)

  // 当日成功率
  const [todayRate, setTodayRate] = useState<RiskTodaySuccessRate | null>(null)

  // 清空确认弹窗状态
  const [clearConfirm, setClearConfirm] = useState(false)
  const [clearing, setClearing] = useState(false)

  // 远程过滑块配置（与个人设置一致，按用户存储于 user-settings）
  const [remoteUrl, setRemoteUrl] = useState('')
  const [remoteSecret, setRemoteSecret] = useState('')
  const [passCookies, setPassCookies] = useState(false)
  // real_mouse 过滑块本地/远程排队权重（字符串便于输入框编辑，保存时规整为非负数），默认 1
  const [localWeight, setLocalWeight] = useState('1')
  const [remoteWeight, setRemoteWeight] = useState('1')
  const [savingConfig, setSavingConfig] = useState(false)
  const [testing, setTesting] = useState(false)

  const loadLogs = async (nextPage: number = currentPage, nextPageSize: number = pageSize) => {
    if (!_hasHydrated || !isAuthenticated || !token) return
    try {
      setLoading(true)
      const result = await getRiskLogs({ 
        page: nextPage,
        pageSize: nextPageSize,
        cookie_id: selectedAccount || undefined,
        start_date: startDate || undefined,
        end_date: endDate || undefined,
        processing_status: selectedStatus || undefined,
        call_type: selectedCallType || undefined,
      })
      if (result.success) {
        setLogs(result.data || [])
        setCurrentPage(nextPage)
        setPageSize(nextPageSize)
        setTotal(result.total || 0)
      } else {
        setLogs([])
        setCurrentPage(nextPage)
        setPageSize(nextPageSize)
        setTotal(0)
        addToast({ type: 'error', message: result.message || '加载风控日志失败' })
      }
    } catch (error) {
      addToast({ type: 'error', message: getApiErrorMessage(error, '加载风控日志失败') })
    } finally {
      setLoading(false)
    }
  }

  // 加载当日成功率（独立于筛选条件，统计北京时间当天）
  const loadTodayRate = async () => {
    if (!_hasHydrated || !isAuthenticated || !token) return
    try {
      const res = await getRiskTodaySuccessRate()
      if (res.success && res.data) {
        setTodayRate(res.data)
      }
    } catch {
      // 成功率加载失败不阻断页面
    }
  }

  // 远程过滑块全局配置（仅管理员，存于 system_settings）
  const loadRemoteConfig = async () => {
    if (!_hasHydrated || !isAuthenticated || !token) return
    if (!user?.is_admin) return  // 仅管理员可查看/回显远程过滑块配置
    try {
      const res = await getRemoteCaptchaConfig()
      if (res.success && res.data) {
        setRemoteUrl(res.data.url || '')
        setRemoteSecret(res.data.secret_key || '')
        setPassCookies(!!res.data.pass_cookies)
        setLocalWeight(String(res.data.local_weight ?? 1))
        setRemoteWeight(String(res.data.remote_weight ?? 1))
      }
    } catch {
      // 回显失败不阻断页面
    }
  }

  const handleSaveRemoteConfig = async () => {
    try {
      setSavingConfig(true)
      // 权重规整：空串/非法回退 1，负数回退 1（与后端 _sanitize_weight 口径一致）
      const normWeight = (v: string) => {
        const n = Number(v)
        return Number.isFinite(n) && n >= 0 ? n : 1
      }
      const res = await saveRemoteCaptchaConfig(
        remoteUrl.trim(),
        remoteSecret.trim(),
        passCookies,
        normWeight(localWeight),
        normWeight(remoteWeight),
      )
      if (res.success) {
        addToast({ type: 'success', message: '远程过滑块配置已保存' })
      } else {
        addToast({ type: 'error', message: res.message || '保存失败' })
      }
    } catch (error) {
      addToast({ type: 'error', message: getApiErrorMessage(error, '保存失败') })
    } finally {
      setSavingConfig(false)
    }
  }

  const handleTestRemoteConfig = async () => {
    const url = remoteUrl.trim()
    if (!url) {
      addToast({ type: 'error', message: '请先填写远程服务URL' })
      return
    }
    try {
      setTesting(true)
      const res = await testRemoteSliderSolve(url, remoteSecret.trim())
      addToast({ type: res.success ? 'success' : 'error', message: res.message || (res.success ? '连接成功' : '连接失败') })
    } catch (error) {
      addToast({ type: 'error', message: getApiErrorMessage(error, '测试失败') })
    } finally {
      setTesting(false)
    }
  }

  const loadAccounts = async () => {
    if (!_hasHydrated || !isAuthenticated || !token) return
    try {
      const data = await getAccountDetails()
      setAccounts(data)
    } catch (error) {
      addToast({ type: 'error', message: getApiErrorMessage(error, '加载账号列表失败') })
    }
  }

  useEffect(() => {
    if (!_hasHydrated || !isAuthenticated || !token) return
    loadAccounts()
    loadLogs(1, pageSize)
    loadTodayRate()
    loadRemoteConfig()
  }, [_hasHydrated, isAuthenticated, token])

  // 查询按钮点击
  const handleSearch = () => {
    loadLogs(1, pageSize)
    loadTodayRate()
  }

  const handlePageChange = (nextPage: number) => {
    if (nextPage < 1 || nextPage > totalPages) {
      return
    }
    loadLogs(nextPage, pageSize)
  }

  const handlePageSizeChange = (nextPageSize: number) => {
    loadLogs(1, nextPageSize)
  }

  const handleClear = async () => {
    setClearing(true)
    try {
      await clearRiskLogs()
      addToast({ type: 'success', message: '日志已清空' })
      setClearConfirm(false)
      loadLogs(1, pageSize)
      loadTodayRate()
    } catch (error) {
      addToast({ type: 'error', message: getApiErrorMessage(error, '清空失败') })
    } finally {
      setClearing(false)
    }
  }

  // 分页计算
  const totalPages = Math.ceil(total / pageSize)
  const startIndex = (currentPage - 1) * pageSize + 1
  const endIndex = Math.min(currentPage * pageSize, total)

  if (loading && logs.length === 0) {
    return <PageLoading />
  }

  return (
    <div className="space-y-4">
      {/* 远程过滑块配置（仅管理员可见可操作；按用户保存/回显，存储逻辑与个人设置一致） */}
      {user?.is_admin && (
      <div className="vben-card">
        <div className="vben-card-body">
          {/* 配置说明提示条 */}
          <div className="flex items-start gap-2 mb-4 px-3 py-2.5 rounded-lg bg-blue-50 dark:bg-blue-500/10 border border-blue-100 dark:border-blue-500/20">
            <Info className="w-4 h-4 mt-0.5 shrink-0 text-blue-500 dark:text-blue-400" />
            <div className="text-xs leading-relaxed text-blue-700 dark:text-blue-300 space-y-0.5">
              <p>填写 <span className="font-medium">https://xy-api.zhinianboke.com/api/v1/captcha/slider-solve</span> 使用远程服务过滑块验证，提高成功率。</p>
              <p>秘钥请在 <span className="font-medium">xy.zhinianboke.com</span> 注册账号后，于个人设置中获取。</p>
            </div>
          </div>
          <div className="flex flex-wrap items-end gap-4">
            <div className="input-group flex-1 min-w-[260px]">
              <label className="input-label">远程服务URL</label>
              <input
                type="text"
                value={remoteUrl}
                onChange={(e) => setRemoteUrl(e.target.value)}
                placeholder="例如：https://your-host/api/v1/captcha/slider-solve"
                className="input-ios"
              />
            </div>
            <div className="input-group flex-1 min-w-[260px]">
              <label className="input-label">秘钥</label>
              <input
                type="text"
                value={remoteSecret}
                onChange={(e) => setRemoteSecret(e.target.value)}
                placeholder="个人设置中的秘钥"
                className="input-ios"
              />
            </div>
            <button
              onClick={handleSaveRemoteConfig}
              disabled={savingConfig}
              className="btn-ios-primary disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {savingConfig ? <Loader2 className="w-4 h-4 animate-spin" /> : null}
              保存
            </button>
            <button
              onClick={handleTestRemoteConfig}
              disabled={testing}
              className="btn-ios-secondary disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {testing ? <Loader2 className="w-4 h-4 animate-spin" /> : null}
              测试
            </button>
          </div>

          {/* 是否传递账号Cookie（默认关闭）：开启后调用远程接口时会把当前账号 Cookie 传给远程服务，
              远程端在验证链接过期时可凭 Cookie 自动重取新链接，提高成功率 */}
          <div className="flex items-start gap-3 mt-4">
            <button
              type="button"
              onClick={() => setPassCookies((v) => !v)}
              role="switch"
              aria-checked={passCookies}
              className={`relative inline-flex h-5 w-10 items-center rounded-full transition-colors shrink-0 mt-0.5 ${
                passCookies ? 'bg-blue-500' : 'bg-gray-300 dark:bg-slate-600'
              }`}
            >
              <span
                className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
                  passCookies ? 'translate-x-5' : 'translate-x-0.5'
                }`}
              />
            </button>
            <div className="text-sm">
              <p className="font-medium text-slate-700 dark:text-slate-200">调用远程接口时传递账号 Cookie</p>
              <p className="mt-0.5 text-xs text-amber-600 dark:text-amber-400">
                默认关闭。传递 Cookie 可进一步提高过滑块成功率（链接过期时远程端可凭此自动重取新链接），远程系统不会保存该值；请仅在信任该远程服务时开启。
              </p>
            </div>
          </div>

          {/* real_mouse 本机/远程排队权重：本机开启真实鼠标引擎时，物理光标同一时刻只能解一个滑块，
              本机自身任务与外部远程调用会排队。权重决定争抢时的放行比例（如 3:1），只在两边同时排队时生效。 */}
          <div className="mt-4 pt-4 border-t border-slate-100 dark:border-slate-700/60">
            <div className="flex flex-wrap items-end gap-4">
              <div className="input-group w-32">
                <label className="input-label">本地排队权重</label>
                <input
                  type="number"
                  min={0}
                  step={1}
                  value={localWeight}
                  onChange={(e) => setLocalWeight(e.target.value)}
                  className="input-ios"
                />
              </div>
              <div className="input-group w-32">
                <label className="input-label">远程排队权重</label>
                <input
                  type="number"
                  min={0}
                  step={1}
                  value={remoteWeight}
                  onChange={(e) => setRemoteWeight(e.target.value)}
                  className="input-ios"
                />
              </div>
              <p className="flex-1 min-w-[240px] text-xs text-slate-500 dark:text-slate-400 leading-relaxed">
                仅真实鼠标（real_mouse）过滑块引擎生效。物理光标同一时刻只解一个滑块，本地任务与外部远程调用同时排队时，按此比例放行（如 3:1 ≈ 每 4 个放 3 本地 1 远程）；一方空闲时另一方独占。默认 1:1。修改后随“保存”按钮一起生效。
              </p>
            </div>
          </div>
        </div>
      </div>
      )}

      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="page-title">风控日志</h1>
          <p className="page-description">查看账号风控相关日志</p>
        </div>
        <div className="flex gap-3">
          {user?.is_admin ? (
            <button onClick={() => setClearConfirm(true)} className="btn-ios-danger ">
              <Trash2 className="w-4 h-4" />
              清空日志
            </button>
          ) : null}
          <button onClick={() => { loadLogs(); loadTodayRate() }} disabled={loading} className="btn-ios-secondary ">
            {loading ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <RefreshCw className="w-4 h-4" />
            )}
            刷新
          </button>
        </div>
      </div>

      {/* Filter */}
      <div className="vben-card">
        <div className="vben-card-body">
          <div className="flex flex-wrap items-end gap-4">
            <div className="input-group">
              <label className="input-label">开始日期</label>
              <input
                type="date"
                value={startDate}
                onChange={(e) => setStartDate(e.target.value)}
                className="input-ios"
              />
            </div>
            <div className="input-group">
              <label className="input-label">结束日期</label>
              <input
                type="date"
                value={endDate}
                onChange={(e) => setEndDate(e.target.value)}
                className="input-ios"
              />
            </div>
            <div className="input-group">
              <label className="input-label">处理状态</label>
              <select
                value={selectedStatus}
                onChange={(e) => setSelectedStatus(e.target.value)}
                className="input-ios"
              >
                <option value="">全部状态</option>
                <option value="success">成功</option>
                <option value="failed">失败</option>
                <option value="processing">处理中</option>
                <option value="cancelled">已取消</option>
              </select>
            </div>
            <div className="input-group">
              <label className="input-label">调用类型</label>
              <select
                value={selectedCallType}
                onChange={(e) => setSelectedCallType(e.target.value)}
                className="input-ios"
              >
                <option value="">全部类型</option>
                <option value="local">本机</option>
                <option value="remote">远程</option>
              </select>
            </div>
            <div className="input-group min-w-[200px]">
              <label className="input-label">筛选账号</label>
              <Select
                value={selectedAccount}
                onChange={setSelectedAccount}
                options={[
                  { value: '', label: '全部账号', key: 'all' },
                  ...accounts.map((account) => ({
                    value: account.id,
                    label: account.note ? `${account.id} (${account.note})` : account.id,
                    key: account.pk?.toString() || account.id,
                  })),
                ]}
                placeholder="全部账号"
              />
            </div>
            <button onClick={handleSearch} className="btn-ios-primary">
              <Calendar className="w-4 h-4" />
              查询
            </button>
          </div>
        </div>
      </div>

      {/* 当日成功率（总体 / 本机 / 远程，紧凑展示） */}
      <div className="vben-card">
        <div className="vben-card-body !py-3">
          <div className="flex flex-wrap items-center gap-x-6 gap-y-2">
            <div className="flex items-center gap-2 text-sm text-slate-500 dark:text-slate-400">
              <TrendingUp className="w-4 h-4 text-emerald-500 dark:text-emerald-400" />
              <span>当日成功率{todayRate?.date ? `（${todayRate.date}）` : ''}</span>
            </div>
            {/* 总体 */}
            <div className="flex items-baseline gap-1.5">
              <span className="text-sm text-slate-500 dark:text-slate-400">总体</span>
              <span className="text-lg font-bold text-emerald-600 dark:text-emerald-400">
                {todayRate ? `${todayRate.rate}%` : '-'}
              </span>
              <span className="text-xs text-slate-400 dark:text-slate-500">
                ({todayRate?.success ?? '-'}/{todayRate?.total ?? '-'})
              </span>
            </div>
            {/* 本机 */}
            <div className="flex items-baseline gap-1.5">
              <span className="text-sm text-slate-500 dark:text-slate-400">本机</span>
              <span className="text-lg font-bold text-blue-600 dark:text-blue-400">
                {todayRate ? `${todayRate.local_rate}%` : '-'}
              </span>
              <span className="text-xs text-slate-400 dark:text-slate-500">
                ({todayRate?.local_success ?? '-'}/{todayRate?.local_total ?? '-'})
              </span>
            </div>
            {/* 远程 */}
            <div className="flex items-baseline gap-1.5">
              <span className="text-sm text-slate-500 dark:text-slate-400">远程</span>
              <span className="text-lg font-bold text-orange-600 dark:text-orange-400">
                {todayRate ? `${todayRate.remote_rate}%` : '-'}
              </span>
              <span className="text-xs text-slate-400 dark:text-slate-500">
                ({todayRate?.remote_success ?? '-'}/{todayRate?.remote_total ?? '-'})
              </span>
            </div>
            {/* 处理中（仅统计当日，未计入成功率分母） */}
            <div className="flex items-baseline gap-1.5">
              <span className="text-sm text-slate-500 dark:text-slate-400">处理中</span>
              <span className="text-lg font-bold text-amber-600 dark:text-amber-400">
                {todayRate?.processing ?? '-'}
              </span>
            </div>
          </div>
        </div>
      </div>

      {/* Logs List */}
      <div className="vben-card flex flex-col" style={{ height: 'calc(100vh - 380px)', minHeight: '400px' }}>
        <div className="vben-card-header flex-shrink-0">
          <h2 className="vben-card-title">
            <ShieldAlert className="w-4 h-4 text-amber-500" />
            风控日志
          </h2>
          <span className="badge-primary">{total} 条记录</span>
        </div>
        <div className="flex-1 overflow-auto">
          <table className="table-ios">
            <thead className="sticky top-0 bg-white dark:bg-slate-800 z-10">
              <tr>
                <th>账号ID</th>
                <th>事件描述</th>
                <th>处理结果</th>
                <th>处理状态</th>
                <th>验证引擎</th>
                <th>调用类型</th>
                <th>调用用户</th>
                <th>创建时间</th>
                <th>更新时间</th>
              </tr>
            </thead>
            <tbody>
              {logs.length === 0 ? (
                <tr>
                  <td colSpan={9} className="text-center py-8 text-slate-500 dark:text-slate-400">
                    <div className="flex flex-col items-center gap-2">
                      <ShieldAlert className="w-12 h-12 text-slate-300 dark:text-slate-600" />
                      <p>暂无风控日志</p>
                    </div>
                  </td>
                </tr>
              ) : (
                logs.map((log) => (
                  <tr key={log.id}>
                    <td className="font-medium text-blue-600 dark:text-blue-400">
                      {(() => {
                        const account = accounts.find(acc => acc.id === log.cookie_id)
                        return account?.note ? `${log.cookie_id} (${account.note})` : log.cookie_id
                      })()}
                    </td>
                    <td className="max-w-[200px] text-slate-500 dark:text-slate-400">
                      <span 
                        className="block truncate cursor-help" 
                        title={log.message}
                      >
                        {log.message || '-'}
                      </span>
                    </td>
                    <td className="max-w-[200px] text-slate-500 dark:text-slate-400">
                      <span 
                        className="block truncate cursor-help" 
                        title={log.processing_result}
                      >
                        {log.processing_result || '-'}
                      </span>
                    </td>
                    <td>
                      <span className={`text-xs px-2 py-1 rounded ${
                        log.processing_status === 'success' ? 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400' :
                        log.processing_status === 'failed' ? 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400' :
                        log.processing_status === 'processing' ? 'bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-400' :
                        'bg-gray-100 text-gray-700 dark:bg-gray-700 dark:text-gray-300'
                      }`}>
                        {log.processing_status === 'success' ? '成功' :
                         log.processing_status === 'failed' ? '失败' :
                         log.processing_status === 'processing' ? '处理中' :
                         log.processing_status === 'cancelled' ? '已取消' :
                         log.processing_status || '-'}
                      </span>
                    </td>
                    <td>
                      {log.captcha_engine === 'drissionpage' ? (
                        <span className="text-xs px-2 py-1 rounded bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-400">
                          兜底引擎
                        </span>
                      ) : log.captcha_engine === 'playwright' ? (
                        <span className="text-xs px-2 py-1 rounded bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400">
                          主引擎
                        </span>
                      ) : log.captcha_engine === 'real_mouse' ? (
                        <span className="text-xs px-2 py-1 rounded bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400">
                          真人鼠标
                        </span>
                      ) : log.captcha_engine === 'remote' ? (
                        <span className="text-xs px-2 py-1 rounded bg-cyan-100 text-cyan-700 dark:bg-cyan-900/30 dark:text-cyan-400">
                          远程接口
                        </span>
                      ) : (
                        <span className="text-slate-400 dark:text-slate-500">-</span>
                      )}
                    </td>
                    <td>
                      {log.call_type === 'remote' ? (
                        <span className="text-xs px-2 py-1 rounded bg-orange-100 text-orange-700 dark:bg-orange-900/30 dark:text-orange-400">
                          远程
                        </span>
                      ) : (
                        <span className="text-xs px-2 py-1 rounded bg-slate-100 text-slate-600 dark:bg-slate-700 dark:text-slate-300">
                          本机
                        </span>
                      )}
                    </td>
                    <td className="text-slate-500 dark:text-slate-400 text-sm whitespace-nowrap">
                      {log.call_user || '-'}
                    </td>
                    <td className="text-slate-500 dark:text-slate-400 text-sm whitespace-nowrap">
                      {new Date(log.created_at).toLocaleString()}
                    </td>
                    <td className="text-slate-500 dark:text-slate-400 text-sm whitespace-nowrap">
                      {log.updated_at ? new Date(log.updated_at).toLocaleString() : '-'}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
        
        {/* 分页组件 */}
        {total > 0 && (
          <div className="flex-shrink-0 vben-card-footer flex flex-col sm:flex-row items-center justify-between gap-4 px-4 py-3 border-t border-slate-200 dark:border-slate-700">
            <div className="flex items-center gap-2 text-sm text-slate-500 dark:text-slate-400">
              <span>每页</span>
              <select
                value={pageSize}
                onChange={(e) => handlePageSizeChange(Number(e.target.value))}
                className="px-2 py-1 border border-slate-300 dark:border-slate-600 rounded bg-white dark:bg-slate-800 text-slate-700 dark:text-slate-300"
              >
                <option value={10}>10</option>
                <option value={20}>20</option>
                <option value={50}>50</option>
                <option value={100}>100</option>
              </select>
              <span>条</span>
              <span className="ml-2">
                显示 {startIndex}-{endIndex} 条，共 {total} 条
              </span>
            </div>
            <div className="flex items-center gap-2">
              <button
                onClick={() => handlePageChange(currentPage - 1)}
                disabled={currentPage === 1}
                className="p-2 rounded border border-slate-300 dark:border-slate-600 disabled:opacity-50 disabled:cursor-not-allowed hover:bg-slate-100 dark:hover:bg-slate-700"
              >
                <ChevronLeft className="w-4 h-4" />
              </button>
              <span className="px-3 py-1 text-sm text-slate-600 dark:text-slate-400">
                第 {currentPage} / {totalPages || 1} 页
              </span>
              <button
                onClick={() => handlePageChange(currentPage + 1)}
                disabled={currentPage >= totalPages}
                className="p-2 rounded border border-slate-300 dark:border-slate-600 disabled:opacity-50 disabled:cursor-not-allowed hover:bg-slate-100 dark:hover:bg-slate-700"
              >
                <ChevronRight className="w-4 h-4" />
              </button>
            </div>
          </div>
        )}
      </div>

      {/* 清空确认弹窗 */}
      {user?.is_admin ? (
        <ConfirmModal
          isOpen={clearConfirm}
          title="清空确认"
          message="确定要清空所有风控日志吗？此操作不可恢复！"
          confirmText="清空"
          cancelText="取消"
          type="danger"
          loading={clearing}
          onConfirm={handleClear}
          onCancel={() => setClearConfirm(false)}
        />
      ) : null}
    </div>
  )
}
