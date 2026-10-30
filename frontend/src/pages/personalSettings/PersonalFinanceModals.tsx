/** 个人设置的结算、提现及收款码弹窗，沿用原有操作反馈。 */
import { RefreshCw, ArrowUpFromLine, Upload, X } from 'lucide-react'
import { ButtonLoading } from '@/components/common/Loading'
import type { usePersonalSettingsData } from './usePersonalSettingsData'
import type { usePersonalFinance } from './usePersonalFinance'

interface PersonalFinanceModalsProps {
  settings: ReturnType<typeof usePersonalSettingsData>
  finance: ReturnType<typeof usePersonalFinance>
}

export function PersonalFinanceModals({ settings, finance }: PersonalFinanceModalsProps) {
  const { balance, paymentQrcode, paymentType, setPaymentType } = settings
  const {
    showSettlementModal,
    setShowSettlementModal,
    settlementRecords,
    settlementLoading,
    settlementPage,
    settlementPageSize,
    setSettlementPageSize,
    settlementTotal,
    settlementTotalPages,
    withdrawing,
    showWithdrawModal,
    setShowWithdrawModal,
    withdrawAmount,
    setWithdrawAmount,
    withdrawMinAmount,
    showQrcodeModal,
    setShowQrcodeModal,
    uploadingQrcode,
    qrcodeFileRef,
    loadSettlementRecords,
    handleUploadQrcode,
    handleWithdraw
  } = finance
  return (
    <>
      {/* 结算记录弹窗 */}
      {showSettlementModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
          <div className="flex h-[80vh] w-full max-w-5xl flex-col rounded-2xl bg-white p-6 shadow-2xl dark:bg-slate-900">
            <div className="mb-4 flex items-center justify-between gap-3">
              <div>
                <h3 className="text-lg font-semibold text-slate-900 dark:text-slate-100">结算记录</h3>
                <p className="text-xs text-slate-500 dark:text-slate-400">按实际创建时间倒序显示，最新申请排在最前面</p>
              </div>
              <div className="flex items-center gap-2">
                <button onClick={() => loadSettlementRecords(settlementPage, settlementPageSize)} className="btn-ios-secondary text-sm" disabled={settlementLoading}>
                  <RefreshCw className={`w-4 h-4 ${settlementLoading ? 'animate-spin' : ''}`} />
                  刷新
                </button>
                <button
                  onClick={() => setShowSettlementModal(false)}
                  className="rounded-lg p-2 text-slate-500 transition hover:bg-slate-100 hover:text-slate-700 dark:hover:bg-slate-800 dark:hover:text-slate-200"
                >
                  <X className="h-5 w-5" />
                </button>
              </div>
            </div>

            <div className="flex-1 overflow-hidden rounded-xl border border-slate-200 dark:border-slate-700">
              <div className="table-scroll h-full">
                <table className="table-ios">
                  <thead>
                    <tr>
                      <th>记录ID</th>
                      <th>提现金额</th>
                      <th>收款方式</th>
                      <th>状态</th>
                      <th>拒绝原因</th>
                      <th>创建时间</th>
                    </tr>
                  </thead>
                  <tbody>
                    {settlementLoading ? (
                      <tr>
                        <td colSpan={6}>
                          <div className="py-10 text-center text-sm text-slate-500">加载中...</div>
                        </td>
                      </tr>
                    ) : settlementRecords.length === 0 ? (
                      <tr>
                        <td colSpan={6}>
                          <div className="py-10 text-center text-sm text-slate-500">暂无结算记录</div>
                        </td>
                      </tr>
                    ) : (
                      settlementRecords.map((record) => (
                        <tr key={record.id}>
                          <td>{record.id}</td>
                          <td>¥{record.amount}</td>
                          <td>{record.payment_type === 'wechat' ? '微信' : record.payment_type === 'alipay' ? '支付宝' : (record.alipay_id ? '支付宝' : '-')}</td>
                          <td>
                            <span className={`inline-block rounded px-2 py-0.5 text-xs font-medium ${
                              record.status === 'pending_review' ? 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400' :
                              record.status === 'approved' ? 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400' :
                              record.status === 'paid' ? 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400' :
                              'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400'
                            }`}>
                              {record.status === 'pending_review' ? '待审核' : record.status === 'approved' ? '已通过' : record.status === 'paid' ? '已打款' : '已拒绝'}
                            </span>
                          </td>
                          <td className="max-w-[200px] truncate text-red-600 dark:text-red-400" title={record.reject_reason || ''}>
                            {record.reject_reason || '-'}
                          </td>
                          <td className="whitespace-nowrap">{record.created_at ? new Date(record.created_at).toLocaleString('zh-CN') : '-'}</td>
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
              </div>
            </div>

            <div className="mt-4 flex flex-wrap items-center justify-between gap-3 border-t border-slate-200 pt-4 dark:border-slate-700">
              <div className="flex items-center gap-2 text-sm text-gray-500">
                <span>每页</span>
                <select
                  value={settlementPageSize}
                  onChange={async (e) => {
                    const nextSize = Number(e.target.value)
                    setSettlementPageSize(nextSize)
                    await loadSettlementRecords(1, nextSize)
                  }}
                  className="input-ios w-auto py-1 px-2 text-sm"
                >
                  <option value={10}>10</option>
                  <option value={20}>20</option>
                  <option value={50}>50</option>
                  <option value={100}>100</option>
                </select>
                <span>条，共 {settlementTotal} 条</span>
              </div>
              <div className="flex items-center gap-1">
                <button
                  onClick={() => loadSettlementRecords(settlementPage - 1, settlementPageSize)}
                  disabled={settlementPage <= 1 || settlementLoading}
                  className="btn-ios-secondary btn-sm"
                >
                  上一页
                </button>
                <span className="px-3 text-sm text-gray-600 dark:text-gray-400">
                  {settlementPage} / {settlementTotalPages || 1}
                </span>
                <button
                  onClick={() => loadSettlementRecords(settlementPage + 1, settlementPageSize)}
                  disabled={settlementPage >= settlementTotalPages || settlementLoading || settlementTotalPages === 0}
                  className="btn-ios-secondary btn-sm"
                >
                  下一页
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* 提现弹窗 */}
      {showWithdrawModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
          <div className="w-full max-w-lg rounded-2xl bg-white p-6 shadow-2xl dark:bg-slate-900">
            <div className="mb-4 flex items-center justify-between">
              <div>
                <h3 className="text-lg font-semibold text-slate-900 dark:text-slate-100">申请提现</h3>
                <p className="text-xs text-slate-500 dark:text-slate-400">提现后将立即扣减余额，并生成待审核结算记录</p>
              </div>
              <button
                onClick={() => {
                  if (withdrawing) return
                  setShowWithdrawModal(false)
                }}
                className="rounded-lg p-2 text-slate-500 transition hover:bg-slate-100 hover:text-slate-700 dark:hover:bg-slate-800 dark:hover:text-slate-200"
              >
                <X className="h-5 w-5" />
              </button>
            </div>
            <div className="space-y-4">
              <div className="rounded-lg bg-slate-50 p-3 text-sm text-slate-700 dark:bg-slate-800 dark:text-slate-200">
                <div>当前余额：¥{balance || '0.00'}</div>
                <div className="mt-1">
                  收款方式：{paymentQrcode ? (paymentType === 'wechat' ? '微信' : '支付宝') + '收款码' : '未上传收款码'}
                </div>
                {withdrawMinAmount && Number(withdrawMinAmount) > 0 && (
                  <div className="mt-1 text-amber-600 dark:text-amber-400">
                    最低提现金额：¥{withdrawMinAmount}
                  </div>
                )}
              </div>
              <div>
                <label className="input-label">提现金额（元）</label>
                <input
                  type="number"
                  min="0"
                  step="0.01"
                  value={withdrawAmount}
                  onChange={(e) => setWithdrawAmount(e.target.value)}
                  placeholder="请输入提现金额"
                  className="input-ios"
                  autoFocus
                />
              </div>
              <p className="text-xs text-slate-500 dark:text-slate-400">
                提现提交后会同步扣减余额、写入资金流水，并生成状态为“待审核”的结算记录。
              </p>
              <div className="flex justify-end gap-3">
                <button
                  onClick={() => setShowWithdrawModal(false)}
                  className="btn-ios-secondary"
                  disabled={withdrawing}
                >
                  取消
                </button>
                <button
                  onClick={handleWithdraw}
                  className="btn-ios-primary"
                  disabled={withdrawing}
                >
                  {withdrawing ? <ButtonLoading /> : <ArrowUpFromLine className="w-4 h-4" />}
                  确认提现
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* 收款码管理弹窗 */}
      {showQrcodeModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
          <div className="w-full max-w-lg rounded-2xl bg-white p-6 shadow-2xl dark:bg-slate-900">
            <div className="mb-4 flex items-center justify-between">
              <h3 className="text-lg font-semibold text-slate-900 dark:text-slate-100">收款码管理</h3>
              <button
                onClick={() => setShowQrcodeModal(false)}
                className="rounded-lg p-2 text-slate-500 transition hover:bg-slate-100 hover:text-slate-700 dark:hover:bg-slate-800 dark:hover:text-slate-200"
              >
                <X className="h-5 w-5" />
              </button>
            </div>
            <div className="space-y-4">
              {/* 收款类型选择 */}
              <div>
                <label className="input-label">收款方式</label>
                <div className="flex gap-3">
                  <button
                    onClick={() => setPaymentType('alipay')}
                    className={`flex-1 rounded-xl border-2 py-3 text-sm font-medium transition ${
                      paymentType === 'alipay'
                        ? 'border-blue-500 bg-blue-50 text-blue-700 dark:bg-blue-900/20 dark:text-blue-400'
                        : 'border-slate-200 text-slate-600 dark:border-slate-700 dark:text-slate-400'
                    }`}
                  >
                    支付宝
                  </button>
                  <button
                    onClick={() => setPaymentType('wechat')}
                    className={`flex-1 rounded-xl border-2 py-3 text-sm font-medium transition ${
                      paymentType === 'wechat'
                        ? 'border-green-500 bg-green-50 text-green-700 dark:bg-green-900/20 dark:text-green-400'
                        : 'border-slate-200 text-slate-600 dark:border-slate-700 dark:text-slate-400'
                    }`}
                  >
                    微信
                  </button>
                </div>
              </div>
              {/* 当前收款码预览 */}
              {paymentQrcode && (
                <div className="text-center">
                  <label className="input-label">当前收款码</label>
                  <img
                    src={paymentQrcode}
                    alt="当前收款码"
                    className="mx-auto mt-2 h-40 w-40 rounded-xl border border-slate-200 object-contain dark:border-slate-700"
                  />
                </div>
              )}
              {/* 上传区域 */}
              <div>
                <label className="input-label">{paymentQrcode ? '更换收款码' : '上传收款码'}</label>
                <div
                  onClick={() => qrcodeFileRef.current?.click()}
                  className="flex cursor-pointer flex-col items-center justify-center rounded-xl border-2 border-dashed border-slate-300 py-8 transition hover:border-blue-400 hover:bg-slate-50 dark:border-slate-600 dark:hover:bg-slate-800"
                >
                  {uploadingQrcode ? (
                    <ButtonLoading />
                  ) : (
                    <>
                      <Upload className="mb-2 h-8 w-8 text-slate-400" />
                      <span className="text-sm text-slate-500">点击选择图片（JPG/PNG/WEBP）</span>
                    </>
                  )}
                </div>
                <input
                  ref={qrcodeFileRef}
                  type="file"
                  accept="image/jpeg,image/png,image/webp"
                  className="hidden"
                  onChange={handleUploadQrcode}
                />
              </div>
              <div className="rounded-lg bg-slate-50 p-3 text-xs text-slate-500 dark:bg-slate-800 dark:text-slate-400">
                请上传{paymentType === 'wechat' ? '微信' : '支付宝'}收款码图片，管理员打款时将看到此收款码。已上传的收款码可重新上传替换。
              </div>
              <div className="flex justify-end">
                <button onClick={() => setShowQrcodeModal(false)} className="btn-ios-secondary">
                  关闭
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

    </>
  )
}
