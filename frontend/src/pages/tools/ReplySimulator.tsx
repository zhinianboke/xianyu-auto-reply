import { useEffect, useState } from 'react'
import { Bot, Play } from 'lucide-react'
import { Button, Empty, Input, Select, Switch, Tag } from '@arco-design/web-react'
import { getAccounts } from '@/api/accounts'
import { simulateReply, type ReplySimulationResult } from '@/api/admin'
import { getItems } from '@/api/items'
import { useAuthStore } from '@/store/authStore'
import { useUIStore } from '@/store/uiStore'
import { PageLoading } from '@/components/common/Loading'
import type { Account, Item } from '@/types'

const replyTypeLabel: Record<string, string> = {
  keyword: '关键词回复',
  default: '默认回复',
  ai: 'AI 回复',
  blocked: '已拦截',
  none: '无回复',
}

export function ReplySimulator() {
  const { addToast } = useUIStore()
  const { isAuthenticated, token, _hasHydrated } = useAuthStore()
  const [loading, setLoading] = useState(true)
  const [running, setRunning] = useState(false)
  const [accounts, setAccounts] = useState<Account[]>([])
  const [items, setItems] = useState<Item[]>([])
  const [itemsLoading, setItemsLoading] = useState(false)
  const [cookieId, setCookieId] = useState('')
  const [message, setMessage] = useState('你好，在吗')
  const [itemId, setItemId] = useState('')
  const [includeAI, setIncludeAI] = useState(false)
  const [result, setResult] = useState<ReplySimulationResult | null>(null)
  const chatId = itemId ? `simulate_${itemId}` : undefined

  const loadAccounts = async () => {
    if (!_hasHydrated || !isAuthenticated || !token) return
    try {
      setLoading(true)
      const data = await getAccounts()
      setAccounts(data)
      if (!cookieId && data[0]?.id) setCookieId(data[0].id)
    } catch {
      addToast({ type: 'error', message: '加载账号失败' })
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadAccounts()
  }, [_hasHydrated, isAuthenticated, token])

  useEffect(() => {
    const loadItems = async () => {
      if (!cookieId) {
        setItems([])
        setItemId('')
        return
      }

      try {
        setItemsLoading(true)
        const response = await getItems(cookieId)
        setItems(response.data)
        if (itemId && !response.data.some((item) => item.item_id === itemId)) {
          setItemId('')
        }
      } catch {
        setItems([])
        setItemId('')
        addToast({ type: 'error', message: '加载商品列表失败' })
      } finally {
        setItemsLoading(false)
      }
    }

    loadItems()
  }, [cookieId])

  const runSimulation = async () => {
    if (!cookieId) {
      addToast({ type: 'warning', message: '请先选择账号' })
      return
    }
    if (!message.trim()) {
      addToast({ type: 'warning', message: '请输入买家消息' })
      return
    }
    if (!itemId) {
      addToast({ type: 'warning', message: '请先选择商品' })
      return
    }
    try {
      setRunning(true)
      setResult(await simulateReply({
        cookie_id: cookieId,
        message: message.trim(),
        chat_id: chatId,
        item_id: itemId,
        include_ai: includeAI,
      }))
    } catch {
      addToast({ type: 'error', message: '模拟回复失败' })
    } finally {
      setRunning(false)
    }
  }

  if (loading && accounts.length === 0) return <PageLoading />

  return (
    <div className="space-y-4">
      <div className="vben-card">
        <div className="accounts-page-intro">
          <h1>回复模拟</h1>
          <p>输入一条买家消息，查看安全阈值、关键词、默认回复和 AI 的命中链路。</p>
        </div>
        <div className="vben-card-body grid grid-cols-1 lg:grid-cols-[520px_minmax(0,1fr)] gap-5">
          <div className="space-y-4 max-w-[520px]">
            <div className="input-group">
              <label className="input-label">测试账号</label>
              <Select
                value={cookieId}
                onChange={(value) => setCookieId(String(value))}
                options={accounts.map((account) => ({ value: account.id, label: account.id }))}
                placeholder="选择账号"
              />
            </div>
            <div className="input-group">
              <label className="input-label">买家消息</label>
              <Input.TextArea value={message} onChange={setMessage} autoSize={{ minRows: 4, maxRows: 8 }} />
            </div>
            <div className="input-group">
              <label className="input-label">选择商品</label>
              <Select
                value={itemId || undefined}
                onChange={(value) => setItemId(String(value || ''))}
                loading={itemsLoading}
                allowClear
                showSearch
                placeholder="请选择商品"
                style={{ width: '100%' }}
                dropdownMenuStyle={{ maxWidth: 520 }}
                filterOption={(inputValue, option) => {
                  const label = String(option.props?.children || option.props?.label || '')
                  return label.toLowerCase().includes(inputValue.toLowerCase())
                }}
              >
                {items.map((item) => {
                  const title = item.item_title || item.title || '未命名商品'
                  const price = item.item_price || item.price
                  return (
                    <Select.Option key={`${item.cookie_id}-${item.item_id}`} value={item.item_id}>
                      <span className="block max-w-[460px] truncate">
                        {`${title} - ${item.item_id}${price ? ` - ¥${price}` : ''}`}
                      </span>
                    </Select.Option>
                  )
                })}
              </Select>
              <p className="text-xs text-slate-500 dark:text-slate-400 mt-1">
                会话ID将按所选商品自动生成：{chatId || '请选择商品'}
              </p>
            </div>
            <div className="flex items-center justify-between rounded-lg border border-slate-200 p-3 dark:border-slate-700">
              <div>
                <div className="font-medium">生成 AI 回复预览</div>
                <div className="text-xs text-slate-500">完整链路走到 AI 分支时，真实调用模型生成预览。</div>
              </div>
              <Switch checked={includeAI} onChange={setIncludeAI} />
            </div>
            <Button type="primary" onClick={runSimulation} loading={running} className="accounts-header-btn">
              <Play />
              开始模拟
            </Button>
          </div>

          <div className="rounded-lg border border-slate-200 p-4 dark:border-slate-700 min-h-[360px]">
            {!result ? (
              <div className="flex min-h-[320px] items-center justify-center">
                <Empty icon={<Bot className="w-12 h-12 text-slate-300" />} description="暂无模拟结果" />
              </div>
            ) : (
              <div className="space-y-4">
                <div className="flex items-center justify-between">
                  <h2 className="settings-section-title">模拟结果</h2>
                  <Tag color={result.blocked ? 'red' : result.reply_type === 'none' ? 'gray' : 'green'}>
                    {replyTypeLabel[result.reply_type] || result.reply_type}
                  </Tag>
                </div>
                <div className="rounded-lg bg-slate-50 p-4 text-sm dark:bg-slate-800/50">
                  {result.reply || '不会自动回复'}
                </div>
                <div className="space-y-2">
                  {result.steps.map((step) => (
                    <div key={step.name} className="flex items-start justify-between gap-3 rounded-lg border border-slate-200 px-3 py-2 text-sm dark:border-slate-700">
                      <div>
                        <div className="font-medium">{step.name}</div>
                        <div className="text-slate-500">{step.detail}</div>
                      </div>
                      <Tag color={step.matched ? 'green' : 'gray'}>{step.matched ? '通过' : '未命中'}</Tag>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
