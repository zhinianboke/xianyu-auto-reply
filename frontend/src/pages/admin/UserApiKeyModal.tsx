import { useEffect, useState } from 'react'
import { Check, Copy, KeyRound, Loader2, RotateCw, Trash2, X } from 'lucide-react'

import { getUserApiKey, resetUserApiKey, revokeUserApiKey } from '@/api/admin'
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
  const [keyLoading, setKeyLoading] = useState(Boolean(user.has_api_key))
  const [plainKey, setPlainKey] = useState('')
  const [requiresReset, setRequiresReset] = useState(
    Boolean(user.has_api_key && !user.api_key_recoverable),
  )
  const [copied, setCopied] = useState(false)
  const [hasApiKey, setHasApiKey] = useState(Boolean(user.has_api_key))
  const [keyMask, setKeyMask] = useState(user.api_key_mask ?? '')
  const [createdAt, setCreatedAt] = useState(user.api_key_created_at ?? null)

  useEffect(() => {
    let active = true
    if (!user.has_api_key) {
      setKeyLoading(false)
      return () => {
        active = false
      }
    }

    setKeyLoading(true)
    getUserApiKey(user.user_id)
      .then((result) => {
        if (!active || !result.success || !result.data) return
        setPlainKey(result.data.api_key ?? '')
        setKeyMask(result.data.api_key_mask ?? user.api_key_mask ?? '')
        setRequiresReset(result.data.requires_reset)
      })
      .catch((error) => {
        if (!active) return
        addToast({ type: 'error', message: getApiErrorMessage(error, 'API Key 加载失败') })
      })
      .finally(() => {
        if (active) setKeyLoading(false)
      })

    return () => {
      active = false
    }
  }, [addToast, user.api_key_mask, user.has_api_key, user.user_id])

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
      setRequiresReset(false)
      setHasApiKey(true)
      setKeyMask(result.data.api_key_mask)
      setCreatedAt(result.data.created_at)
      setCopied(false)
      addToast({ type: 'success', message: 'API Key 已生成并展示完整明文' })
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
      setRequiresReset(false)
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
            <div className="flex items-start justify-between gap-4">
              <span className="text-slate-500 shrink-0">API Key</span>
              <div className="flex min-w-0 items-start gap-2">
                {keyLoading ? (
                  <Loader2 className="mt-0.5 h-4 w-4 animate-spin text-slate-400" />
                ) : (
                  <code className="break-all text-right">{plainKey || keyMask || '—'}</code>
                )}
                {plainKey && (
                  <button
                    className="shrink-0 text-blue-600 hover:text-blue-500"
                    onClick={handleCopy}
                    title="复制完整 API Key"
                  >
                    {copied ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
                  </button>
                )}
              </div>
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

          {requiresReset && (
            <div className="rounded-lg border border-amber-300 bg-amber-50 dark:bg-amber-900/20 p-4">
              <p className="text-sm font-medium text-amber-800 dark:text-amber-200">
                这是升级前生成的旧 Key，系统只保存了哈希，无法恢复明文。请重置一次，之后可随时在这里查看完整 Key。
              </p>
            </div>
          )}

          <p className="text-sm text-slate-500">
            完整 API Key 仅管理员可查看；重置、撤销或停用用户后会立即失效。
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
