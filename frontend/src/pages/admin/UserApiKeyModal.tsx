import { useState } from 'react'
import { Check, Copy, KeyRound, Loader2, RotateCw, Trash2, X } from 'lucide-react'

import { resetUserApiKey, revokeUserApiKey } from '@/api/admin'
import { useUIStore } from '@/store/uiStore'
import { getApiErrorMessage } from '@/utils/request'
import type { User } from '@/types'

interface Props {
  user: User
  onClose: () => void
  onUpdated: () => void
}

function formatTime(value?: string | null) {
  if (!value) return '—'
  return value.replace('T', ' ').slice(0, 19)
}

export function UserApiKeyModal({ user, onClose, onUpdated }: Props) {
  const { addToast } = useUIStore()
  const [loading, setLoading] = useState(false)
  const [plainKey, setPlainKey] = useState('')
  const [copied, setCopied] = useState(false)
  const [hasApiKey, setHasApiKey] = useState(Boolean(user.has_api_key))
  const [keyMask, setKeyMask] = useState(user.api_key_mask ?? '')
  const [createdAt, setCreatedAt] = useState(user.api_key_created_at ?? null)

  const handleReset = async () => {
    if (hasApiKey && !window.confirm('重置后旧 API Key 会立即失效，确定继续吗？')) {
      return
    }
    setLoading(true)
    try {
      const result = await resetUserApiKey(user.user_id)
      if (!result.success || !result.data?.api_key) {
        addToast({ type: 'error', message: result.message || 'API Key 生成失败' })
        return
      }
      setPlainKey(result.data.api_key)
      setHasApiKey(true)
      setKeyMask(result.data.api_key_mask)
      setCreatedAt(result.data.created_at)
      setCopied(false)
      addToast({ type: 'success', message: 'API Key 已生成，请立即复制保存' })
      onUpdated()
    } catch (error) {
      addToast({ type: 'error', message: getApiErrorMessage(error, 'API Key 生成失败') })
    } finally {
      setLoading(false)
    }
  }

  const handleCopy = async () => {
    if (!plainKey) return
    try {
      await navigator.clipboard.writeText(plainKey)
      setCopied(true)
      addToast({ type: 'success', message: 'API Key 已复制' })
    } catch {
      addToast({ type: 'error', message: '复制失败，请手动选择并复制' })
    }
  }

  const handleRevoke = async () => {
    if (!window.confirm('撤销后使用该 Key 的外部服务会立即无法访问，确定继续吗？')) {
      return
    }
    setLoading(true)
    try {
      const result = await revokeUserApiKey(user.user_id)
      if (!result.success) {
        addToast({ type: 'error', message: result.message || '撤销失败' })
        return
      }
      setPlainKey('')
      setHasApiKey(false)
      addToast({ type: 'success', message: 'API Key 已撤销' })
      onUpdated()
      onClose()
    } catch (error) {
      addToast({ type: 'error', message: getApiErrorMessage(error, '撤销失败') })
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="modal-overlay">
      <div className="modal-content max-w-lg">
        <div className="modal-header">
          <div>
            <h2 className="modal-title flex items-center gap-2">
              <KeyRound className="w-5 h-5" />
              用户 API Key
            </h2>
            <p className="text-sm text-slate-500 mt-1">用户：{user.username}</p>
          </div>
          <button className="modal-close" onClick={onClose} disabled={loading}>
            <X className="w-5 h-5" />
          </button>
        </div>
        <div className="modal-body space-y-4">
          <div className="rounded-lg bg-slate-50 dark:bg-slate-700/40 p-4 space-y-2 text-sm">
            <div className="flex justify-between gap-4">
              <span className="text-slate-500">当前状态</span>
              <span className={hasApiKey ? 'text-emerald-600' : 'text-slate-500'}>
                {hasApiKey ? '已启用' : '未生成'}
              </span>
            </div>
            <div className="flex justify-between gap-4">
              <span className="text-slate-500">掩码</span>
              <code>{keyMask || '—'}</code>
            </div>
            <div className="flex justify-between gap-4">
              <span className="text-slate-500">创建时间</span>
              <span>{formatTime(createdAt)}</span>
            </div>
            <div className="flex justify-between gap-4">
              <span className="text-slate-500">最后使用</span>
              <span>{formatTime(user.api_key_last_used_at)}</span>
            </div>
          </div>

          {plainKey && (
            <div className="rounded-lg border border-amber-300 bg-amber-50 dark:bg-amber-900/20 p-4">
              <p className="text-sm font-medium text-amber-800 dark:text-amber-200">
                该密钥只展示一次，请立即复制到目标服务的安全环境变量。
              </p>
              <div className="mt-3 flex gap-2">
                <input className="input-ios font-mono text-xs" value={plainKey} readOnly />
                <button className="btn-ios-secondary whitespace-nowrap" onClick={handleCopy}>
                  {copied ? <Check className="w-4 h-4" /> : <Copy className="w-4 h-4" />}
                  {copied ? '已复制' : '复制'}
                </button>
              </div>
            </div>
          )}

          <p className="text-sm text-slate-500">
            API Key 可访问该用户拥有权限的 REST API，不会自动过期；重置、撤销或停用用户会立即失效。
          </p>
        </div>
        <div className="modal-footer justify-between">
          <div>
            {hasApiKey && (
              <button className="btn-ios-danger" onClick={handleRevoke} disabled={loading}>
                <Trash2 className="w-4 h-4" />
                撤销
              </button>
            )}
          </div>
          <div className="flex gap-2">
            <button className="btn-ios-secondary" onClick={onClose} disabled={loading}>关闭</button>
            <button className="btn-ios-primary" onClick={handleReset} disabled={loading}>
              {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <RotateCw className="w-4 h-4" />}
              {hasApiKey ? '重置 Key' : '生成 Key'}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
