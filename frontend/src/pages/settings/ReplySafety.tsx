import { useEffect, useState } from 'react'
import { Save, Shield } from 'lucide-react'
import { Button, Input, InputNumber, Switch } from '@arco-design/web-react'
import { getSystemSettings, updateSystemSettings } from '@/api/settings'
import { useAuthStore } from '@/store/authStore'
import { useUIStore } from '@/store/uiStore'
import { PageLoading } from '@/components/common/Loading'
import type { SystemSettings } from '@/types'

export function ReplySafety() {
  const { addToast } = useUIStore()
  const { isAuthenticated, token, _hasHydrated } = useAuthStore()
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [settings, setSettings] = useState<SystemSettings | null>(null)

  const loadSettings = async () => {
    if (!_hasHydrated || !isAuthenticated || !token) return
    try {
      setLoading(true)
      const result = await getSystemSettings()
      setSettings(result.data || {})
    } catch {
      addToast({ type: 'error', message: '加载回复安全设置失败' })
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadSettings()
  }, [_hasHydrated, isAuthenticated, token])

  const saveSettings = async () => {
    if (!settings) return
    try {
      setSaving(true)
      const result = await updateSystemSettings({
        reply_safety_enabled: Boolean(settings.reply_safety_enabled ?? true),
        reply_max_per_minute: Number(settings.reply_max_per_minute ?? 20),
        reply_chat_cooldown_seconds: Number(settings.reply_chat_cooldown_seconds ?? 30),
        reply_message_dedupe_seconds: Number(settings.reply_message_dedupe_seconds ?? 10),
        reply_block_sensitive_words: Boolean(settings.reply_block_sensitive_words ?? true),
        reply_sensitive_words: String(settings.reply_sensitive_words || ''),
      })
      addToast({ type: result.success ? 'success' : 'error', message: result.message || (result.success ? '设置已保存' : '保存失败') })
    } catch {
      addToast({ type: 'error', message: '保存回复安全设置失败' })
    } finally {
      setSaving(false)
    }
  }

  if (loading && !settings) return <PageLoading />

  return (
    <div className="space-y-4">
      <div className="vben-card">
        <div className="accounts-page-intro">
          <h1>自动回复安全</h1>
          <p>限制自动回复频率，拦截高风险消息，避免误触发和高频异常。</p>
        </div>
        <div className="vben-card-body space-y-5">
          <div className="flex items-center justify-between rounded-lg border border-slate-200 p-4 dark:border-slate-700">
            <div className="flex items-center gap-3">
              <Shield className="w-5 h-5 text-slate-500" />
              <div>
                <div className="font-medium text-slate-900 dark:text-slate-100">启用安全阈值</div>
                <div className="text-sm text-slate-500">关闭后不会进行频率和敏感词拦截。</div>
              </div>
            </div>
            <Switch
              checked={Boolean(settings?.reply_safety_enabled ?? true)}
              onChange={(checked) => setSettings((value) => value ? { ...value, reply_safety_enabled: checked } : value)}
            />
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div className="input-group">
              <label className="input-label">单账号每分钟回复上限</label>
              <InputNumber
                min={0}
                value={Number(settings?.reply_max_per_minute ?? 20)}
                onChange={(value) => setSettings((current) => current ? { ...current, reply_max_per_minute: Number(value) || 0 } : current)}
                className="w-full"
              />
              <p className="text-xs text-slate-400 mt-1">设为 0 表示不限制每分钟回复数。</p>
            </div>
            <div className="input-group">
              <label className="input-label">同一买家冷却时间（秒）</label>
              <InputNumber
                min={0}
                value={Number(settings?.reply_chat_cooldown_seconds ?? 30)}
                onChange={(value) => setSettings((current) => current ? { ...current, reply_chat_cooldown_seconds: Number(value) || 0 } : current)}
                className="w-full"
              />
              <p className="text-xs text-slate-400 mt-1">设为 0 表示不限制同一会话回复间隔。</p>
            </div>
            <div className="input-group">
              <label className="input-label">消息去重过期时间（秒）</label>
              <InputNumber
                min={0}
                value={Number(settings?.reply_message_dedupe_seconds ?? 10)}
                onChange={(value) => setSettings((current) => current ? { ...current, reply_message_dedupe_seconds: Number(value) || 0 } : current)}
                className="w-full"
              />
              <p className="text-xs text-slate-400 mt-1">建议 3-10 秒。用于防止同一消息ID重复处理，设为 0 表示不去重。</p>
            </div>
          </div>

          <div className="space-y-3 rounded-lg border border-slate-200 p-4 dark:border-slate-700">
            <div className="flex items-center justify-between">
              <div>
                <div className="font-medium text-slate-900 dark:text-slate-100">敏感词拦截</div>
                <div className="text-sm text-slate-500">买家消息包含这些词时不自动回复。</div>
              </div>
              <Switch
                checked={Boolean(settings?.reply_block_sensitive_words ?? true)}
                onChange={(checked) => setSettings((value) => value ? { ...value, reply_block_sensitive_words: checked } : value)}
              />
            </div>
            <Input.TextArea
              value={String(settings?.reply_sensitive_words || '微信,加微信,QQ,手机号,电话,线下交易')}
              onChange={(value) => setSettings((current) => current ? { ...current, reply_sensitive_words: value } : current)}
              autoSize={{ minRows: 3, maxRows: 5 }}
              placeholder="用逗号分隔，例如：微信,QQ,手机号"
            />
          </div>

          <Button type="primary" onClick={saveSettings} loading={saving} className="accounts-header-btn">
            <Save />
            保存设置
          </Button>
        </div>
      </div>
    </div>
  )
}
