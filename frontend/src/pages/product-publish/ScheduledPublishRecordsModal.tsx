/**
 * 定时发布规则记录弹窗。
 *
 * 功能：
 * 1. 分页展示指定规则的发布记录；
 * 2. 分页展示指定规则的触发记录；
 * 3. 支持单条或勾选批量删除触发记录；
 * 4. 使用固定高度表格容器，避免撑高浏览器页面。
 */
import { useCallback, useEffect, useRef, useState } from 'react'
import { CalendarClock, RefreshCw, ScrollText, Trash2, X } from 'lucide-react'
import {
  deleteScheduledPublishTriggerRecords,
  getScheduledPublishRecords,
  getScheduledPublishTriggerRecords,
  type ScheduledPublishRecord,
  type ScheduledPublishRule,
  type ScheduledPublishTriggerRecord,
} from '@/api/scheduledPublish'
import { ConfirmModal } from '@/components/common/ConfirmModal'
import { Loading } from '@/components/common/Loading'
import { Pager } from '@/components/common/Pager'
import { useUIStore } from '@/store/uiStore'
import { getApiErrorMessage } from '@/utils/apiError'

interface ScheduledPublishRecordsModalProps {
  rule: ScheduledPublishRule
  type: 'publish' | 'trigger'
  onClose: () => void
}

const formatDateTime = (value?: string | null): string => value ? value.replace('T', ' ') : '-'

export function ScheduledPublishRecordsModal({
  rule,
  type,
  onClose,
}: ScheduledPublishRecordsModalProps) {
  const { addToast } = useUIStore()
  const [publishRecords, setPublishRecords] = useState<ScheduledPublishRecord[]>([])
  const [triggerRecords, setTriggerRecords] = useState<ScheduledPublishTriggerRecord[]>([])
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)
  const [total, setTotal] = useState(0)
  const [totalPages, setTotalPages] = useState(0)
  const [loading, setLoading] = useState(true)
  const [selectedTriggerIds, setSelectedTriggerIds] = useState<Set<number>>(new Set())
  const [deleteTriggerIds, setDeleteTriggerIds] = useState<number[] | null>(null)
  const [deleting, setDeleting] = useState(false)
  const selectAllRef = useRef<HTMLInputElement>(null)
  const isPublish = type === 'publish'

  const loadRecords = useCallback(async (nextPage: number, nextPageSize = pageSize) => {
    setLoading(true)
    setSelectedTriggerIds(new Set())
    try {
      const response = isPublish
        ? await getScheduledPublishRecords(rule.id, nextPage, nextPageSize)
        : await getScheduledPublishTriggerRecords(rule.id, nextPage, nextPageSize)
      if (!response.success || !response.data) {
        setPublishRecords([])
        setTriggerRecords([])
        setTotal(0)
        setTotalPages(0)
        addToast({ type: 'error', message: response.message || '记录查询失败' })
        return
      }
      if (isPublish) setPublishRecords(response.data.list as ScheduledPublishRecord[])
      else setTriggerRecords(response.data.list as ScheduledPublishTriggerRecord[])
      setPage(response.data.page)
      setPageSize(response.data.page_size)
      setTotal(response.data.total)
      setTotalPages(response.data.total_pages)
    } catch (error) {
      setPublishRecords([])
      setTriggerRecords([])
      setTotal(0)
      setTotalPages(0)
      addToast({ type: 'error', message: getApiErrorMessage(error, '记录查询失败') })
    } finally {
      setLoading(false)
    }
  }, [addToast, isPublish, pageSize, rule.id])

  useEffect(() => {
    void loadRecords(1, 20)
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  const allTriggerRecordsSelected = triggerRecords.length > 0
    && triggerRecords.every((record) => selectedTriggerIds.has(record.id))
  const currentPageSelectedCount = triggerRecords.filter(
    (record) => selectedTriggerIds.has(record.id),
  ).length

  useEffect(() => {
    if (selectAllRef.current) {
      selectAllRef.current.indeterminate = currentPageSelectedCount > 0
        && !allTriggerRecordsSelected
    }
  }, [allTriggerRecordsSelected, currentPageSelectedCount])

  const toggleTriggerRecord = (recordId: number) => {
    setSelectedTriggerIds((current) => {
      const next = new Set(current)
      if (next.has(recordId)) next.delete(recordId)
      else next.add(recordId)
      return next
    })
  }

  const toggleAllTriggerRecords = () => {
    setSelectedTriggerIds((current) => {
      const next = new Set(current)
      if (allTriggerRecordsSelected) {
        triggerRecords.forEach((record) => next.delete(record.id))
      } else {
        triggerRecords.forEach((record) => next.add(record.id))
      }
      return next
    })
  }

  const confirmDeleteTriggerRecords = async () => {
    if (!deleteTriggerIds?.length) return
    const ids = deleteTriggerIds
    setDeleting(true)
    try {
      const response = await deleteScheduledPublishTriggerRecords(rule.id, ids)
      if (!response.success || !response.data) {
        addToast({ type: 'error', message: response.message || '触发记录删除失败' })
        return
      }
      addToast({ type: 'success', message: response.message || `成功删除 ${response.data.success_count} 条触发记录` })
      setDeleteTriggerIds(null)
      setSelectedTriggerIds(new Set())
      const nextTotal = Math.max(0, total - response.data.success_count)
      const lastPage = Math.max(1, Math.ceil(nextTotal / pageSize))
      await loadRecords(Math.min(page, lastPage), pageSize)
    } catch (error) {
      addToast({ type: 'error', message: getApiErrorMessage(error, '触发记录删除失败') })
    } finally {
      setDeleting(false)
    }
  }

  return (
    <div className="modal-overlay" role="dialog" aria-modal="true" aria-label={isPublish ? '定时发布记录' : '定时发布触发记录'}>
      <div className="modal-content flex h-[min(82vh,720px)] max-h-[92vh] max-w-6xl flex-col overflow-hidden">
        <div className="modal-header">
          <div>
            <h2 className="modal-title flex items-center gap-2">
              {isPublish ? <ScrollText className="h-5 w-5" /> : <CalendarClock className="h-5 w-5" />}
              {isPublish ? '发布记录' : '触发记录'}
            </h2>
            <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">规则：{rule.rule_name}</p>
          </div>
          <div className="flex items-center gap-2">
            {!isPublish && selectedTriggerIds.size > 0 && (
              <button
                type="button"
                className="inline-flex items-center gap-1.5 rounded-md bg-red-50 px-3 py-2 text-sm font-medium text-red-600 transition-colors hover:bg-red-100 disabled:cursor-not-allowed disabled:opacity-50 dark:bg-red-900/20 dark:text-red-400 dark:hover:bg-red-900/30"
                onClick={() => setDeleteTriggerIds(Array.from(selectedTriggerIds))}
                disabled={loading || deleting}
              >
                <Trash2 className="h-4 w-4" />
                删除选中（{selectedTriggerIds.size}）
              </button>
            )}
            <button
              type="button"
              className="btn-ios-secondary"
              onClick={() => void loadRecords(page, pageSize)}
              disabled={loading}
            >
              <RefreshCw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
              刷新
            </button>
            <button type="button" className="modal-close" onClick={onClose} aria-label="关闭">
              <X className="h-5 w-5" />
            </button>
          </div>
        </div>

        <div className="relative flex min-h-0 flex-1 flex-col">
          {loading && (
            <div className="absolute inset-0 z-20 flex items-center justify-center bg-white/80 backdrop-blur-sm dark:bg-slate-900/80">
              <Loading text={isPublish ? '正在查询发布记录...' : '正在查询触发记录...'} />
            </div>
          )}
          <div className="table-scroll flex-1">
            {isPublish ? (
              <table className="table-ios min-w-[1050px]">
                <thead><tr><th>账号</th><th>素材</th><th>发布结果</th><th>失败原因</th><th>发布日期</th><th>记录时间</th></tr></thead>
                <tbody>
                  {!loading && publishRecords.length === 0 ? (
                    <tr><td colSpan={6} className="py-20 text-center text-slate-400">暂无发布记录</td></tr>
                  ) : publishRecords.map((record) => (
                    <tr key={record.id}>
                      <td><p className="font-medium">{record.account_name}</p><p className="text-xs text-slate-400">{record.account_id}</p></td>
                      <td>
                        <p className="max-w-72 truncate">{record.material_title}</p>
                        {record.material_id !== null && <p className="text-xs text-slate-400">ID：{record.material_id}</p>}
                      </td>
                      <td><span className={record.publish_result === 'success' ? 'badge-success' : 'badge-danger'}>{record.publish_result_text}</span></td>
                      <td className="max-w-96 break-words text-slate-500 dark:text-slate-400">{record.failure_reason || '-'}</td>
                      <td className="whitespace-nowrap">{record.publish_date || '-'}</td>
                      <td className="whitespace-nowrap">{formatDateTime(record.created_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : (
              <table className="table-ios min-w-[980px]">
                <thead><tr>
                  <th className="w-12 !text-center">
                    <input
                      ref={selectAllRef}
                      type="checkbox"
                      checked={allTriggerRecordsSelected}
                      onChange={toggleAllTriggerRecords}
                      disabled={loading || deleting || triggerRecords.length === 0}
                      aria-label="全选当前页触发记录"
                      className="h-4 w-4 rounded border-slate-300 accent-blue-500 focus:ring-2 focus:ring-blue-500 disabled:cursor-not-allowed"
                    />
                  </th>
                  <th>账号</th><th>计划日期</th><th>下次触发时间</th><th>更新时间</th><th>操作</th>
                </tr></thead>
                <tbody>
                  {!loading && triggerRecords.length === 0 ? (
                    <tr><td colSpan={6} className="py-20 text-center text-slate-400">暂无触发记录</td></tr>
                  ) : triggerRecords.map((record) => (
                    <tr key={record.id} className={selectedTriggerIds.has(record.id) ? 'bg-blue-50 dark:bg-blue-900/10' : ''}>
                      <td className="!text-center">
                        <input
                          type="checkbox"
                          checked={selectedTriggerIds.has(record.id)}
                          onChange={() => toggleTriggerRecord(record.id)}
                          disabled={deleting}
                          aria-label={`选择账号 ${record.account_name} 的触发记录`}
                          className="h-4 w-4 rounded border-slate-300 accent-blue-500 focus:ring-2 focus:ring-blue-500 disabled:cursor-not-allowed"
                        />
                      </td>
                      <td><p className="font-medium">{record.account_name}</p><p className="text-xs text-slate-400">{record.account_id}</p></td>
                      <td className="whitespace-nowrap">{record.schedule_date || '-'}</td>
                      <td className="whitespace-nowrap font-medium text-slate-800 dark:text-slate-100">{formatDateTime(record.next_trigger_at)}</td>
                      <td className="whitespace-nowrap">{formatDateTime(record.updated_at)}</td>
                      <td>
                        <button
                          type="button"
                          className="whitespace-nowrap font-medium text-red-600 transition-colors hover:text-red-700 disabled:cursor-not-allowed disabled:opacity-50 dark:text-red-400 dark:hover:text-red-300"
                          onClick={() => setDeleteTriggerIds([record.id])}
                          disabled={deleting}
                        >
                          删除
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
          <Pager
            page={page}
            pageSize={pageSize}
            total={total}
            totalPages={totalPages}
            loading={loading}
            onPageChange={(nextPage) => void loadRecords(nextPage)}
            onPageSizeChange={(nextPageSize) => void loadRecords(1, nextPageSize)}
          />
        </div>
      </div>
      <ConfirmModal
        isOpen={!isPublish && deleteTriggerIds !== null}
        type="danger"
        title={deleteTriggerIds?.length === 1 ? '删除触发记录' : '批量删除触发记录'}
        confirmText={deleteTriggerIds?.length === 1 ? '删除' : '批量删除'}
        loading={deleting}
        message={`确定要删除选中的 ${deleteTriggerIds?.length ?? 0} 条触发记录吗？删除后，定时任务将在下次扫描时重新计算触发时间。`}
        onConfirm={() => void confirmDeleteTriggerRecords()}
        onCancel={() => { if (!deleting) setDeleteTriggerIds(null) }}
      />
    </div>
  )
}
