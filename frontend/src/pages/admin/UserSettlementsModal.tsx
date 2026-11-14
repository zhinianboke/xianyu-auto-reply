/** 用户管理结算记录弹窗：按用户分页展示，支持修改每条数据的结算结果。 */
import { useState } from 'react'
import { ClipboardList, Loader2, RefreshCw } from 'lucide-react'
import { Pager } from '@/components/common/Pager'
import type { User } from '@/types'
import type { AdminSettlementRecord } from '@/api/adminSettlements'
import { SettlementResultModal } from './SettlementResultModal'
import { useAdminSettlements } from './useAdminSettlements'

/** 后端时间为北京时间，直接排版展示，不按浏览器时区转换。 */
const displayTime = (value?: string) => value ? value.replace('T', ' ').slice(0, 19) : '—'

/** 展示目标用户真实结算数据，加载/错误有明确反馈，表格在固定高度容器内滚动。 */
export function UserSettlementsModal({ user, onClose }: { user: User; onClose: () => void }) {
  const records = useAdminSettlements(user.user_id)
  const [editing, setEditing] = useState<AdminSettlementRecord | null>(null)
  const { data, loading, saving, error, load, save, clearError } = records
  const page = data?.page ?? 1
  const pageSize = data?.page_size ?? 20
  const total = data?.total ?? 0
  const totalPages = data?.total_pages ?? 0
  const busy = loading || saving || !!editing

  return (
    <div className="modal-overlay z-[200]">
      <div role="dialog" aria-modal="true" aria-labelledby="user-settlements-title" className="modal-content max-w-6xl h-[85vh] !overflow-hidden">
        <div className="modal-header gap-3">
          <h2 id="user-settlements-title" className="modal-title truncate">结算记录 · {user.username}</h2>
          <button type="button" className="btn-ios-secondary btn-sm shrink-0" disabled={saving || !!editing} onClick={onClose}>关闭</button>
        </div>
        <div className="flex min-h-0 flex-1 flex-col gap-3 p-3 sm:p-5">
          <div className="flex items-center justify-between gap-3">
            <p className="text-sm text-slate-500 dark:text-slate-400">用户ID：{user.user_id} · 共 {total} 条结算记录</p>
            <button type="button" className="btn-ios-secondary btn-sm" disabled={busy} onClick={() => load(page, pageSize)}>
              <RefreshCw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} />刷新
            </button>
          </div>
          {error && <p role="alert" className="rounded-md bg-red-50 p-3 text-sm text-red-700 dark:bg-red-900/20 dark:text-red-300">{error}</p>}
          <div className="relative flex min-h-0 flex-1 overflow-hidden rounded-lg border border-slate-200 dark:border-slate-700">
            <div className="table-scroll">
              <table className="table-ios">
                <thead><tr><th>记录ID</th><th>提现金额</th><th>收款方式</th><th>支付宝ID</th><th>结算结果</th><th>拒绝原因</th><th>备注</th><th>创建时间（北京时间）</th><th>更新时间（北京时间）</th><th>操作</th></tr></thead>
                <tbody>
                  {!loading && !error && !data?.list.length && <tr><td colSpan={10}>
                    <div className="flex flex-col items-center gap-2 py-10 text-slate-500 dark:text-slate-400"><ClipboardList className="h-10 w-10 text-slate-300 dark:text-slate-600" /><p>该用户暂无结算记录</p></div>
                  </td></tr>}
                  {data?.list.map(record => <tr key={record.id}>
                    <td>{record.id}</td><td className="font-medium tabular-nums whitespace-nowrap">¥{record.amount}</td>
                    <td className="whitespace-nowrap">{record.payment_type_label}</td><td>{record.alipay_id || '—'}</td>
                    <td className="whitespace-nowrap"><span className="badge-primary">{record.status_label}</span></td>
                    <td className="max-w-[180px] break-words text-red-600 dark:text-red-400">{record.reject_reason || '—'}</td>
                    <td className="min-w-[160px] max-w-[300px] whitespace-pre-wrap break-words">{record.remark || '—'}</td>
                    <td className="whitespace-nowrap">{displayTime(record.created_at)}</td><td className="whitespace-nowrap">{displayTime(record.updated_at)}</td>
                    <td><button type="button" className="btn-ios-secondary btn-sm whitespace-nowrap" disabled={busy} onClick={() => { clearError(); setEditing(record) }}>修改结果</button></td>
                  </tr>)}
                </tbody>
              </table>
            </div>
            {loading && <div role="status" className="absolute inset-0 flex items-center justify-center gap-2 bg-white/80 dark:bg-slate-800/85"><Loader2 className="h-6 w-6 animate-spin text-[rgb(var(--color-primary))]" /><span className="text-sm text-slate-700 dark:text-slate-200">正在读取结算记录…</span></div>}
          </div>
          <Pager page={page} pageSize={pageSize} total={total} totalPages={totalPages} loading={busy}
            onPageChange={next => load(next, pageSize)} onPageSizeChange={size => load(1, size)} />
        </div>
      </div>
      {editing && <SettlementResultModal key={`${editing.id}:${editing.revision}`} record={editing} options={data?.options.statuses ?? []} saving={saving} error={error}
        onClose={() => { if (!saving) { setEditing(null); clearError() } }}
        onSave={payload => { void save(editing.id, payload).then(saved => { if (saved) setEditing(null) }) }} />}
    </div>
  )
}
