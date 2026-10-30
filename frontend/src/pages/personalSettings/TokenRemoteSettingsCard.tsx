/** 个人设置的 Token 获取方式模块：仅管理远程配置和测试结果。 */
import { useCallback, useEffect, useRef, useState } from 'react'
import { Key, Loader2, RefreshCw, Save } from 'lucide-react'

import {
  getPersonalTokenSettings,
  savePersonalTokenSettings,
  testPersonalTokenSettings,
} from '@/api/personalTokenSettings'
import { PasswordInput } from '@/components/common/PasswordInput'
import { useUIStore } from '@/store/uiStore'
import { getApiErrorMessage } from '@/utils/apiError'

export function TokenRemoteSettingsCard() {
  const { addToast } = useUIStore()
  const [remoteUrl, setRemoteUrl] = useState('')
  const [secretKey, setSecretKey] = useState('')
  const [loading, setLoading] = useState(true)
  const [loaded, setLoaded] = useState(false)
  const [saving, setSaving] = useState(false)
  const [testing, setTesting] = useState(false)
  const operationPending = useRef(false)
  const loadSequence = useRef(0)
  const busy = loading || saving || testing

  /** 读取配置后再开放保存，防止读取失败时覆盖已有设置。 */
  const loadSettings = useCallback(() => {
    const sequence = ++loadSequence.current
    setLoading(true)
    setLoaded(false)
    return getPersonalTokenSettings().then((result) => {
      if (sequence !== loadSequence.current) return
      if (!result.success || !result.data) {
        addToast({ type: 'error', message: result.message || 'Token远程配置读取失败' })
        return
      }
      setRemoteUrl(result.data.remote_url)
      setSecretKey(result.data.remote_secret_key)
      setLoaded(true)
    }, (error: unknown) => {
      if (sequence !== loadSequence.current) return
      addToast({ type: 'error', message: getApiErrorMessage(error, 'Token远程配置读取失败') })
    }).finally(() => {
      if (sequence === loadSequence.current) setLoading(false)
    })
  }, [addToast])

  useEffect(() => {
    void loadSettings()
    return () => { loadSequence.current += 1 }
  }, [loadSettings])

  /** 验证必填字段；URL 格式及配置内容由后端再次校验。 */
  const validate = () => {
    if (!remoteUrl.trim() || !secretKey.trim()) {
      addToast({ type: 'warning', message: '请输入远程URL和秘钥' })
      return false
    }
    return true
  }

  const handleSave = () => {
    if (operationPending.current || busy || !loaded || !validate()) return
    operationPending.current = true
    setSaving(true)
    void savePersonalTokenSettings({
      remote_url: remoteUrl.trim(), remote_secret_key: secretKey.trim(),
    }).then((result) => {
      if (!result.success) {
        addToast({ type: 'error', message: result.message || 'Token远程配置保存失败' })
        return
      }
      setRemoteUrl(remoteUrl.trim())
      setSecretKey(secretKey.trim())
      addToast({ type: 'success', message: result.message || 'Token远程配置已保存' })
    }, (error: unknown) => {
      addToast({ type: 'error', message: getApiErrorMessage(error, 'Token远程配置保存失败') })
    }).finally(() => { operationPending.current = false; setSaving(false) })
  }

  const handleTest = () => {
    if (operationPending.current || busy || !loaded || !validate()) return
    operationPending.current = true
    setTesting(true)
    void testPersonalTokenSettings({
      remote_url: remoteUrl.trim(), remote_secret_key: secretKey.trim(),
    }).then((result) => {
      addToast({
        type: result.success ? 'success' : 'error',
        message: result.message || (result.success ? '远程接口测试成功' : '远程接口测试失败'),
      })
    }, (error: unknown) => {
      addToast({ type: 'error', message: getApiErrorMessage(error, '远程接口测试失败') })
    }).finally(() => { operationPending.current = false; setTesting(false) })
  }

  return (
    <div className="vben-card relative" aria-busy={busy}>
      <div className="vben-card-header">
        <h2 className="vben-card-title"><Key className="h-4 w-4" />Token获取方式</h2>
      </div>
      <div className="vben-card-body space-y-4">
        <p className="rounded-md border border-sky-200 bg-sky-50 px-3 py-2 text-sm text-sky-700 dark:border-sky-900/70 dark:bg-sky-950/30 dark:text-sky-300">
          秘钥请到{' '}
          <a href="https://api.xianyushop.shop" target="_blank" rel="noopener noreferrer" className="break-all font-medium underline underline-offset-2 hover:opacity-80">
            https://api.xianyushop.shop
          </a>{' '}获取，使用接口列表中的“闲鱼获取Token”接口
        </p>
        {!loading && !loaded && (
          <div className="flex flex-wrap items-center gap-3 text-sm text-red-600 dark:text-red-400">
            <span>配置读取失败，请重新加载后操作</span>
            <button type="button" onClick={() => void loadSettings()} className="btn-ios-secondary">重新加载</button>
          </div>
        )}
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          <div className="input-group">
            <label className="input-label" htmlFor="personal-token-remote-url">远程URL <span className="text-red-500">*</span></label>
            <input id="personal-token-remote-url" type="url" value={remoteUrl} onChange={(event) => setRemoteUrl(event.target.value)} disabled={busy || !loaded} required placeholder="https://api.xianyushop.shop/api/external/invoke" className="input-ios" />
          </div>
          <div className="input-group">
            <label className="input-label">秘钥 <span className="text-red-500">*</span></label>
            <PasswordInput value={secretKey} onChange={setSecretKey} disabled={busy || !loaded} required placeholder="请输入远程接口秘钥" showLabel="显示秘钥" hideLabel="隐藏秘钥" />
          </div>
        </div>
        <div className="flex flex-col gap-3 sm:flex-row sm:justify-end">
          <button type="button" onClick={handleTest} disabled={busy || !loaded} className="btn-ios-secondary">
            {testing ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}测试
          </button>
          <button type="button" onClick={handleSave} disabled={busy || !loaded} className="btn-ios-primary">
            {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}保存
          </button>
        </div>
      </div>
      {loading && (
        <div className="absolute inset-0 flex items-center justify-center gap-2 rounded-lg bg-white/80 text-sm text-slate-600 backdrop-blur-sm dark:bg-slate-900/80 dark:text-slate-300" role="status">
          <Loader2 className="h-5 w-5 animate-spin text-[rgb(var(--color-primary))]" />加载中...
        </div>
      )}
    </div>
  )
}
