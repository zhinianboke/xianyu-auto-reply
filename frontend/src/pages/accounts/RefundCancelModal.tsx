/**
 * 退款订单注销配置弹窗组件
 *
 * 功能：
 * 1. 配置账号的「退款订单注销」开关、请求URL、超时时间
 * 2. 收到买家退款消息时，websocket 服务按此配置调用外部注销接口
 */
import { useEffect, useState } from 'react'
import { X, Loader2, RotateCcw } from 'lucide-react'
import { getRefundCancelConfig, updateRefundCancelConfig } from '@/api/accounts'
import { getApiErrorMessage } from '@/utils/request'
import { useUIStore } from '@/store/uiStore'

interface Props {
  accountId: string
  accountDisplayId: string
  onClose: () => void
}

export function RefundCancelModal({ accountId, accountDisplayId, onClose }: Props) {
  const { addToast } = useUIStore()
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [enabled, setEnabled] = useState(false)
  const [url, setUrl] = useState('')
  const [timeout, setTimeoutValue] = useState(60)

  useEffect(() => {
    loadConfig()
  }, [accountId])

  const loadConfig = async () => {
    setLoading(true)
    try {
      const res = await getRefundCancelConfig(accountId)
      if (res.success && res.data) {
        setEnabled(res.data.enabled)
        setUrl(res.data.url || '')
        setTimeoutValue(res.data.timeout || 60)
      } else {
        addToast({ type: 'error', message: res.message || '加载配置失败' })
      }
    } catch (error) {
      addToast({ type: 'error', message: getApiErrorMessage(error, '加载配置失败') })
    } finally {
      setLoading(false)
    }
  }

  const handleSave = async () => {
    if (enabled) {
      if (!url.trim()) {
        addToast({ type: 'warning', message: '开启退款订单注销时，请求URL不能为空' })
        return
      }
      if (!/^https?:\/\//i.test(url.trim())) {
        addToast({ type: 'warning', message: '请求URL必须以 http:// 或 https:// 开头' })
        return
      }
    }
    if (!Number.isFinite(timeout) || timeout < 1) {
      addToast({ type: 'warning', message: '超时时间请输入大于 0 的秒数' })
      return
    }

    setSaving(true)
    try {
      const res = await updateRefundCancelConfig(accountId, {
        enabled,
        url: enabled ? url.trim() : null,
        timeout,
      })
      if (res.success) {
        addToast({ type: 'success', message: '退款订单注销配置已保存' })
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
            <RotateCcw className="w-4 h-4 text-orange-500" />
            退款订单注销设置
          </h2>
          <button onClick={onClose} className="modal-close">
            <X className="w-4 h-4" />
          </button>
        </div>

        <div className="modal-body space-y-4">
          {/* 账号信息 */}
          <div className="bg-blue-50 dark:bg-blue-900/20 rounded-lg p-3 text-sm text-blue-700 dark:text-blue-300">
            <p>账号: <span className="font-medium">{accountDisplayId}</span></p>
            <p className="text-xs mt-1 opacity-80">买家发起退款时，将发货内容和链接推送到此接口</p>
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
                  <p className="text-sm font-medium text-slate-700 dark:text-slate-200">开启退款订单注销</p>
                  <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">收到买家退款申请时调用注销接口</p>
                </div>
                <button
                  type="button"
                  onClick={() => {
                    // URL 未填写时禁止开启
                    if (!enabled && !url.trim()) {
                      addToast({ type: 'warning', message: '请先填写请求URL，再开启退款订单注销' })
                      return
                    }
                    setEnabled(!enabled)
                  }}
                  className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors flex-shrink-0 ${enabled ? 'bg-orange-500' : 'bg-slate-300 dark:bg-slate-600'}`}
                  aria-pressed={enabled}
                >
                  <span className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${enabled ? 'translate-x-6' : 'translate-x-1'}`} />
                </button>
              </div>

              {/* 请求URL（始终可见，需先填写才能开启开关） */}
              <div>
                <label className="text-xs font-medium text-slate-600 dark:text-slate-300">请求URL</label>
                <input
                  type="text"
                  value={url}
                  onChange={(e) => {
                    const v = e.target.value
                    setUrl(v)
                    // URL 清空时自动关闭开关，保证「无URL时开关必关」
                    if (!v.trim() && enabled) setEnabled(false)
                  }}
                  placeholder="https://example.com/cancel"
                  className="input-ios mt-1 text-sm w-full"
                />
                <p className="text-[10px] text-slate-400 mt-0.5">
                  POST 表单，参数 delivery_content（发货内容）、link_url（发货链接），每个发货内容调一次
                </p>
              </div>

              {/* 超时时间 */}
              <div>
                <label className="text-xs font-medium text-slate-600 dark:text-slate-300">超时时间(秒)</label>
                <input
                  type="number"
                  min={1}
                  value={timeout}
                  onChange={(e) => setTimeoutValue(Math.max(1, parseInt(e.target.value) || 60))}
                  className="input-ios mt-1 text-sm w-24"
                />
                <p className="text-[10px] text-slate-400 mt-0.5">默认 60 秒，不限上限，填写大于 0 的整数即可</p>
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
