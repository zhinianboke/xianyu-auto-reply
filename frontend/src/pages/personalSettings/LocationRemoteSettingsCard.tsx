/** 个人设置的原有位置聊天远程配置。 */
import { useEffect, useState } from 'react'
import { Link2, RefreshCw, Save } from 'lucide-react'
import { getUserSetting, updateUserSetting, testLocationChatRemoteApi } from '@/api/settings'
import { ButtonLoading } from '@/components/common/Loading'
import { PasswordInput } from '@/components/common/PasswordInput'
import { useUIStore } from '@/store/uiStore'

const LOCATION_CHAT_REMOTE_URL_KEY = 'location_chat.remote_url'
const LOCATION_CHAT_REMOTE_SECRET_KEY = 'location_chat.remote_secret_key'
const DEFAULT_LOCATION_CHAT_REMOTE_URL = 'https://api.xianyushop.shop/api/external/invoke'

export function LocationRemoteSettingsCard() {
  const { addToast } = useUIStore()
  const [locationRemoteUrl, setLocationRemoteUrl] = useState('')
  const [locationRemoteSecretKey, setLocationRemoteSecretKey] = useState('')
  const [testingLocationRemote, setTestingLocationRemote] = useState(false)
  const [savingLocationRemote, setSavingLocationRemote] = useState(false)

  useEffect(() => {
    void Promise.all([
      getUserSetting(LOCATION_CHAT_REMOTE_URL_KEY),
      getUserSetting(LOCATION_CHAT_REMOTE_SECRET_KEY),
    ]).then(([url, secret]) => {
      setLocationRemoteUrl(url.value || DEFAULT_LOCATION_CHAT_REMOTE_URL)
      setLocationRemoteSecretKey(secret.value || '')
    })
  }, [])

  const handleTestLocationRemote = async () => {
    const url = locationRemoteUrl.trim()
    const secretKey = locationRemoteSecretKey.trim()
    if (!url || !secretKey) {
      addToast({ type: 'warning', message: '请输入远程URL和秘钥' })
      return
    }
    try {
      setTestingLocationRemote(true)
      const result = await testLocationChatRemoteApi(url, secretKey)
      if (result.success || result.data?.status_code === 200) {
        addToast({ type: 'success', message: '测试成功' })
      } else {
        addToast({ type: 'error', message: result.message || '测试失败' })
      }
    } catch (error: unknown) {
      const err = error as { response?: { data?: { detail?: string; message?: string } }; message?: string }
      addToast({ type: 'error', message: err?.response?.data?.detail || err?.response?.data?.message || err?.message || '测试失败' })
    } finally {
      setTestingLocationRemote(false)
    }
  }

  const handleSaveLocationRemote = async () => {
    const url = locationRemoteUrl.trim()
    const secretKey = locationRemoteSecretKey.trim()
    if (!url || !secretKey) {
      addToast({ type: 'warning', message: '请输入远程URL和秘钥' })
      return
    }
    try {
      setSavingLocationRemote(true)
      const [urlResult, secretResult] = await Promise.all([
        updateUserSetting(LOCATION_CHAT_REMOTE_URL_KEY, url, '位置聊天远程URL'),
        updateUserSetting(LOCATION_CHAT_REMOTE_SECRET_KEY, secretKey, '位置聊天远程秘钥'),
      ])
      if (!urlResult.success || !secretResult.success) {
        addToast({ type: 'error', message: urlResult.message || secretResult.message || '保存失败' })
        return
      }
      setLocationRemoteUrl(url)
      setLocationRemoteSecretKey(secretKey)
      addToast({ type: 'success', message: '位置聊天远程配置已保存' })
    } catch (error: unknown) {
      const err = error as { response?: { data?: { detail?: string; message?: string } }; message?: string }
      addToast({ type: 'error', message: err?.response?.data?.detail || err?.response?.data?.message || err?.message || '保存失败' })
    } finally {
      setSavingLocationRemote(false)
    }
  }

  return (
        <div className="vben-card">
          <div className="vben-card-header">
            <h2 className="vben-card-title">
              <Link2 className="w-4 h-4" />
              位置聊天配置
            </h2>
          </div>
          <div className="vben-card-body space-y-5">
            <p className="text-sm text-slate-500 dark:text-slate-400">
              配置位置消息生成接口，用于测试远程服务是否能够正常生成位置聊天报文。
            </p>
            <div className="space-y-4">
              <div className="input-group">
                <label className="input-label">远程URL</label>
                <input type="url" value={locationRemoteUrl} onChange={(e) => setLocationRemoteUrl(e.target.value)} placeholder={DEFAULT_LOCATION_CHAT_REMOTE_URL} className="input-ios" />
              </div>
              <div className="input-group">
                <label className="input-label">秘钥</label>
                <PasswordInput value={locationRemoteSecretKey} onChange={setLocationRemoteSecretKey} placeholder="请输入远程接口秘钥" showLabel="显示秘钥" hideLabel="隐藏秘钥" />
                <p className="text-xs text-red-500 mt-2">
                  秘钥请到 <a className="underline" href="https://api.xianyushop.shop" target="_blank" rel="noopener noreferrer">https://api.xianyushop.shop</a> 网站的接口列表 “通过定位进行聊天” 接口获取
                </p>
              </div>
              <div className="flex flex-wrap gap-3">
                <button type="button" onClick={handleTestLocationRemote} disabled={testingLocationRemote || savingLocationRemote} className="btn-ios-secondary">
                  {testingLocationRemote ? <ButtonLoading /> : <RefreshCw className="w-4 h-4" />}
                  测试
                </button>
                <button type="button" onClick={handleSaveLocationRemote} disabled={savingLocationRemote || testingLocationRemote} className="btn-ios-primary">
                  {savingLocationRemote ? <ButtonLoading /> : <Save className="w-4 h-4" />}
                  保存
                </button>
              </div>
            </div>
          </div>
        </div>
  )
}
