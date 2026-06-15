import { useState, useEffect } from 'react'
import type { FormEvent } from 'react'
import { Button, Empty, Input, Modal, Popconfirm, Select, Space, Switch, Table } from '@arco-design/web-react'
import type { TableColumnProps } from '@arco-design/web-react'
import { Truck, RefreshCw, Plus, Loader2 } from 'lucide-react'
import { getDeliveryRules, deleteDeliveryRule, updateDeliveryRule, addDeliveryRule } from '@/api/delivery'
import { getCards, type CardData } from '@/api/cards'
import { getItems } from '@/api/items'
import { useUIStore } from '@/store/uiStore'
import { useAuthStore } from '@/store/authStore'
import { PageLoading } from '@/components/common/Loading'
import type { DeliveryRule, Item } from '@/types'

export function Delivery() {
  const { addToast } = useUIStore()
  const { isAuthenticated, token, _hasHydrated } = useAuthStore()
  const [loading, setLoading] = useState(true)
  const [rules, setRules] = useState<DeliveryRule[]>([])
  const [cards, setCards] = useState<CardData[]>([])
  const [items, setItems] = useState<Item[]>([])

  // 弹窗状态
  const [isModalOpen, setIsModalOpen] = useState(false)
  const [editingRule, setEditingRule] = useState<DeliveryRule | null>(null)
  const [formItemKey, setFormItemKey] = useState('')
  const [formCardId, setFormCardId] = useState('')
  const [formDescription, setFormDescription] = useState('')
  const [formEnabled, setFormEnabled] = useState(true)
  const [saving, setSaving] = useState(false)

  const loadRules = async () => {
    if (!_hasHydrated || !isAuthenticated || !token) return
    try {
      setLoading(true)
      const result = await getDeliveryRules()
      if (result.success) {
        setRules(result.data || [])
      }
    } catch {
      addToast({ type: 'error', message: '加载发货规则失败' })
    } finally {
      setLoading(false)
    }
  }

  const loadCards = async () => {
    if (!_hasHydrated || !isAuthenticated || !token) return
    try {
      const result = await getCards()
      if (result.success) {
        setCards(result.data || [])
      }
    } catch {
      // ignore
    }
  }

  const loadItems = async () => {
    if (!_hasHydrated || !isAuthenticated || !token) return
    try {
      const result = await getItems()
      if (result.success) {
        setItems(result.data || [])
      }
    } catch {
      // ignore
    }
  }

  useEffect(() => {
    if (!_hasHydrated || !isAuthenticated || !token) return
    loadCards()
    loadItems()
    loadRules()
  }, [_hasHydrated, isAuthenticated, token])

  const getItemTitle = (item: Item) => item.item_title || item.title || item.item_id
  const getItemKey = (item: Item) => `${item.cookie_id}::${item.item_id}`
  const findItemByKey = (key: string) => items.find((item) => getItemKey(item) === key)
  const findItemByKeyword = (keyword: string) => items.find((item) => getItemTitle(item) === keyword)

  const itemOptions = items.map((item) => {
    const title = getItemTitle(item)
    return {
      value: getItemKey(item),
      label: `${title}（${item.cookie_id}）`,
    }
  })

  const handleToggleEnabled = async (rule: DeliveryRule) => {
    try {
      await updateDeliveryRule(String(rule.id), { enabled: !rule.enabled })
      addToast({ type: 'success', message: rule.enabled ? '规则已禁用' : '规则已启用' })
      loadRules()
    } catch {
      addToast({ type: 'error', message: '操作失败' })
    }
  }

  const handleDelete = async (id: number) => {
    try {
      await deleteDeliveryRule(String(id))
      addToast({ type: 'success', message: '删除成功' })
      loadRules()
    } catch {
      addToast({ type: 'error', message: '删除失败' })
    }
  }

  const openAddModal = () => {
    setEditingRule(null)
    setFormItemKey('')
    setFormCardId('')
    setFormDescription('')
    setFormEnabled(true)
    setIsModalOpen(true)
  }

  const openEditModal = (rule: DeliveryRule) => {
    setEditingRule(rule)
    setFormItemKey(findItemByKeyword(rule.keyword) ? getItemKey(findItemByKeyword(rule.keyword) as Item) : '')
    setFormCardId(String(rule.card_id))
    setFormDescription(rule.description || '')
    setFormEnabled(rule.enabled)
    setIsModalOpen(true)
  }

  const closeModal = () => {
    setIsModalOpen(false)
    setEditingRule(null)
  }

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    const selectedItem = findItemByKey(formItemKey)
    if (!selectedItem && !editingRule) {
      addToast({ type: 'warning', message: '请选择商品' })
      return
    }
    if (!formCardId) {
      addToast({ type: 'warning', message: '请选择卡券' })
      return
    }

    const keyword = selectedItem ? getItemTitle(selectedItem).trim() : editingRule?.keyword.trim() || ''
    if (!keyword) {
      addToast({ type: 'warning', message: '商品标题为空，无法创建发货规则' })
      return
    }

    setSaving(true)
    try {
      const data = {
        keyword,
        card_id: Number(formCardId),
        delivery_count: 1,  // 固定为1
        description: formDescription || undefined,
        enabled: formEnabled,
      }

      if (editingRule) {
        await updateDeliveryRule(String(editingRule.id), data)
        addToast({ type: 'success', message: '规则已更新' })
      } else {
        await addDeliveryRule(data)
        addToast({ type: 'success', message: '规则已添加' })
      }

      closeModal()
      loadRules()
    } catch {
      addToast({ type: 'error', message: '保存失败' })
    } finally {
      setSaving(false)
    }
  }

  const columns: TableColumnProps<DeliveryRule>[] = [
    {
      title: '匹配商品',
      dataIndex: 'keyword',
      width: 180,
      render: (keyword: string) => (
        <span className="font-medium text-blue-600 dark:text-blue-400">{keyword}</span>
      ),
    },
    {
      title: '关联卡券',
      dataIndex: 'card_name',
      width: 180,
      render: (_value, rule) => (
        <span className="text-sm">{rule.card_name || `卡券ID: ${rule.card_id}`}</span>
      ),
    },
    {
      title: '规格',
      dataIndex: 'card_id',
      width: 180,
      render: (_value, rule) => {
        const relatedCard = cards.find(c => c.id === rule.card_id)
        return relatedCard?.is_multi_spec ? (
          <span className="text-xs text-blue-600 dark:text-blue-400">
            {relatedCard.spec_name}: {relatedCard.spec_value}
          </span>
        ) : (
          <span className="text-gray-400">-</span>
        )
      },
    },
    {
      title: '已发次数',
      dataIndex: 'delivery_times',
      width: 100,
      align: 'center',
      render: (deliveryTimes?: number) => (
        <span className="text-slate-500">{deliveryTimes || 0}</span>
      ),
    },
    {
      title: '状态',
      dataIndex: 'enabled',
      width: 100,
      render: (enabled: boolean) => (
        enabled ? <span className="badge-success">启用</span> : <span className="badge-danger">禁用</span>
      ),
    },
    {
      title: '操作',
      dataIndex: 'operation',
      width: 220,
      render: (_value, rule) => (
        <Space size={4}>
          <Button
            type="text"
            size="mini"
            onClick={() => handleToggleEnabled(rule)}
            className={rule.enabled ? 'accounts-table-action-btn !text-amber-500 hover:!text-amber-500' : 'accounts-table-action-btn !text-emerald-500 hover:!text-emerald-500'}
          >
            {rule.enabled ? '禁用' : '启用'}
          </Button>
          <Button
            type="text"
            size="mini"
            onClick={() => openEditModal(rule)}
            className="accounts-table-action-btn"
          >
            编辑
          </Button>
          <Popconfirm
            title="确定要删除这条规则吗？"
            okText="删除"
            cancelText="取消"
            okButtonProps={{ status: 'danger' }}
            onOk={() => handleDelete(rule.id)}
          >
            <Button
              type="text"
              size="mini"
              className="accounts-table-action-btn !text-red-500 hover:!text-red-500"
            >
              删除
            </Button>
          </Popconfirm>
        </Space>
      ),
    },
  ]

  if (loading && rules.length === 0) {
    return <PageLoading />
  }

  return (
    <div className="space-y-4">
      {/* Rules List */}
      <div
        className="vben-card"
      >
        {/* 标题区 */}
        <div className="accounts-page-intro">
          <h1 className="page-title">自动发货</h1>
          <p className="page-description">配置商品的自动发货规则</p>
        </div>
        <div className="table-toolbar">
          <div className="table-filter-row table-filter-row--lined">
            <div className="table-toolbar-right">
              <Button
                type="primary"
                onClick={openAddModal} className="accounts-header-btn">
                <Plus />
                添加规则
              </Button>
              <Button onClick={loadRules} className="accounts-header-btn">
                <RefreshCw />
                刷新
              </Button>
            </div>
          </div>
        </div>
        <Table
          rowKey="id"
          columns={columns}
          data={rules}
          pagination={false}
          border={false}
          scroll={{ x: 940 }}
          className="accounts-arco-table table-main"
          noDataElement={(
            <Empty
              icon={<Truck className="w-12 h-12 text-gray-300" />}
              description="暂无发货规则"
            />
          )}
        />
      </div>

      <Modal
        visible={isModalOpen}
        title={editingRule ? '编辑发货规则' : '添加发货规则'}
        onCancel={closeModal}
        footer={null}
        unmountOnExit
        style={{ width: 640 }}
      >
        <form onSubmit={handleSubmit}>
          <div className="space-y-4">
            <div>
              <label className="input-label">选择商品 *</label>
              <Select
                value={formItemKey || undefined}
                onChange={(value) => setFormItemKey(String(value || ''))}
                options={itemOptions}
                placeholder="请选择商品"
                showSearch
                allowClear
                filterOption={(inputValue, option) =>
                  String(option.props?.children || option.props?.label || '')
                    .toLowerCase()
                    .includes(inputValue.toLowerCase())
                }
                dropdownMenuStyle={{ maxHeight: 280 }}
              />
              <p className="text-xs text-gray-500 mt-1">
                规则会使用所选商品标题匹配自动发货。
              </p>
              {editingRule && !formItemKey && (
                <p className="text-xs text-amber-500 mt-1">
                  当前旧规则未匹配到商品，原关键词：{editingRule.keyword}
                </p>
              )}
            </div>
            <div className="input-group">
              <label className="input-label">关联卡券 *</label>
              <Select
                value={formCardId}
                onChange={setFormCardId}
                options={[
                  { value: '', label: '请选择卡券' },
                  ...cards.map((card) => ({
                    value: String(card.id),
                    label: card.is_multi_spec
                      ? `${card.name} [${card.spec_name}: ${card.spec_value}]`
                      : card.name || card.text_content?.substring(0, 20) || `卡券 ${card.id}`,
                  })),
                ]}
                placeholder="请选择卡券"
              />
            </div>
            <div>
              <label className="input-label">描述（可选）</label>
              <Input.TextArea
                value={formDescription}
                onChange={setFormDescription}
                placeholder="规则描述，方便识别"
                autoSize={{ minRows: 3, maxRows: 5 }}
              />
            </div>
            <div className="flex items-center justify-between pt-2">
              <span className="text-sm font-medium text-slate-700 dark:text-slate-200">启用此规则</span>
              <Switch checked={formEnabled} onChange={setFormEnabled} />
            </div>
          </div>
          <div className="mt-6 flex justify-end gap-3">
            <Button onClick={closeModal} disabled={saving}>
              取消
            </Button>
            <Button htmlType="submit" type="primary" disabled={saving}>
              {saving ? (
                <span className="flex items-center gap-2">
                  <Loader2 className="w-4 h-4 animate-spin" />
                  保存中...
                </span>
              ) : (
                '保存'
              )}
            </Button>
          </div>
        </form>
      </Modal>
    </div>
  )
}
