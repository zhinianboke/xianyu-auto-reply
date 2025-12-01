import { useState, useEffect } from 'react'
import type { FormEvent } from 'react'
import { motion } from 'framer-motion'
import { Truck, RefreshCw, Plus, Edit2, Trash2, Power, PowerOff, X, Loader2 } from 'lucide-react'
import { getDeliveryRules, deleteDeliveryRule, updateDeliveryRule, addDeliveryRule } from '@/api/delivery'
import { getCards, type CardData } from '@/api/cards'
import { useUIStore } from '@/store/uiStore'
import { useAuthStore } from '@/store/authStore'
import { PageLoading } from '@/components/common/Loading'
import { Select } from '@/components/common/Select'
import type { DeliveryRule } from '@/types'

export function Delivery() {
  const { addToast } = useUIStore()
  const { isAuthenticated, token, _hasHydrated } = useAuthStore()
  const [loading, setLoading] = useState(true)
  const [rules, setRules] = useState<DeliveryRule[]>([])
  const [cards, setCards] = useState<CardData[]>([])
  
  // 弹窗状态
  const [isModalOpen, setIsModalOpen] = useState(false)
  const [editingRule, setEditingRule] = useState<DeliveryRule | null>(null)
  const [formKeyword, setFormKeyword] = useState('')
  const [formCardId, setFormCardId] = useState('')
  const [formDeliveryCount, setFormDeliveryCount] = useState(1)
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

  useEffect(() => {
    if (!_hasHydrated || !isAuthenticated || !token) return
    loadCards()
    loadRules()
  }, [_hasHydrated, isAuthenticated, token])

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
    if (!confirm('确定要删除这条规则吗？')) return
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
    setFormKeyword('')
    setFormCardId('')
    setFormDeliveryCount(1)
    setFormDescription('')
    setFormEnabled(true)
    setIsModalOpen(true)
  }

  const openEditModal = (rule: DeliveryRule) => {
    setEditingRule(rule)
    setFormKeyword(rule.keyword)
    setFormCardId(String(rule.card_id))
    setFormDeliveryCount(rule.delivery_count)
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
    if (!formKeyword.trim()) {
      addToast({ type: 'warning', message: '请输入触发关键词' })
      return
    }
    if (!formCardId) {
      addToast({ type: 'warning', message: '请选择卡券' })
      return
    }

    setSaving(true)
    try {
      const data = {
        keyword: formKeyword.trim(),
        card_id: Number(formCardId),
        delivery_count: formDeliveryCount,
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

  if (loading && rules.length === 0) {
    return <PageLoading />
  }

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="page-title">自动发货</h1>
          <p className="page-description">配置商品的自动发货规则</p>
        </div>
        <div className="flex gap-3">
          <button onClick={openAddModal} className="btn-ios-primary ">
            <Plus className="w-4 h-4" />
            添加规则
          </button>
          <button onClick={loadRules} className="btn-ios-secondary ">
            <RefreshCw className="w-4 h-4" />
            刷新
          </button>
        </div>
      </div>

      {/* Rules List */}
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.1 }}
        className="vben-card"
      >
        <div className="vben-card-header 
                      flex items-center justify-between">
          <h2 className="vben-card-title ">
            <Truck className="w-4 h-4" />
            发货规则
          </h2>
          <span className="badge-primary">{rules.length} 条规则</span>
        </div>
        <div className="overflow-x-auto">
          <table className="table-ios">
            <thead>
              <tr>
                <th>触发关键词</th>
                <th>关联卡券</th>
                <th>发货数量</th>
                <th>已发次数</th>
                <th>状态</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              {rules.length === 0 ? (
                <tr>
                  <td colSpan={6} className="text-center py-8 text-gray-500">
                    <div className="flex flex-col items-center gap-2">
                      <Truck className="w-12 h-12 text-gray-300" />
                      <p>暂无发货规则</p>
                    </div>
                  </td>
                </tr>
              ) : (
                rules.map((rule) => (
                  <tr key={rule.id}>
                    <td className="font-medium text-blue-600 dark:text-blue-400">{rule.keyword}</td>
                    <td className="text-sm">{rule.card_name || `卡券ID: ${rule.card_id}`}</td>
                    <td className="text-center">{rule.delivery_count}</td>
                    <td className="text-center text-slate-500">{rule.delivery_times || 0}</td>
                    <td>
                      {rule.enabled ? (
                        <span className="badge-success">启用</span>
                      ) : (
                        <span className="badge-danger">禁用</span>
                      )}
                    </td>
                    <td>
                      <div className="">
                        <button
                          onClick={() => handleToggleEnabled(rule)}
                          className="p-2 rounded-lg hover:bg-gray-100 transition-colors"
                          title={rule.enabled ? '禁用' : '启用'}
                        >
                          {rule.enabled ? (
                            <PowerOff className="w-4 h-4 text-amber-500" />
                          ) : (
                            <Power className="w-4 h-4 text-emerald-500" />
                          )}
                        </button>
                        <button
                          onClick={() => openEditModal(rule)}
                          className="p-2 rounded-lg hover:bg-gray-100 transition-colors"
                          title="编辑"
                        >
                          <Edit2 className="w-4 h-4 text-blue-500 dark:text-blue-400" />
                        </button>
                        <button
                          onClick={() => handleDelete(rule.id)}
                          className="p-2 rounded-lg hover:bg-red-50 transition-colors"
                          title="删除"
                        >
                          <Trash2 className="w-4 h-4 text-red-500" />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </motion.div>

      {/* 添加/编辑规则弹窗 */}
      {isModalOpen && (
        <div className="modal-overlay">
          <div className="modal-content max-w-lg">
            <div className="modal-header flex items-center justify-between">
              <h2 className="text-lg font-semibold">
                {editingRule ? '编辑发货规则' : '添加发货规则'}
              </h2>
              <button onClick={closeModal} className="p-1 hover:bg-gray-100 rounded-lg">
                <X className="w-4 h-4 text-gray-500" />
              </button>
            </div>
            <form onSubmit={handleSubmit}>
              <div className="modal-body space-y-4">
                <div>
                  <label className="input-label">触发关键词 *</label>
                  <input
                    type="text"
                    value={formKeyword}
                    onChange={(e) => setFormKeyword(e.target.value)}
                    className="input-ios"
                    placeholder="输入触发自动发货的关键词"
                    required
                  />
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
                        label: card.name || card.text_content?.substring(0, 20) || `卡券 ${card.id}`,
                      })),
                    ]}
                    placeholder="请选择卡券"
                  />
                </div>
                <div>
                  <label className="input-label">发货数量</label>
                  <input
                    type="number"
                    value={formDeliveryCount}
                    onChange={(e) => setFormDeliveryCount(Number(e.target.value) || 1)}
                    className="input-ios"
                    min={1}
                    placeholder="每次发货的卡密数量"
                  />
                </div>
                <div>
                  <label className="input-label">描述（可选）</label>
                  <textarea
                    value={formDescription}
                    onChange={(e) => setFormDescription(e.target.value)}
                    className="input-ios h-20 resize-none"
                    placeholder="规则描述，方便识别"
                  />
                </div>
                <div className="flex items-center justify-between pt-2">
                  <span className="text-sm font-medium text-slate-700 dark:text-slate-200">启用此规则</span>
                  <button
                    type="button"
                    onClick={() => setFormEnabled(!formEnabled)}
                    className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${
                      formEnabled ? 'bg-blue-600' : 'bg-slate-300 dark:bg-slate-600'
                    }`}
                  >
                    <span
                      className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
                        formEnabled ? 'translate-x-6' : 'translate-x-1'
                      }`}
                    />
                  </button>
                </div>
              </div>
              <div className="modal-footer">
                <button type="button" onClick={closeModal} className="btn-ios-secondary" disabled={saving}>
                  取消
                </button>
                <button type="submit" className="btn-ios-primary" disabled={saving}>
                  {saving ? (
                    <span className="">
                      <Loader2 className="w-4 h-4 animate-spin" />
                      保存中...
                    </span>
                  ) : (
                    '保存'
                  )}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  )
}
