/**
 * 基础设置中的账号密码登录方式切换项。
 *
 * 功能：
 * 1. 展示协议登录、浏览器登录两种方式
 * 2. 选择协议登录时展示远程URL和秘钥输入框，需填写后保存
 * 3. 独立保存，避免提交页面其他未保存内容，并反馈实时生效结果
 */
import { useEffect, useState } from 'react'
import { Loader2 } from 'lucide-react'

import {
  normalizePasswordLoginMode,
  testRemotePasswordLoginInterface,
  updatePasswordLoginMode,
  updateRemotePasswordLoginSettings,
} from '@/api/passwordLoginSettings'
import { PasswordInput } from '@/components/common/PasswordInput'
import { useUIStore } from '@/store/uiStore'
import { getApiErrorMessage } from '@/utils/apiError'
import type { PasswordLoginMode } from '@/types'

interface PasswordLoginModeSettingProps {
  value: unknown
  remoteUrl?: unknown
  remoteSecretKey?: unknown
  onSaved: (mode: PasswordLoginMode, remoteUrl?: string, remoteSecretKey?: string) => void
}

const MODE_LABELS: Record<PasswordLoginMode, string> = {
  protocol: '协议登录',
  browser: '浏览器登录',
}

export function PasswordLoginModeSetting({
  value,
  remoteUrl,
  remoteSecretKey,
  onSaved,
}: PasswordLoginModeSettingProps) {
  const { addToast } = useUIStore()
  const [saving, setSaving] = useState(false)
  const [testing, setTesting] = useState(false)
  const [selectedMode, setSelectedMode] = useState<PasswordLoginMode>(
    normalizePasswordLoginMode(value),
  )
  const [remoteUrlValue, setRemoteUrlValue] = useState(
    typeof remoteUrl === 'string' ? remoteUrl : '',
  )
  const [remoteSecretKeyValue, setRemoteSecretKeyValue] = useState(
    typeof remoteSecretKey === 'string' ? remoteSecretKey : '',
  )
  const currentMode = normalizePasswordLoginMode(value)
  const remoteFieldsVisible = selectedMode === 'protocol'

  useEffect(() => {
    setSelectedMode(normalizePasswordLoginMode(value))
  }, [value])

  useEffect(() => {
    setRemoteUrlValue(typeof remoteUrl === 'string' ? remoteUrl : '')
  }, [remoteUrl])

  useEffect(() => {
    setRemoteSecretKeyValue(typeof remoteSecretKey === 'string' ? remoteSecretKey : '')
  }, [remoteSecretKey])

  const validateRemoteFields = (): boolean => {
    if (!remoteUrlValue.trim()) {
      addToast({ type: 'error', message: '选择协议登录时必须填写远程URL' })
      return false
    }
    if (!remoteSecretKeyValue.trim()) {
      addToast({ type: 'error', message: '选择协议登录时必须填写秘钥' })
      return false
    }
    return true
  }

  const handleSaveMode = async (mode: PasswordLoginMode) => {
    if (saving || testing || mode === currentMode) {
      return
    }

    try {
      setSaving(true)
      const result = await updatePasswordLoginMode(mode)
      if (!result.success) {
        addToast({ type: 'error', message: result.message || '账号密码登录方式切换失败' })
        return
      }

      onSaved(mode, remoteUrlValue, remoteSecretKeyValue)
      addToast({
        type: 'success',
        message: `已切换为${MODE_LABELS[mode]}，后续账号密码登录实时生效`,
      })
    } catch (error) {
      addToast({
        type: 'error',
        message: getApiErrorMessage(error, '账号密码登录方式切换失败'),
      })
    } finally {
      setSaving(false)
    }
  }

  const handleModeChange = (mode: PasswordLoginMode) => {
    setSelectedMode(mode)
    if (mode !== 'protocol') {
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
      const result = await updateRemotePasswordLoginSettings(
        'protocol',
        trimmedUrl,
        trimmedSecretKey,
      )
      if (!result.success) {
        addToast({ type: 'error', message: result.message || '协议登录远程接口设置保存失败' })
        return
      }

      onSaved('protocol', trimmedUrl, trimmedSecretKey)
      addToast({ type: 'success', message: '协议登录远程接口设置已保存，后续账号密码登录实时生效' })
    } catch (error) {
      addToast({
        type: 'error',
        message: getApiErrorMessage(error, '协议登录远程接口设置保存失败'),
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
      const result = await testRemotePasswordLoginInterface({
        remote_url: remoteUrlValue.trim(),
        remote_secret_key: remoteSecretKeyValue.trim(),
      })
      if (!result.success) {
        addToast({ type: 'error', message: result.message || '远程接口测试失败' })
        return
      }

      addToast({
        type: 'success',
        message: result.message || '远程接口连通性测试成功，请点击保存',
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
          <p className="font-medium text-slate-900 dark:text-slate-100">账号密码登录方式</p>
          <p className="text-sm text-slate-500 dark:text-slate-400">
            账号密码登录将严格按照所选方式执行，切换后立即生效
          </p>
        </div>
        <div className="relative shrink-0">
          <select
            aria-label="账号密码登录方式"
            value={selectedMode}
            disabled={saving || testing}
            onChange={(event) => handleModeChange(event.target.value as PasswordLoginMode)}
            className="input-ios w-full pr-9 disabled:cursor-not-allowed disabled:opacity-60 sm:w-44"
          >
            <option value="protocol">协议登录</option>
            <option value="browser">浏览器登录</option>
          </select>
          {saving && (
            <Loader2 className="pointer-events-none absolute right-8 top-1/2 h-4 w-4 -translate-y-1/2 animate-spin text-[rgb(var(--color-primary))]" />
          )}
        </div>
      </div>

      {remoteFieldsVisible && (
        <div className="mt-3 rounded-md border border-sky-200 bg-sky-50 px-3 py-2 text-sm text-sky-700 dark:border-sky-900/70 dark:bg-sky-950/30 dark:text-sky-300">
          <p>协议登录的滑块风控本项目自身已无法处理，将直接调用远程接口获取 x5sec 完成过滑块</p>
          <p className="mt-1">
            秘钥请到{' '}
            <a
              href="https://api.xianyusite.shop"
              target="_blank"
              rel="noreferrer"
              className="font-medium underline underline-offset-2 hover:opacity-80"
            >
              https://api.xianyusite.shop
            </a>{' '}
            获取，使用接口列表中的“阿里滑块获取x5sec”接口
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
                placeholder="https://api.xianyusite.shop/api/external/invoke"
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
                placeholder="填写秘钥，将通过 X-API-Key 请求头发送"
                showLabel="显示秘钥"
                hideLabel="隐藏秘钥"
              />
            </div>
          </div>
          <p className="mt-3 text-xs text-slate-500 dark:text-slate-400">
            请求头 X-API-Key=秘钥，请求体 type=x5sec_ali、data.url 为淘宝滑块页面完整链接，返回 data.x5sec 等校验值；测试仅验证连通性 data.url 传空字符串。
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
