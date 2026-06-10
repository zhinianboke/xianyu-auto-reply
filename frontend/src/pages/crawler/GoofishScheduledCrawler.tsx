import { useEffect, useMemo, useRef, useState } from 'react'
import { ExternalLink, Play, RefreshCw, Square, Trash2, Eye, Clock } from 'lucide-react'
import { motion } from 'framer-motion'
import { getAccountDetails } from '@/api/accounts'
import {
  createGoofishCrawlJob,
  deleteGoofishCrawlJob,
  listGoofishCrawlItems,
  listGoofishCrawlJobs,
  runOnceGoofishCrawlJob,
  startGoofishCrawlJob,
  stopGoofishCrawlJob,
  type GoofishCrawlItem,
  type GoofishCrawlJob,
} from '@/api/goofishCrawler'
import { PageLoading } from '@/components/common/Loading'
import { Select } from '@/components/common/Select'
import { ConfirmModal } from '@/components/common/ConfirmModal'
import { useUIStore } from '@/store/uiStore'
import type { AccountDetail } from '@/types'
import { cn } from '@/utils/cn'

function formatDateTime(value?: string) {
  if (!value) return '-'
  const d = new Date(value)
  if (Number.isNaN(d.getTime())) return value
  return d.toLocaleString()
}

function secondsToText(seconds: number) {
  if (!Number.isFinite(seconds) || seconds <= 0) return '-'
  if (seconds < 60) return `${seconds}s`
  if (seconds % 60 === 0) return `${seconds / 60}min`
  return `${Math.floor(seconds / 60)}min ${seconds % 60}s`
}

function StatPill({ label, value }: { label: string; value: string }) {
  return (
    <div className="px-3 py-1.5 rounded-full bg-slate-100 dark:bg-slate-800 text-xs text-slate-700 dark:text-slate-200">
      <span className="text-slate-500 dark:text-slate-400 mr-1">{label}</span>
      <span className="font-medium">{value}</span>
    </div>
  )
}

export function GoofishScheduledCrawler() {
  const { addToast } = useUIStore()

  const [loadingPage, setLoadingPage] = useState(true)
  const [loadingAction, setLoadingAction] = useState(false)
  const refreshTimerRef = useRef<number | null>(null)

  const [accounts, setAccounts] = useState<AccountDetail[]>([])
  const accountOptions = useMemo(
    () =>
      accounts.map((a) => ({
        value: a.id,
        label: `${a.id}${a.enabled === false ? '（已禁用）' : ''}${a.show_browser ? '（显示浏览器）' : ''}`,
        disabled: a.enabled === false,
      })),
    [accounts],
  )

  const [jobs, setJobs] = useState<GoofishCrawlJob[]>([])

  const [cookieId, setCookieId] = useState('')
  const [keyword, setKeyword] = useState('')
  const [intervalSeconds, setIntervalSeconds] = useState(900)

  const [startPage, setStartPage] = useState(1)
  const [pages, setPages] = useState(1)
  const [pageSize, setPageSize] = useState(20)
  const [fetchDetail, setFetchDetail] = useState(true)
  const [detailLimit, setDetailLimit] = useState(20)
  const [enabled, setEnabled] = useState(true)

  const [itemsModalOpen, setItemsModalOpen] = useState(false)
  const [itemsJob, setItemsJob] = useState<GoofishCrawlJob | null>(null)
  const [itemsLoading, setItemsLoading] = useState(false)
  const [items, setItems] = useState<GoofishCrawlItem[]>([])
  const [deleteJob, setDeleteJob] = useState<GoofishCrawlJob | null>(null)

  const loadAccountsAndJobs = async () => {
    try {
      setLoadingPage(true)
      const [accsRes, jobsRes] = await Promise.all([getAccountDetails(), listGoofishCrawlJobs()])
      setAccounts(accsRes)
      setJobs(jobsRes.jobs || [])
      const firstEnabled = accsRes.find((a) => a.enabled !== false) || accsRes[0]
      if (firstEnabled && !cookieId) setCookieId(firstEnabled.id)
    } catch {
      addToast({ type: 'error', message: '加载数据失败' })
    } finally {
      setLoadingPage(false)
    }
  }

  const refreshJobs = async () => {
    try {
      const res = await listGoofishCrawlJobs()
      setJobs(res.jobs || [])
    } catch {
      // ignore background refresh errors
    }
  }

  useEffect(() => {
    loadAccountsAndJobs()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    if (refreshTimerRef.current) window.clearInterval(refreshTimerRef.current)
    refreshTimerRef.current = window.setInterval(() => {
      refreshJobs()
    }, 5000)
    return () => {
      if (refreshTimerRef.current) window.clearInterval(refreshTimerRef.current)
      refreshTimerRef.current = null
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const openItems = async (job: GoofishCrawlJob) => {
    setItemsJob(job)
    setItemsModalOpen(true)
    setItems([])
    try {
      setItemsLoading(true)
      const res = await listGoofishCrawlItems(job.id, { limit: 50, offset: 0 })
      setItems(res.items || [])
    } catch {
      addToast({ type: 'error', message: '加载采集结果失败' })
    } finally {
      setItemsLoading(false)
    }
  }

  const createJob = async (e?: React.FormEvent) => {
    e?.preventDefault()
    if (!cookieId) {
      addToast({ type: 'warning', message: '请先选择账号' })
      return
    }
    if (!keyword.trim()) {
      addToast({ type: 'warning', message: '请填写关键词' })
      return
    }
    if (!Number.isFinite(intervalSeconds) || intervalSeconds < 60) {
      addToast({ type: 'warning', message: '间隔至少 60 秒' })
      return
    }

    try {
      setLoadingAction(true)
      const res = await createGoofishCrawlJob({
        cookie_id: cookieId,
        keyword: keyword.trim(),
        interval_seconds: intervalSeconds,
        start_page: startPage,
        pages,
        page_size: pageSize,
        fetch_detail: fetchDetail,
        detail_limit: detailLimit,
        enabled,
      })
      if (!res.success) {
        addToast({ type: 'error', message: res.message || '创建失败' })
        return
      }
      addToast({ type: 'success', message: `已创建任务 #${res.job_id}` })
      setKeyword('')
      await refreshJobs()
    } catch {
      addToast({ type: 'error', message: '创建失败' })
    } finally {
      setLoadingAction(false)
    }
  }

  const runOnce = async (job: GoofishCrawlJob) => {
    try {
      setLoadingAction(true)
      addToast({ type: 'info', message: '开始执行一次采集，请稍候…', duration: 2500 })
      const res = await runOnceGoofishCrawlJob(job.id)
      if (!res.success) {
        addToast({ type: 'error', message: res.error || '执行失败' })
      } else {
        addToast({ type: 'success', message: `执行完成：写入 ${res.upserted} 条（抓到 ${res.total} 条）` })
      }
      await refreshJobs()
      if (itemsModalOpen && itemsJob?.id === job.id) {
        await openItems(job)
      }
    } catch {
      addToast({ type: 'error', message: '执行失败' })
    } finally {
      setLoadingAction(false)
    }
  }

  const start = async (job: GoofishCrawlJob) => {
    try {
      setLoadingAction(true)
      await startGoofishCrawlJob(job.id)
      addToast({ type: 'success', message: '已启动' })
      await refreshJobs()
    } catch {
      addToast({ type: 'error', message: '启动失败' })
    } finally {
      setLoadingAction(false)
    }
  }

  const stop = async (job: GoofishCrawlJob) => {
    try {
      setLoadingAction(true)
      await stopGoofishCrawlJob(job.id)
      addToast({ type: 'success', message: '已停止' })
      await refreshJobs()
    } catch {
      addToast({ type: 'error', message: '停止失败' })
    } finally {
      setLoadingAction(false)
    }
  }

  const remove = async (job: GoofishCrawlJob) => {
    try {
      setLoadingAction(true)
      await deleteGoofishCrawlJob(job.id)
      addToast({ type: 'success', message: '已删除' })
      await refreshJobs()
      if (itemsModalOpen && itemsJob?.id === job.id) {
        setItemsModalOpen(false)
        setItemsJob(null)
        setItems([])
      }
    } catch {
      addToast({ type: 'error', message: '删除失败' })
    } finally {
      setLoadingAction(false)
    }
  }

  if (loadingPage) return <PageLoading />

  const runningCount = jobs.filter((j) => j.running).length
  const enabledCount = jobs.filter((j) => j.enabled).length

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-3">
        <div>
          <h1 className="page-title">Goofish 定时采集</h1>
          <p className="page-description">选择账号 Cookie，定时通过浏览器采集 Goofish 商品数据。</p>
        </div>
        <div className="flex items-center gap-2">
          <button onClick={loadAccountsAndJobs} className="btn-ios-secondary" disabled={loadingAction}>
            <RefreshCw className="w-4 h-4" />
            刷新
          </button>
        </div>
      </div>

      <div className="flex flex-wrap gap-2">
        <StatPill label="任务" value={`${jobs.length}`} />
        <StatPill label="启用" value={`${enabledCount}`} />
        <StatPill label="运行中" value={`${runningCount}`} />
      </div>

      <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} className="vben-card">
        <div className="vben-card-body">
          <form onSubmit={createJob} className="space-y-3">
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-3">
              <div className="input-group">
                <label className="input-label">账号（Cookie）</label>
                <Select value={cookieId} onChange={setCookieId} options={accountOptions} placeholder="请选择账号" />
              </div>
              <div className="input-group lg:col-span-2">
                <label className="input-label">关键词</label>
                <input
                  value={keyword}
                  onChange={(e) => setKeyword(e.target.value)}
                  className="input-ios"
                  placeholder="例如：iPhone 15 / 显卡 / 相机"
                />
              </div>
            </div>

            <div className="grid grid-cols-2 lg:grid-cols-6 gap-3">
              <div className="input-group">
                <label className="input-label">间隔（秒）</label>
                <div className="relative">
                  <Clock className="absolute left-4 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400 dark:text-slate-500" />
                  <input
                    type="number"
                    min={60}
                    max={86400}
                    value={intervalSeconds}
                    onChange={(e) => setIntervalSeconds(e.target.value ? Number(e.target.value) : 900)}
                    className="input-ios pl-12"
                  />
                </div>
                <div className="text-xs text-slate-500 mt-1">当前：{secondsToText(intervalSeconds)}</div>
              </div>
              <div className="input-group">
                <label className="input-label">起始页</label>
                <input type="number" min={1} max={50} value={startPage} onChange={(e) => setStartPage(Number(e.target.value || 1))} className="input-ios" />
              </div>
              <div className="input-group">
                <label className="input-label">抓取页数</label>
                <input type="number" min={1} max={10} value={pages} onChange={(e) => setPages(Number(e.target.value || 1))} className="input-ios" />
              </div>
              <div className="input-group">
                <label className="input-label">每页条数</label>
                <input type="number" min={1} max={50} value={pageSize} onChange={(e) => setPageSize(Number(e.target.value || 20))} className="input-ios" />
              </div>
              <div className="input-group">
                <label className="input-label">抓详情</label>
                <label className="flex items-center gap-2 h-10">
                  <input type="checkbox" checked={fetchDetail} onChange={(e) => setFetchDetail(e.target.checked)} className="accent-blue-600" />
                  <span className="text-sm text-slate-600 dark:text-slate-300">二级页</span>
                </label>
              </div>
              <div className="input-group">
                <label className="input-label">详情上限</label>
                <input type="number" min={0} max={50} value={detailLimit} onChange={(e) => setDetailLimit(Number(e.target.value || 0))} className="input-ios" />
              </div>
            </div>

            <div className="flex items-center justify-between flex-wrap gap-2">
              <label className="flex items-center gap-2">
                <input type="checkbox" checked={enabled} onChange={(e) => setEnabled(e.target.checked)} className="accent-blue-600" />
                <span className="text-sm text-slate-600 dark:text-slate-300">创建后自动启用</span>
              </label>
              <button type="submit" className="btn-ios-primary" disabled={loadingAction}>
                创建任务
              </button>
            </div>
          </form>
        </div>
      </motion.div>

      <div className="vben-card">
        <div className="vben-card-body">
          <div className="flex items-center justify-between mb-3">
            <div className="text-sm font-semibold text-slate-900 dark:text-slate-100">任务列表</div>
            <div className="text-xs text-slate-500">每 5 秒自动刷新状态</div>
          </div>

          {jobs.length === 0 ? (
            <div className="text-sm text-slate-500">暂无任务</div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left text-slate-500 border-b border-slate-200 dark:border-slate-700">
                    <th className="py-2 pr-3">#</th>
                    <th className="py-2 pr-3">账号</th>
                    <th className="py-2 pr-3">关键词</th>
                    <th className="py-2 pr-3">间隔</th>
                    <th className="py-2 pr-3">状态</th>
                    <th className="py-2 pr-3">最后执行</th>
                    <th className="py-2 pr-3">错误</th>
                    <th className="py-2 pr-3 text-right">操作</th>
                  </tr>
                </thead>
                <tbody>
                  {jobs.map((job) => (
                    <tr key={job.id} className="border-b border-slate-100 dark:border-slate-800">
                      <td className="py-2 pr-3 font-mono text-xs text-slate-600 dark:text-slate-300">{job.id}</td>
                      <td className="py-2 pr-3 font-mono text-xs text-slate-700 dark:text-slate-200">{job.cookie_id}</td>
                      <td className="py-2 pr-3 text-slate-900 dark:text-slate-100">{job.keyword}</td>
                      <td className="py-2 pr-3 text-slate-700 dark:text-slate-200">{secondsToText(job.interval_seconds)}</td>
                      <td className="py-2 pr-3">
                        <span
                          className={cn(
                            'px-2 py-1 rounded-full text-xs',
                            job.enabled
                              ? job.running
                                ? 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-300'
                                : 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300'
                              : 'bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300',
                          )}
                        >
                          {job.enabled ? (job.running ? '运行中' : '已启用') : '已停止'}
                        </span>
                      </td>
                      <td className="py-2 pr-3 text-slate-700 dark:text-slate-200">{formatDateTime(job.last_run_at)}</td>
                      <td className="py-2 pr-3 max-w-[260px] truncate text-slate-500" title={job.last_error || ''}>
                        {job.last_error || '-'}
                      </td>
                      <td className="py-2 pr-3">
                        <div className="flex justify-end gap-2">
                          <button
                            className="btn-ios-secondary !px-2 !py-1.5"
                            onClick={() => openItems(job)}
                            disabled={loadingAction}
                            title="查看采集结果"
                          >
                            <Eye className="w-4 h-4" />
                          </button>
                          <button
                            className="btn-ios-secondary !px-2 !py-1.5"
                            onClick={() => runOnce(job)}
                            disabled={loadingAction}
                            title="立即执行一次"
                          >
                            <Play className="w-4 h-4" />
                          </button>
                          {job.enabled ? (
                            <button
                              className="btn-ios-secondary !px-2 !py-1.5"
                              onClick={() => stop(job)}
                              disabled={loadingAction}
                              title="停止"
                            >
                              <Square className="w-4 h-4" />
                            </button>
                          ) : (
                            <button
                              className="btn-ios-secondary !px-2 !py-1.5"
                              onClick={() => start(job)}
                              disabled={loadingAction}
                              title="启动"
                            >
                              <Play className="w-4 h-4" />
                            </button>
                          )}
                          <button
                            className="btn-ios-danger !px-2 !py-1.5"
                            onClick={() => setDeleteJob(job)}
                            disabled={loadingAction}
                            title="删除"
                          >
                            <Trash2 className="w-4 h-4" />
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>

      {itemsModalOpen && (
        <div className="fixed inset-0 z-50">
          <div
            className="absolute inset-0 bg-black/50"
            onClick={() => {
              setItemsModalOpen(false)
              setItemsJob(null)
            }}
          />
          <div className="absolute inset-x-3 top-16 md:inset-x-16 lg:inset-x-40">
            <div className="vben-card">
              <div className="vben-card-body">
                <div className="flex items-center justify-between gap-3 mb-3">
                  <div className="min-w-0">
                    <div className="text-sm font-semibold text-slate-900 dark:text-slate-100 truncate">
                      采集结果 {itemsJob ? `#${itemsJob.id}` : ''}
                    </div>
                    <div className="text-xs text-slate-500 truncate">
                      {itemsJob ? `${itemsJob.cookie_id} · ${itemsJob.keyword}` : ''}
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <button
                      className="btn-ios-secondary"
                      onClick={() => itemsJob && openItems(itemsJob)}
                      disabled={itemsLoading}
                    >
                      <RefreshCw className="w-4 h-4" />
                      刷新
                    </button>
                    <button
                      className="btn-ios-secondary"
                      onClick={() => {
                        setItemsModalOpen(false)
                        setItemsJob(null)
                      }}
                    >
                      关闭
                    </button>
                  </div>
                </div>

                {itemsLoading ? (
                  <div className="text-sm text-slate-500">加载中...</div>
                ) : items.length === 0 ? (
                  <div className="text-sm text-slate-500">暂无采集结果（可点击“立即执行一次”）</div>
                ) : (
                  <div className="space-y-2 max-h-[65vh] overflow-auto pr-1">
                    {items.map((it) => (
                      <div key={it.item_id} className="p-3 rounded-lg border border-slate-200 dark:border-slate-700">
                        <div className="flex items-start justify-between gap-3">
                          <div className="min-w-0">
                            <div className="text-sm font-medium text-slate-900 dark:text-slate-100 truncate">
                              {it.title || it.item_id}
                            </div>
                            <div className="text-xs text-slate-500 mt-0.5">
                              {it.price ? `￥${it.price}` : '-'}
                              {' · '}
                              想要 {it.want_count ?? 0}
                              {' · '}
                              浏览 {it.view_count ?? 0}
                              {' · '}
                              {formatDateTime(it.fetched_at)}
                            </div>
                          </div>
                          {it.item_url && (
                            <a className="btn-ios-secondary !px-2 !py-1.5" href={it.item_url} target="_blank" rel="noreferrer">
                              <ExternalLink className="w-4 h-4" />
                            </a>
                          )}
                        </div>
                        {it.detail_error && (
                          <div className="text-xs text-amber-600 dark:text-amber-300 mt-2">
                            详情错误：{it.detail_error}
                          </div>
                        )}
                        {it.description && (
                          <div className="text-xs text-slate-600 dark:text-slate-300 mt-2 line-clamp-3">
                            {it.description}
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      )}
      <ConfirmModal
        isOpen={!!deleteJob}
        title="删除采集任务"
        message={`确认删除任务 #${deleteJob?.id || ''} 吗？同时会删除采集结果。`}
        confirmText="删除"
        type="danger"
        loading={loadingAction}
        onConfirm={() => deleteJob && remove(deleteJob).finally(() => setDeleteJob(null))}
        onCancel={() => setDeleteJob(null)}
      />
    </div>
  )
}

