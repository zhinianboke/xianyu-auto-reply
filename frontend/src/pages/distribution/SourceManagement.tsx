/**
 * 货源管理页面
 * 
 * 两个 Tab：
 * 1. 我的对接 - 通过输入对接码绑定供应商，绑定后可在货源广场看到该供应商的 dealer_only 卡券
 * 2. 对接我的 - 查看所有绑定了自己对接码的分销商，支持删除（级联删除对接记录）
 */
import { useState, useEffect } from 'react'
import { Link2, Plus, Trash2, RefreshCw, Loader2, Users } from 'lucide-react'
import { getSourceBindings, bindDockCode, unbindSource, getBoundToMe, removeBoundUser } from '@/api/distribution'
import type { SourceBinding, BoundUser } from '@/api/distribution'
import { useUIStore } from '@/store/uiStore'
import { useAuthStore } from '@/store/authStore'
import { PageLoading } from '@/components/common/Loading'
import { ConfirmModal } from '@/components/common/ConfirmModal'

type TabKey = 'my-bindings' | 'bound-to-me'

export function SourceManagement() {
  const { addToast } = useUIStore()
  const { isAuthenticated, token, _hasHydrated } = useAuthStore()
  const [activeTab, setActiveTab] = useState<TabKey>('my-bindings')

  // 我的对接
  const [loading, setLoading] = useState(true)
  const [bindings, setBindings] = useState<SourceBinding[]>([])
  const [showBindModal, setShowBindModal] = useState(false)
  const [dockCodeInput, setDockCodeInput] = useState('')
  const [binding, setBinding] = useState(false)
  const [unbindConfirm, setUnbindConfirm] = useState<{ open: boolean; id: number | null; name: string }>({ open: false, id: null, name: '' })
  const [unbinding, setUnbinding] = useState(false)

  // 对接我的
  const [boundLoading, setBoundLoading] = useState(true)
  const [boundUsers, setBoundUsers] = useState<BoundUser[]>([])
  const [removeConfirm, setRemoveConfirm] = useState<{ open: boolean; id: number | null; name: string }>({ open: false, id: null, name: '' })
  const [removing, setRemoving] = useState(false)

  // 加载我的对接
  const loadBindings = async () => {
    if (!_hasHydrated || !isAuthenticated || !token) return
    try {
      setLoading(true)
      const result = await getSourceBindings()
      if (result.success) {
        setBindings(result.data || [])
      }
    } catch {
      addToast({ type: 'error', message: '加载货源列表失败' })
    } finally {
      setLoading(false)
    }
  }

  // 加载对接我的
  const loadBoundUsers = async () => {
    if (!_hasHydrated || !isAuthenticated || !token) return
    try {
      setBoundLoading(true)
      const result = await getBoundToMe()
      if (result.success) {
        setBoundUsers(result.data || [])
      }
    } catch {
      addToast({ type: 'error', message: '加载对接列表失败' })
    } finally {
      setBoundLoading(false)
    }
  }

  useEffect(() => {
    loadBindings()
    loadBoundUsers()
  }, [_hasHydrated, isAuthenticated, token])

  const handleBind = async () => {
    const code = dockCodeInput.trim()
    if (!code) {
      addToast({ type: 'warning', message: '请输入对接码' })
      return
    }
    try {
      setBinding(true)
      const result = await bindDockCode(code)
      if (result.success) {
        addToast({ type: 'success', message: result.message || '绑定成功' })
        setShowBindModal(false)
        setDockCodeInput('')
        await loadBindings()
      } else {
        addToast({ type: 'error', message: result.message || '绑定失败' })
      }
    } catch {
      addToast({ type: 'error', message: '绑定失败' })
    } finally {
      setBinding(false)
    }
  }

  const handleUnbind = async (id: number) => {
    try {
      setUnbinding(true)
      const result = await unbindSource(id)
      if (result.success) {
        addToast({ type: 'success', message: result.message || '已解绑' })
        setUnbindConfirm({ open: false, id: null, name: '' })
        await loadBindings()
      } else {
        addToast({ type: 'error', message: result.message || '解绑失败' })
      }
    } catch {
      addToast({ type: 'error', message: '解绑失败' })
    } finally {
      setUnbinding(false)
    }
  }

  const handleRemoveBound = async (id: number) => {
    try {
      setRemoving(true)
      const result = await removeBoundUser(id)
      if (result.success) {
        addToast({ type: 'success', message: result.message || '已删除' })
        setRemoveConfirm({ open: false, id: null, name: '' })
        await loadBoundUsers()
      } else {
        addToast({ type: 'error', message: result.message || '删除失败' })
      }
    } catch {
      addToast({ type: 'error', message: '删除失败' })
    } finally {
      setRemoving(false)
    }
  }

  const handleRefresh = () => {
    if (activeTab === 'my-bindings') {
      loadBindings()
    } else {
      loadBoundUsers()
    }
  }

  const tabs = [
    { key: 'my-bindings' as TabKey, label: '我的对接', count: bindings.length },
    { key: 'bound-to-me' as TabKey, label: '对接我的', count: boundUsers.length },
  ]

  return (
    <div className="space-y-4">
      {/* 页头 */}
      <div className="page-header flex-between flex-wrap gap-4">
        <div>
          <h1 className="page-title">货源管理</h1>
          <p className="page-description">管理对接码绑定关系，查看供应商和分销商的对接情况</p>
        </div>
        <div className="flex items-center gap-2">
          <button onClick={handleRefresh} className="btn-ios-secondary">
            <RefreshCw className="w-4 h-4" />
            刷新
          </button>
          {activeTab === 'my-bindings' && (
            <button onClick={() => setShowBindModal(true)} className="btn-ios-primary">
              <Plus className="w-4 h-4" />
              新增货源
            </button>
          )}
        </div>
      </div>

      {/* Tab 切换 */}
      <div
        className="vben-card flex flex-col"
        style={{ height: 'calc(100vh - 220px)', minHeight: '420px' }}
      >
        <div className="border-b border-slate-200 dark:border-slate-700 flex-shrink-0">
          <div className="flex">
            {tabs.map((tab) => (
              <button
                key={tab.key}
                onClick={() => setActiveTab(tab.key)}
                className={`px-6 py-3 text-sm font-medium border-b-2 transition-colors ${
                  activeTab === tab.key
                    ? 'border-blue-500 text-blue-600 dark:text-blue-400'
                    : 'border-transparent text-slate-500 hover:text-slate-700 dark:hover:text-slate-300'
                }`}
              >
                {tab.label}
                <span className={`ml-2 px-1.5 py-0.5 rounded-full text-xs ${
                  activeTab === tab.key
                    ? 'bg-blue-100 text-blue-600 dark:bg-blue-900/30 dark:text-blue-400'
                    : 'bg-slate-100 text-slate-500 dark:bg-slate-700 dark:text-slate-400'
                }`}>
                  {tab.count}
                </span>
              </button>
            ))}
          </div>
        </div>

        {/* 表格主体：横向 + 纵向滚动，粘性表头 */}
        <div className="flex-1 overflow-x-auto overflow-y-auto scrollbar-visible">
          {/* 我的对接 Tab */}
          {activeTab === 'my-bindings' && (
            loading ? (
              <div className="py-12"><PageLoading /></div>
            ) : bindings.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-12 text-gray-400">
                <Link2 className="w-12 h-12 mb-3 opacity-30" />
                <p className="text-sm">暂无绑定的货源</p>
                <p className="text-xs mt-1">点击"新增货源"按钮，输入供应商提供的对接码即可绑定</p>
              </div>
            ) : (
              <table className="table-ios min-w-[800px]">
                <thead className="sticky top-0 bg-slate-50 dark:bg-slate-700/50 z-10">
                  <tr>
                    <th className="whitespace-nowrap">供应商</th>
                    <th className="whitespace-nowrap">对接码</th>
                    <th className="whitespace-nowrap">绑定时间</th>
                    <th className="whitespace-nowrap sticky right-0 bg-slate-50 dark:bg-slate-800 z-20">操作</th>
                  </tr>
                </thead>
                <tbody>
                  {bindings.map((item) => (
                    <tr key={item.id}>
                      <td className="whitespace-nowrap font-medium text-slate-900 dark:text-white">{item.target_username}</td>
                      <td className="whitespace-nowrap font-mono text-sm tracking-wider">{item.dock_code}</td>
                      <td className="whitespace-nowrap text-sm text-slate-500">
                        {item.created_at ? new Date(item.created_at).toLocaleString('zh-CN') : '-'}
                      </td>
                      <td className="whitespace-nowrap sticky right-0 bg-white dark:bg-slate-900 z-10">
                        <button
                          onClick={() => setUnbindConfirm({ open: true, id: item.id, name: item.target_username })}
                          className="p-2 rounded-lg hover:bg-red-50 dark:hover:bg-red-900/20 transition-colors"
                          title="解绑"
                        >
                          <Trash2 className="w-4 h-4 text-red-500" />
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )
          )}

          {/* 对接我的 Tab */}
          {activeTab === 'bound-to-me' && (
            boundLoading ? (
              <div className="py-12"><PageLoading /></div>
            ) : boundUsers.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-12 text-gray-400">
                <Users className="w-12 h-12 mb-3 opacity-30" />
                <p className="text-sm">暂无分销商绑定你的对接码</p>
                <p className="text-xs mt-1">在个人设置中获取对接码并分享给分销商即可</p>
              </div>
            ) : (
              <table className="table-ios min-w-[900px]">
                <thead className="sticky top-0 bg-slate-50 dark:bg-slate-700/50 z-10">
                  <tr>
                    <th className="whitespace-nowrap">分销商</th>
                    <th className="whitespace-nowrap">使用对接码</th>
                    <th className="whitespace-nowrap">对接卡券数</th>
                    <th className="whitespace-nowrap">绑定时间</th>
                    <th className="whitespace-nowrap sticky right-0 bg-slate-50 dark:bg-slate-800 z-20">操作</th>
                  </tr>
                </thead>
                <tbody>
                  {boundUsers.map((item) => (
                    <tr key={item.id}>
                      <td className="whitespace-nowrap font-medium text-slate-900 dark:text-white">{item.username}</td>
                      <td className="whitespace-nowrap font-mono text-sm tracking-wider">{item.dock_code}</td>
                      <td className="whitespace-nowrap">
                        <span className="px-2 py-0.5 rounded-full text-xs bg-blue-100 text-blue-600 dark:bg-blue-900/30 dark:text-blue-400">
                          {item.dock_count} 个
                        </span>
                      </td>
                      <td className="whitespace-nowrap text-sm text-slate-500">
                        {item.created_at ? new Date(item.created_at).toLocaleString('zh-CN') : '-'}
                      </td>
                      <td className="whitespace-nowrap sticky right-0 bg-white dark:bg-slate-900 z-10">
                        <button
                          onClick={() => setRemoveConfirm({ open: true, id: item.id, name: item.username })}
                          className="p-2 rounded-lg hover:bg-red-50 dark:hover:bg-red-900/20 transition-colors"
                          title="删除"
                        >
                          <Trash2 className="w-4 h-4 text-red-500" />
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )
          )}
        </div>
      </div>

      {/* 新增绑定弹窗 */}
      {showBindModal && (
        <div className="fixed inset-0 z-[100] flex items-center justify-center">
          <div className="absolute inset-0 bg-black/50 backdrop-blur-sm" onClick={() => !binding && setShowBindModal(false)} />
          <div className="relative w-full max-w-sm mx-4 bg-white dark:bg-slate-800 rounded-2xl shadow-2xl border border-slate-200 dark:border-slate-700">
            <div className="p-6">
              <h3 className="text-lg font-semibold text-slate-900 dark:text-white mb-1">新增货源</h3>
              <p className="text-sm text-gray-500 mb-4">输入供应商提供的对接码进行绑定</p>
              <div>
                <label className="input-label">对接码</label>
                <input
                  type="text"
                  value={dockCodeInput}
                  onChange={(e) => setDockCodeInput(e.target.value.toUpperCase())}
                  placeholder="请输入对接码"
                  className="input-ios font-mono tracking-widest text-center text-lg"
                  maxLength={32}
                  autoFocus
                  onKeyDown={(e) => e.key === 'Enter' && handleBind()}
                />
                <p className="text-xs text-amber-600 dark:text-amber-400 mt-2">提示：对接码在个人设置中获取</p>
              </div>
            </div>
            <div className="flex gap-3 px-6 pb-6">
              <button
                onClick={() => { setShowBindModal(false); setDockCodeInput('') }}
                disabled={binding}
                className="flex-1 px-4 py-2.5 rounded-lg font-medium bg-slate-100 dark:bg-slate-700 text-slate-700 dark:text-slate-300 hover:bg-slate-200 dark:hover:bg-slate-600 transition-colors disabled:opacity-50"
              >
                取消
              </button>
              <button
                onClick={handleBind}
                disabled={binding || !dockCodeInput.trim()}
                className="flex-1 px-4 py-2.5 rounded-lg font-medium bg-blue-500 hover:bg-blue-600 text-white transition-colors flex items-center justify-center gap-2 disabled:opacity-50"
              >
                {binding && <Loader2 className="w-4 h-4 animate-spin" />}
                绑定
              </button>
            </div>
          </div>
        </div>
      )}

      {/* 解绑确认弹窗 */}
      <ConfirmModal
        isOpen={unbindConfirm.open}
        title="解绑确认"
        message={`确定要解绑供应商「${unbindConfirm.name}」吗？解绑后将无法在货源广场看到其专属卡券，同时相关对接记录将被删除。`}
        confirmText="确定解绑"
        cancelText="取消"
        type="danger"
        loading={unbinding}
        onConfirm={() => unbindConfirm.id && handleUnbind(unbindConfirm.id)}
        onCancel={() => setUnbindConfirm({ open: false, id: null, name: '' })}
      />

      {/* 删除对接我的确认弹窗 */}
      <ConfirmModal
        isOpen={removeConfirm.open}
        title="删除确认"
        message={`确定要删除分销商「${removeConfirm.name}」的绑定关系吗？该分销商的所有对接记录（包括下级分销商的对接记录）将被一并删除。`}
        confirmText="确定删除"
        cancelText="取消"
        type="danger"
        loading={removing}
        onConfirm={() => removeConfirm.id && handleRemoveBound(removeConfirm.id)}
        onCancel={() => setRemoveConfirm({ open: false, id: null, name: '' })}
      />
    </div>
  )
}



