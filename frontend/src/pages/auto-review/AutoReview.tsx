import { useEffect, useState } from 'react'
import { Button, Form, Input, InputNumber, Radio, Select, Spin, Switch } from '@arco-design/web-react'
import { RefreshCw, Save } from 'lucide-react'
import { getAccounts, getAutoReviewSettings, updateAutoReviewSettings, type AutoReviewSettings } from '@/api/accounts'
import { useUIStore } from '@/store/uiStore'
import { useAuthStore } from '@/store/authStore'
import { PageLoading } from '@/components/common/Loading'
import type { Account } from '@/types'

const { TextArea } = Input

const defaultSettings: AutoReviewSettings = {
  enabled: false,
  review_text: '',
  review_mode: 'fixed',
  review_word_count: 30,
  delay_seconds: 30,
  auto_send_flower: false,
  only_completed_orders: true,
}

export function AutoReview() {
  const { addToast } = useUIStore()
  const { isAuthenticated, token, _hasHydrated } = useAuthStore()
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [accounts, setAccounts] = useState<Account[]>([])
  const [selectedAccount, setSelectedAccount] = useState('')
  const [settings, setSettings] = useState<AutoReviewSettings>(defaultSettings)

  const loadAccounts = async () => {
    const data = await getAccounts()
    setAccounts(data)
    if (!selectedAccount && data.length > 0) {
      setSelectedAccount(data[0].id)
    }
  }

  const loadSettings = async (cookieId: string) => {
    const data = await getAutoReviewSettings(cookieId)
    setSettings({
      enabled: data.enabled ?? false,
      review_text: data.review_text ?? '',
      review_mode: data.review_mode ?? 'fixed',
      review_word_count: data.review_word_count ?? 30,
      delay_seconds: data.delay_seconds ?? 30,
      auto_send_flower: data.auto_send_flower ?? false,
      only_completed_orders: data.only_completed_orders ?? true,
    })
  }

  useEffect(() => {
    if (!_hasHydrated || !isAuthenticated || !token) return
    ;(async () => {
      try {
        setLoading(true)
        await loadAccounts()
      } catch {
        addToast({ type: 'error', message: '加载账号失败' })
      } finally {
        setLoading(false)
      }
    })()
  }, [_hasHydrated, isAuthenticated, token])

  useEffect(() => {
    if (!_hasHydrated || !isAuthenticated || !token || !selectedAccount) return
    ;(async () => {
      try {
        setLoading(true)
        await loadSettings(selectedAccount)
      } catch {
        addToast({ type: 'error', message: '加载自动评论配置失败' })
      } finally {
        setLoading(false)
      }
    })()
  }, [_hasHydrated, isAuthenticated, token, selectedAccount])

  const handleSave = async () => {
    if (!selectedAccount) {
      addToast({ type: 'warning', message: '请先选择账号' })
      return
    }
    setSaving(true)
    try {
      await updateAutoReviewSettings(selectedAccount, settings)
      addToast({ type: 'success', message: '自动评论配置已保存' })
    } catch {
      addToast({ type: 'error', message: '保存失败' })
    } finally {
      setSaving(false)
    }
  }

  if (loading && !selectedAccount) {
    return <PageLoading />
  }

  return (
    <div className="space-y-4">
      <div className="vben-card">
        <div className="accounts-page-intro">
          <h1>订单评价</h1>
          <p>按账号配置成交订单评价文案，并在收到评价提醒时自动执行</p>
        </div>

        <div className="table-toolbar">
          <div className="table-action-row">
            <div className="flex w-full justify-end gap-2">
              <Button 
                type="primary" 
                onClick={handleSave} loading={saving} className="accounts-header-btn">
                <Save />
                保存
              </Button>
              <Button onClick={() => selectedAccount && loadSettings(selectedAccount)} className="accounts-header-btn">
                <RefreshCw />
                刷新
              </Button>
            </div>
          </div>
        </div>

        {loading ? (
          <div className="flex items-center justify-center py-12">
            <Spin tip="加载中..." />
          </div>
        ) : (
          <Form layout="vertical">
            <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
              <div>
                <Form.Item label="选择账号">
                  <Select
                    value={selectedAccount}
                    onChange={setSelectedAccount}
                    placeholder="请选择账号"
                    options={accounts.map((account) => ({ label: account.id, value: account.id }))}
                  />
                </Form.Item>
                <Form.Item label="启用订单评价">
                  <Switch checked={settings.enabled} onChange={(checked) => setSettings((prev) => ({ ...prev, enabled: checked }))} />
                </Form.Item>
                <Form.Item label="延迟执行（秒）">
                  <InputNumber
                    min={0}
                    max={3600}
                    value={settings.delay_seconds}
                    onChange={(value) => setSettings((prev) => ({ ...prev, delay_seconds: Number(value || 0) }))}
                    style={{ width: '100%' }}
                  />
                </Form.Item>
                <Form.Item label="仅处理已完成订单">
                  <Switch
                    checked={settings.only_completed_orders}
                    onChange={(checked) => setSettings((prev) => ({ ...prev, only_completed_orders: checked }))}
                  />
                </Form.Item>
                <Form.Item label="自动送小红花">
                  <Switch
                    checked={settings.auto_send_flower}
                    onChange={(checked) => setSettings((prev) => ({ ...prev, auto_send_flower: checked }))}
                  />
                </Form.Item>
              </div>
              <div>
                <Form.Item label="评论方案">
                  <Radio.Group
                    type="button"
                    value={settings.review_mode}
                    onChange={(value) => setSettings((prev) => ({ ...prev, review_mode: value as 'fixed' | 'auto' }))}
                    options={[
                      { label: '固定文案', value: 'fixed' },
                      { label: '根据商品自动生成', value: 'auto' },
                    ]}
                  />
                </Form.Item>
                {settings.review_mode === 'fixed' ? (
                  <Form.Item label="固定评论文案">
                    <TextArea
                      value={settings.review_text}
                      onChange={(value) => setSettings((prev) => ({ ...prev, review_text: value }))}
                      autoSize={{ minRows: 10, maxRows: 16 }}
                      placeholder="例如：交易顺利，沟通愉快，欢迎下次再来。"
                    />
                  </Form.Item>
                ) : (
                  <>
                    <Form.Item label="自动生成字数（左右）">
                      <InputNumber
                        min={10}
                        max={120}
                        value={settings.review_word_count}
                        onChange={(value) => setSettings((prev) => ({ ...prev, review_word_count: Number(value || 30) }))}
                        style={{ width: '100%' }}
                      />
                    </Form.Item>
                    <div className="rounded-xl border border-slate-200 bg-slate-50 p-4 text-sm text-slate-500 dark:border-slate-700 dark:bg-slate-800/50 dark:text-slate-400">
                      系统会优先读取订单关联的商品标题、规格和交易信息，自动生成一段自然好评；该方式不额外调用 AI，不产生 Token 成本。
                    </div>
                  </>
                )}
              </div>
            </div>
          </Form>
        )}
      </div>
    </div>
  )
}
