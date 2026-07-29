/**
 * 基础设置中的 Token 获取方式切换项。
 *
 * 功能：
 * 1. 展示网页接口、远程接口两种 Token 获取方式
 * 2. 选择远程接口时展示远程URL和秘钥输入框
 * 3. 支持远程接口测试与独立保存，避免提交页面其他未保存内容
 */
import { useEffect, useState } from 'react'
import { Loader2 } from 'lucide-react'

import {
  normalizeTokenApiMode,
  testRemoteTokenInterface,
  updateRemoteTokenSettings,
  updateTokenApiMode,
} from '@/api/tokenApiModeSettings'
import { PasswordInput } from '@/components/common/PasswordInput'
import { useUIStore } from '@/store/uiStore'
import { getApiErrorMessage } from '@/utils/apiError'
import type { TokenApiMode } from '@/types'

interface TokenApiModeSettingProps {
  value: unknown
  remoteUrl?: unknown
  remoteSecretKey?: unknown
  onSaved: (mode: TokenApiMode, remoteUrl?: string, remoteSecretKey?: string) => void
}
const MODE_LABELS: Record<TokenApiMode, string> = {
  web: '网页接口',
  remote: '远程接口',
}

export function TokenApiModeSetting({
  value,
  remoteUrl,
  remoteSecretKey,
  onSaved,
}: TokenApiModeSettingProps) {
  const { addToast } = useUIStore()
  const [saving, setSaving] = useState(false)
  const [testing, setTesting] = useState(false)
  const [selectedMode, setSelectedMode] = useState<TokenApiMode>(normalizeTokenApiMode(value))
  const [remoteUrlValue, setRemoteUrlValue] = useState(typeof remoteUrl === 'string' ? remoteUrl : '')
  const [remoteSecretKeyValue, setRemoteSecretKeyValue] = useState(
    typeof remoteSecretKey === 'string' ? remoteSecretKey : '',
  )
  const currentMode = normalizeTokenApiMode(value)
  const remoteFieldsVisible = selectedMode === 'remote'

  useEffect(() => {
    setSelectedMode(normalizeTokenApiMode(value))
  }, [value])

  useEffect(() => {
    setRemoteUrlValue(typeof remoteUrl === 'string' ? remoteUrl : '')
  }, [remoteUrl])

  useEffect(() => {
    setRemoteSecretKeyValue(typeof remoteSecretKey === 'string' ? remoteSecretKey : '')
  }, [remoteSecretKey])

  const validateRemoteFields = (): boolean => {
    if (!remoteUrlValue.trim()) {
      addToast({ type: 'error', message: '请选择远程接口时必须填写远程URL' })
      return false
    }
    if (!remoteSecretKeyValue.trim()) {
      addToast({ type: 'error', message: '请选择远程接口时必须填写秘钥' })
      return false
    }
    return true
  }

  const handleSaveMode = async (mode: TokenApiMode) => {
    if (saving || testing || mode === currentMode) {
      return
    }

    try {
      setSaving(true)
      const result = await updateTokenApiMode(mode)
      if (!result.success) {
        addToast({ type: 'error', message: result.message || 'Token获取方式切换失败' })
        return
      }

      onSaved(mode, remoteUrlValue, remoteSecretKeyValue)
      addToast({
        type: 'success',
        message: `已切换为${MODE_LABELS[mode]}，后续取Token实时生效`,
      })
    } catch (error) {
      addToast({
        type: 'error',
        message: getApiErrorMessage(error, 'Token获取方式切换失败'),
      })
    } finally {
      setSaving(false)
    }
  }

  const handleModeChange = (mode: TokenApiMode) => {
    setSelectedMode(mode)
    if (mode !== 'remote') {
      void handleSaveMode(mode)
    }
  }

  const handleSaveRemote = async () => {
    if (saving || testing || !validateRemoteFields()) {
      return
    }

    try {
      setSaving(true)
      const trimmedUrl = remoteUrlValue.trim()
      const trimmedSecretKey = remoteSecretKeyValue.trim()
      const result = await updateRemoteTokenSettings('remote', trimmedUrl, trimmedSecretKey)
      if (!result.success) {
        addToast({ type: 'error', message: result.message || 'Token远程接口设置保存失败' })
        return
      }

      onSaved('remote', trimmedUrl, trimmedSecretKey)
      addToast({ type: 'success', message: 'Token远程接口设置已保存，后续取Token实时生效' })
    } catch (error) {
      addToast({
        type: 'error',
        message: getApiErrorMessage(error, 'Token远程接口设置保存失败'),
      })
    } finally {
      setSaving(false)
    }
  }

  const handleTestRemote = async () => {
    if (saving || testing || !validateRemoteFields()) {
      return
    }

    try {
      setTesting(true)
      const result = await testRemoteTokenInterface({
        remote_url: remoteUrlValue.trim(),
        remote_secret_key: remoteSecretKeyValue.trim(),
      })
      if (!result.success) {
        addToast({ type: 'error', message: result.message || '远程接口测试失败' })
        return
      }

      addToast({
        type: 'success',
        message: `远程接口测试成功，实际接口：${result.data?.api_mode || '未返回'}`,
      })
    } catch (error) {
      addToast({
        type: 'error',
        message: getApiErrorMessage(error, '远程接口测试失败'),
      })
    } finally {
      setTesting(false)
    }
  }

  return (
    <div className="border-t border-slate-100 py-3 dark:border-slate-700">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="min-w-0">
          <p className="font-medium text-slate-900 dark:text-slate-100">Token获取方式</p>
          <p className="text-sm text-slate-500 dark:text-slate-400">
            可选择网页接口或远程接口
          </p>
        </div>
        <div className="relative shrink-0">
          <select
            aria-label="Token获取方式"
            value={selectedMode}
            disabled={saving || testing}
            onChange={(event) => handleModeChange(event.target.value as TokenApiMode)}
            className="input-ios w-full pr-9 disabled:cursor-not-allowed disabled:opacity-60 sm:w-44"
          >
            <option value="web">网页接口</option>
            <option value="remote">远程接口</option>
          </select>
          {saving && (
            <Loader2 className="pointer-events-none absolute right-8 top-1/2 h-4 w-4 -translate-y-1/2 animate-spin text-[rgb(var(--color-primary))]" />
          )}
        </div>
      </div>

      {selectedMode === 'remote' && (
        <div className="mt-3 rounded-md border border-sky-200 bg-sky-50 px-3 py-2 text-sm text-sky-700 dark:border-sky-900/70 dark:bg-sky-950/30 dark:text-sky-300">
          <p>优先使用本地网页端接口，本地网页端接口获取失败才会调用远程接口获取</p>
          <p className="mt-1">
            秘钥请到{' '}
            <a
              href="https://api.zhinianblog.cn"
              target="_blank"
              rel="noreferrer"
              className="font-medium underline underline-offset-2 hover:opacity-80"
            >
              https://api.zhinianblog.cn
            </a>{' '}
            获取
          </p>
        </div>
      )}

      {remoteFieldsVisible && (
        <div className="mt-4 rounded-lg border border-slate-200 bg-slate-50/80 p-4 dark:border-slate-700 dark:bg-slate-800/50">
          <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
            <div className="input-group">
              <label className="input-label">
                远程URL <span className="text-red-500">*</span>
              </label>
              <input
                type="url"
                value={remoteUrlValue}
                disabled={saving || testing}
                required
                onChange={(event) => setRemoteUrlValue(event.target.value)}
                placeholder="https://example.com/api/token"
                className="input-ios"
              />
            </div>
            <div className="input-group">
              <label className="input-label">
                秘钥 <span className="text-red-500">*</span>
              </label>
              <PasswordInput
                value={remoteSecretKeyValue}
                disabled={saving || testing}
                required
                onChange={setRemoteSecretKeyValue}
                placeholder="填写32位秘钥，将通过 X-API-Key 请求头发送"
                showLabel="显示秘钥"
                hideLabel="隐藏秘钥"
              />
            </div>
          </div>
          <p className="mt-3 text-xs text-slate-500 dark:text-slate-400">
            请求头 X-API-Key=秘钥，请求体 type=xianyu_token、data.cookies 为闲鱼 Cookie；实际取Token时发送对应账号的完整 Cookie，测试仅验证连通性 data.cookies 传空字符串。
          </p>
          <div className="mt-4 flex flex-col gap-2 sm:flex-row sm:justify-end">
            <button
              type="button"
              disabled={saving || testing}
              onClick={() => void handleTestRemote()}
              className="btn-ios-secondary"
            >
              {testing && <Loader2 className="h-4 w-4 animate-spin" />}
              测试远程接口
            </button>
            <button
              type="button"
              disabled={saving || testing}
              onClick={() => void handleSaveRemote()}
              className="btn-ios-primary"
            >
              {saving && <Loader2 className="h-4 w-4 animate-spin" />}
              保存远程接口
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
