/**
 * 个人设置中的卡密推送配置卡片。
 *
 * 功能：
 * 1. 填写卡密提交 URL 与卡密状态查询 URL
 * 2. 保存当前用户的卡密推送配置
 */
import { useEffect, useState } from 'react'
import { Send, Save } from 'lucide-react'
import { getCardPushSettings, saveCardPushSettings } from '@/api/cardPushSettings'
import { ButtonLoading, Loading } from '@/components/common/Loading'
import { useUIStore } from '@/store/uiStore'

export function CardPushRemoteConfig() {
  const { addToast } = useUIStore()
  const [submitUrl, setSubmitUrl] = useState('')
  const [statusQueryUrl, setStatusQueryUrl] = useState('')
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    let active = true

    void getCardPushSettings().then((result) => {
      if (!active) return
      if (!result.success || !result.data) {
        addToast({ type: 'error', message: result.message || '卡密推送配置加载失败' })
        return
      }
      setSubmitUrl(result.data.submitUrl)
      setStatusQueryUrl(result.data.statusQueryUrl)
    }).finally(() => {
      if (active) setLoading(false)
    })

    return () => {
      active = false
    }
  }, [addToast])

  /** 校验并保存两个卡密推送地址。 */
  const handleSave = async () => {
    const normalizedSubmitUrl = submitUrl.trim()
    const normalizedStatusQueryUrl = statusQueryUrl.trim()
    if (!normalizedSubmitUrl || !normalizedStatusQueryUrl) {
      addToast({ type: 'warning', message: '请填写卡密提交URL和卡密状态查询URL' })
      return
    }
    if (!/^https?:\/\//i.test(normalizedSubmitUrl) || !/^https?:\/\//i.test(normalizedStatusQueryUrl)) {
      addToast({ type: 'warning', message: 'URL必须以 http:// 或 https:// 开头' })
      return
    }

    setSaving(true)
    const result = await saveCardPushSettings({
      submitUrl: normalizedSubmitUrl,
      statusQueryUrl: normalizedStatusQueryUrl,
    })
    setSaving(false)

    if (!result.success) {
      addToast({ type: 'error', message: result.message || '卡密推送配置保存失败' })
      return
    }

    setSubmitUrl(normalizedSubmitUrl)
    setStatusQueryUrl(normalizedStatusQueryUrl)
    addToast({ type: 'success', message: result.message || '卡密推送配置已保存' })
  }

  return (
    <div className="vben-card relative overflow-hidden">
      <div className="vben-card-header">
        <h2 className="vben-card-title">
          <Send className="w-4 h-4" />
          卡密推送配置
        </h2>
      </div>
      <div className="vben-card-body space-y-4">
        <div className="input-group">
          <label className="input-label" htmlFor="card-push-submit-url">卡密提交URL</label>
          <input
            id="card-push-submit-url"
            type="url"
            value={submitUrl}
            onChange={(event) => setSubmitUrl(event.target.value)}
            placeholder="请输入卡密提交URL"
            className="input-ios"
            disabled={loading || saving}
          />
        </div>
        <div className="input-group">
          <label className="input-label" htmlFor="card-push-status-query-url">卡密状态查询URL</label>
          <input
            id="card-push-status-query-url"
            type="url"
            value={statusQueryUrl}
            onChange={(event) => setStatusQueryUrl(event.target.value)}
            placeholder="请输入卡密状态查询URL"
            className="input-ios"
            disabled={loading || saving}
          />
        </div>
        <button type="button" onClick={handleSave} disabled={loading || saving} className="btn-ios-primary">
          {saving ? <ButtonLoading /> : <Save className="w-4 h-4" />}
          保存
        </button>
      </div>
      {loading && (
        <div className="absolute inset-0 z-10 flex items-center justify-center bg-white/80 backdrop-blur-sm dark:bg-slate-800/80">
          <Loading size="md" text="加载中..." />
        </div>
      )}
    </div>
  )
}
