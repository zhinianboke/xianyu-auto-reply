/**
 * 商品定时发布规则列表页。
 *
 * 支持规则新建、按名称查询、分页展示及启用规则的自动执行。
 */
import { useCallback, useEffect, useRef, useState } from 'react'
import { CalendarClock, Plus, Search, TimerReset } from 'lucide-react'
import { getScheduledPublishRules, type ScheduledPublishRule } from '@/api/scheduledPublish'
import { Loading } from '@/components/common/Loading'
import { Pager } from '@/components/common/Pager'
import { useUIStore } from '@/store/uiStore'
import { getApiErrorMessage } from '@/utils/apiError'
import { ScheduledPublishRuleModal } from './ScheduledPublishRuleModal'
import { ScheduledPublishRecordsModal } from './ScheduledPublishRecordsModal'

const formatInterval = (minutes: number): string => `${minutes}分钟`

const formatDateTime = (value?: string | null): string => value ? value.replace('T', ' ') : '-'

const formatTimeRange = (start: string, end: string): string =>
  start && end ? `${start} - ${end}` : '配置待补全'

const formatIntervalRange = (minimum: number, maximum: number): string =>
  minimum > 0 && maximum > 0
    ? `${formatInterval(minimum)} - ${formatInterval(maximum)}`
    : '配置待补全'

export function ScheduledPublishRules() {
  const { addToast } = useUIStore()
  const [rules, setRules] = useState<ScheduledPublishRule[]>([])
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)
  const [total, setTotal] = useState(0)
  const [totalPages, setTotalPages] = useState(0)
  const [keywordDraft, setKeywordDraft] = useState('')
  const [appliedKeyword, setAppliedKeyword] = useState('')
  const [loading, setLoading] = useState(true)
  const [showCreateModal, setShowCreateModal] = useState(false)
  const [editingRule, setEditingRule] = useState<ScheduledPublishRule | null>(null)
  const [recordsModal, setRecordsModal] = useState<{
    rule: ScheduledPublishRule
    type: 'publish' | 'trigger'
  } | null>(null)
  const requestSequenceRef = useRef(0)

  const loadRules = useCallback(async (
    nextPage: number,
    nextPageSize = pageSize,
    keyword = appliedKeyword,
  ) => {
    const requestSequence = requestSequenceRef.current + 1
    requestSequenceRef.current = requestSequence
    setLoading(true)
    try {
      const response = await getScheduledPublishRules(nextPage, nextPageSize, keyword)
      if (requestSequence !== requestSequenceRef.current) return
      if (!response.success || !response.data) {
        setRules([])
        setPage(nextPage)
        setTotal(0)
        setTotalPages(0)
        addToast({ type: 'error', message: response.message || '定时发布规则查询失败' })
        return
      }
      setRules(response.data.list)
      setPage(response.data.page)
      setPageSize(response.data.page_size)
      setTotal(response.data.total)
      setTotalPages(response.data.total_pages)
    } catch (error) {
      if (requestSequence !== requestSequenceRef.current) return
      setRules([])
      setPage(nextPage)
      setTotal(0)
      setTotalPages(0)
      addToast({ type: 'error', message: getApiErrorMessage(error, '定时发布规则查询失败') })
    } finally {
      if (requestSequence === requestSequenceRef.current) setLoading(false)
    }
  }, [addToast, appliedKeyword, pageSize])

  useEffect(() => {
    void loadRules(1, 20, '')
    return () => { requestSequenceRef.current += 1 }
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  const handleSearch = () => {
    const keyword = keywordDraft.trim()
    setAppliedKeyword(keyword)
    void loadRules(1, pageSize, keyword)
  }

  const handleReset = () => {
    setKeywordDraft('')
    setAppliedKeyword('')
    void loadRules(1, pageSize, '')
  }

  return (
    <div className="flex min-h-0 flex-col space-y-3 sm:space-y-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="page-title">定时发布</h1>
          <p className="page-description">配置多账号、多素材的定时发布规则，系统将按规则自动执行商品发布</p>
        </div>
        <button type="button" className="btn-ios-primary" onClick={() => setShowCreateModal(true)}>
          <Plus className="h-4 w-4" />新建定时发布规则
        </button>
      </div>

      <div className="vben-card p-4">
        <div className="flex flex-wrap items-end gap-4">
          <div className="input-group w-full sm:w-72">
            <label className="input-label">规则名称</label>
            <div className="relative">
              <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
              <input
                className="input-ios pl-9"
                value={keywordDraft}
                onChange={(event) => setKeywordDraft(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === 'Enter') {
                    event.preventDefault()
                    handleSearch()
                  }
                }}
                placeholder="输入规则名称关键词"
                maxLength={120}
              />
            </div>
          </div>
          <div className="ml-auto flex gap-2">
            {appliedKeyword && <button type="button" className="btn-ios-secondary" onClick={handleReset}>重置</button>}
            <button type="button" className="btn-ios-primary" onClick={handleSearch} disabled={loading}>查询</button>
          </div>
        </div>
      </div>

      <div className="vben-card relative flex h-[440px] min-h-0 flex-col overflow-hidden sm:h-[520px] lg:h-[calc(100vh-270px)] lg:min-h-[440px]">
        {loading && (
          <div className="absolute inset-0 z-20 flex items-center justify-center bg-white/80 backdrop-blur-sm dark:bg-slate-900/80">
            <Loading text="正在查询定时发布规则..." />
          </div>
        )}
        <div className="table-scroll">
          <table className="table-ios min-w-[1250px]">
            <thead>
              <tr>
                <th>规则名称</th>
                <th>账号</th>
                <th>素材</th>
                <th>触发时间范围</th>
                <th>随机时间范围</th>
                <th>创建时间</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              {!loading && rules.length === 0 ? (
                <tr>
                  <td colSpan={7} className="py-20 text-center">
                    <CalendarClock className="mx-auto mb-3 h-12 w-12 text-slate-300 dark:text-slate-600" />
                    <p className="text-sm text-slate-500 dark:text-slate-400">{appliedKeyword ? '没有符合查询条件的定时发布规则' : '暂无定时发布规则，请点击右上角新建'}</p>
                  </td>
                </tr>
              ) : rules.map((rule) => (
                <tr key={rule.id}>
                  <td className="max-w-52 font-medium text-slate-900 dark:text-slate-100">{rule.rule_name}</td>
                  <td>
                    <div className="flex max-w-72 flex-wrap gap-1">
                      {rule.account_names.slice(0, 3).map((name, index) => <span key={`${rule.id}-account-${index}`} className="badge-info">{name}</span>)}
                      {rule.account_names.length > 3 && <span className="badge-gray">+{rule.account_names.length - 3}</span>}
                    </div>
                    <p className="mt-1 text-xs text-slate-400">共 {rule.account_ids.length} 个账号</p>
                  </td>
                  <td>
                    <div className="max-w-80 space-y-1">
                      {rule.material_titles.slice(0, 2).map((title, index) => <p key={`${rule.id}-material-${index}`} className="truncate text-sm">{title}</p>)}
                      {rule.material_titles.length > 2 && <p className="text-xs text-slate-400">另有 {rule.material_titles.length - 2} 条素材</p>}
                    </div>
                  </td>
                  <td><span className="badge-primary"><CalendarClock className="mr-1 h-3.5 w-3.5" />{formatTimeRange(rule.trigger_start_time, rule.trigger_end_time)}</span></td>
                  <td><span className="badge-warning"><TimerReset className="mr-1 h-3.5 w-3.5" />{formatIntervalRange(rule.interval_min_minutes, rule.interval_max_minutes)}</span></td>
                  <td className="whitespace-nowrap text-slate-500 dark:text-slate-400">{formatDateTime(rule.created_at)}</td>
                  <td>
                    <div className="flex min-w-max flex-wrap gap-x-3 gap-y-1">
                      <button type="button" className="btn-ios-link text-sm" onClick={() => setEditingRule(rule)}>修改</button>
                      <button type="button" className="btn-ios-link text-sm" onClick={() => setRecordsModal({ rule, type: 'publish' })}>发布记录</button>
                      <button type="button" className="btn-ios-link text-sm" onClick={() => setRecordsModal({ rule, type: 'trigger' })}>触发记录</button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <Pager
          page={page}
          pageSize={pageSize}
          total={total}
          totalPages={totalPages}
          loading={loading}
          onPageChange={(nextPage) => void loadRules(nextPage)}
          onPageSizeChange={(nextPageSize) => void loadRules(1, nextPageSize)}
        />
      </div>

      {showCreateModal && (
        <ScheduledPublishRuleModal
          onClose={() => setShowCreateModal(false)}
          onSaved={() => void loadRules(1)}
        />
      )}
      {editingRule && (
        <ScheduledPublishRuleModal
          rule={editingRule}
          onClose={() => setEditingRule(null)}
          onSaved={() => void loadRules(page)}
        />
      )}
      {recordsModal && (
        <ScheduledPublishRecordsModal
          rule={recordsModal.rule}
          type={recordsModal.type}
          onClose={() => setRecordsModal(null)}
        />
      )}
    </div>
  )
}
