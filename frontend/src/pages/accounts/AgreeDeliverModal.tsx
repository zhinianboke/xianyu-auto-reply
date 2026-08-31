/**
 * 同意后发货配置弹窗组件
 *
 * 功能：
 * 1. 配置账号的「同意后发货」开关、通知用户信息、提货URL
 * 2. 提示本系统内置提货页地址，支持一键填入 / 复制（公网地址由后端按环境变量推荐）
 */
import { useEffect, useState } from 'react'
import { X, Loader2, Truck, AlertTriangle, Copy, CornerDownLeft } from 'lucide-react'
import {
  getAgreeDeliverConfig,
  getPickupUrlSuggestion,
  updateAgreeDeliverConfig,
  type PickupUrlSuggestion,
} from '@/api/accounts'
import { getApiErrorMessage } from '@/utils/request'
import { useUIStore } from '@/store/uiStore'

interface Props {
  accountId: string
  accountDisplayId: string
  onClose: () => void
}

export function AgreeDeliverModal({ accountId, accountDisplayId, onClose }: Props) {
  const { addToast } = useUIStore()
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [enabled, setEnabled] = useState(false)
  const [notifyMessage, setNotifyMessage] = useState('')
  const [pickupUrl, setPickupUrl] = useState('')
  const [suggestion, setSuggestion] = useState<PickupUrlSuggestion | null>(null)

  useEffect(() => {
    loadConfig()
  }, [accountId])

  useEffect(() => {
    loadSuggestion()
  }, [])

  const loadConfig = async () => {
    setLoading(true)
    try {
      const res = await getAgreeDeliverConfig(accountId)
      if (res.success && res.data) {
        setEnabled(res.data.enabled)
        setNotifyMessage(res.data.notify_message || '')
        setPickupUrl(res.data.pickup_url || '')
      } else {
        addToast({ type: 'error', message: res.message || '加载配置失败' })
      }
    } catch (error) {
      addToast({ type: 'error', message: getApiErrorMessage(error, '加载配置失败') })
    } finally {
      setLoading(false)
    }
  }

  // 加载本系统提货页地址推荐（失败不阻塞配置，仅提示）
  const loadSuggestion = async () => {
    try {
      const res = await getPickupUrlSuggestion()
      if (res.success && res.data) {
        setSuggestion(res.data)
      } else {
        addToast({ type: 'error', message: res.message || '获取提货页地址失败' })
      }
    } catch (error) {
      addToast({ type: 'error', message: getApiErrorMessage(error, '获取提货页地址失败') })
    }
  }

  // 一键填入本系统提货页地址
  const handleUseSuggestion = () => {
    if (!suggestion?.pickup_url) return
    setPickupUrl(suggestion.pickup_url)
    addToast({ type: 'success', message: '已填入本系统提货页地址' })
  }

  // 复制本系统提货页地址
  const handleCopySuggestion = async () => {
    if (!suggestion?.pickup_url) return
    try {
      await navigator.clipboard.writeText(suggestion.pickup_url)
      addToast({ type: 'success', message: '提货页地址已复制' })
    } catch {
      addToast({ type: 'warning', message: '当前浏览器不支持自动复制，请手动选中复制' })
    }
  }

  const handleSave = async () => {
    // 开启同意后发货时提货URL必填
    if (enabled && !pickupUrl.trim()) {
      addToast({ type: 'warning', message: '开启同意后发货时，提货URL不能为空' })
      return
    }
    // 提货URL 若填写则校验格式
    if (pickupUrl.trim() && !/^https?:\/\//i.test(pickupUrl.trim())) {
      addToast({ type: 'warning', message: '提货URL必须以 http:// 或 https:// 开头' })
      return
    }

    setSaving(true)
    try {
      const res = await updateAgreeDeliverConfig(accountId, {
        enabled,
        notify_message: notifyMessage.trim() || null,
        pickup_url: pickupUrl.trim() || null,
      })
      if (res.success) {
        addToast({ type: 'success', message: '同意后发货配置已保存' })
        onClose()
      } else {
        addToast({ type: 'error', message: res.message || '保存失败' })
      }
    } catch (error) {
      addToast({ type: 'error', message: getApiErrorMessage(error, '保存失败') })
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="modal-overlay">
      <div className="modal-content max-w-md flex flex-col">
        <div className="modal-header">
          <h2 className="modal-title flex items-center gap-2">
            <Truck className="w-4 h-4 text-blue-500" />
            同意后发货设置
          </h2>
          <button onClick={onClose} className="modal-close">
            <X className="w-4 h-4" />
          </button>
        </div>

        <div className="modal-body space-y-4">
          {/* 账号信息 */}
          <div className="bg-blue-50 dark:bg-blue-900/20 rounded-lg p-3 text-sm text-blue-700 dark:text-blue-300">
            <p>账号: <span className="font-medium">{accountDisplayId}</span></p>
            <p className="text-xs mt-1 opacity-80">开启后不再直接发卡券，改为发送提货链接，买家点「同意」后才确认发货</p>
          </div>

          {loading ? (
            <div className="flex items-center justify-center py-10">
              <Loader2 className="w-6 h-6 animate-spin text-blue-500" />
              <span className="ml-2 text-sm text-slate-500">加载配置中...</span>
            </div>
          ) : (
            <>
              {/* 开关 */}
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm font-medium text-slate-700 dark:text-slate-200">开启同意后发货</p>
                  <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">买家同意后自动推送提货信息</p>
                </div>
                <button
                  type="button"
                  onClick={() => {
                    // URL 未填写时禁止开启
                    if (!enabled && !pickupUrl.trim()) {
                      addToast({ type: 'warning', message: '请先填写提货URL，再开启同意后发货' })
                      return
                    }
                    setEnabled(!enabled)
                  }}
                  className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors flex-shrink-0 ${enabled ? 'bg-blue-500' : 'bg-slate-300 dark:bg-slate-600'}`}
                  aria-pressed={enabled}
                >
                  <span className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${enabled ? 'translate-x-6' : 'translate-x-1'}`} />
                </button>
              </div>

              {/* 通知用户信息 */}
              <div>
                <label className="text-xs font-medium text-slate-600 dark:text-slate-300">通知用户信息</label>
                <textarea
                  value={notifyMessage}
                  onChange={(e) => setNotifyMessage(e.target.value)}
                  rows={4}
                  maxLength={2000}
                  placeholder="买家同意后发送给买家的提示内容"
                  className="input-ios mt-1 text-sm w-full resize-y"
                />
                <p className="text-[10px] text-slate-400 mt-0.5">最多 2000 字</p>
              </div>

              {/* 提货URL */}
              <div>
                <label className="text-xs font-medium text-slate-600 dark:text-slate-300">提货URL</label>
                <input
                  type="text"
                  value={pickupUrl}
                  onChange={(e) => setPickupUrl(e.target.value)}
                  placeholder={suggestion?.pickup_url || 'https://你的域名/agree-pickup'}
                  className="input-ios mt-1 text-sm w-full"
                />
                <p className="text-[10px] text-slate-400 mt-0.5">需以 http:// 或 https:// 开头</p>

                {/* 填写提示：本系统内置提货页地址 */}
                <div className="mt-2 rounded-lg bg-slate-50 dark:bg-slate-700/40 border border-slate-200 dark:border-slate-600 p-2.5 space-y-2">
                  <p className="text-[11px] font-medium text-slate-600 dark:text-slate-300">
                    该怎么填？
                  </p>
                  <p className="text-[11px] text-slate-500 dark:text-slate-400 leading-relaxed">
                    直接使用本系统自带的提货页即可（买家点「同意」后自动确认发货并展示卡券）。
                    也可填写你自己的提货页地址。
                  </p>
                  {suggestion?.pickup_url ? (
                    <>
                      <div className="flex items-center gap-1.5">
                        <code className="flex-1 min-w-0 truncate text-[11px] text-blue-600 dark:text-blue-300 bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-600 rounded px-2 py-1">
                          {suggestion.pickup_url}
                        </code>
                        <button
                          type="button"
                          onClick={handleUseSuggestion}
                          title="填入到提货URL"
                          className="flex-shrink-0 flex items-center gap-1 px-2 py-1 rounded text-[11px] bg-blue-500 hover:bg-blue-600 active:bg-blue-700 text-white transition-colors"
                        >
                          <CornerDownLeft className="w-3 h-3" />
                          填入
                        </button>
                        <button
                          type="button"
                          onClick={handleCopySuggestion}
                          title="复制地址"
                          className="flex-shrink-0 p-1.5 rounded text-slate-500 dark:text-slate-400 hover:bg-slate-200 dark:hover:bg-slate-600 transition-colors"
                        >
                          <Copy className="w-3 h-3" />
                        </button>
                      </div>
                      {suggestion.example_url && (
                        <p className="text-[10px] text-slate-400 dark:text-slate-500 break-all leading-relaxed">
                          买家收到的链接会自动追加订单参数：{suggestion.example_url}
                        </p>
                      )}
                    </>
                  ) : (
                    <p className="text-[11px] text-slate-400">正在获取本系统提货页地址...</p>
                  )}
                  {suggestion?.warning && (
                    <div className="flex items-start gap-1.5 rounded bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-800 px-2 py-1.5">
                      <AlertTriangle className="w-3.5 h-3.5 text-amber-500 flex-shrink-0 mt-0.5" />
                      <p className="text-[10px] text-amber-700 dark:text-amber-300 leading-relaxed">
                        {suggestion.warning}
                      </p>
                    </div>
                  )}
                </div>
              </div>
            </>
          )}
        </div>

        <div className="modal-footer">
          <button type="button" onClick={onClose} className="btn-ios-secondary" disabled={saving}>
            取消
          </button>
          <button onClick={handleSave} className="btn-ios-primary" disabled={saving || loading}>
            {saving ? (
              <span className="flex items-center gap-2">
                <Loader2 className="w-4 h-4 animate-spin" />
                保存中...
              </span>
            ) : '保存'}
          </button>
        </div>
      </div>
    </div>
  )
}
