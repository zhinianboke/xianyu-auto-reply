/**
 * 对接商品页面
 * 
 * 功能：展示当前用户已对接的卡券记录列表，管理员可查看所有用户的对接记录
 * 支持搜索、分页、编辑、删除操作
 */
import { useState, useEffect, useCallback } from 'react'
import { Search, RefreshCw, PackageCheck, Pencil, Trash2, X, Filter, MessageCircle, MessageSquare, Mail, Truck, Copy } from 'lucide-react'
import { getDockRecords, updateDockRecord, deleteDockRecord, toggleSubDock, getPickupUrl } from '@/api/distribution'
import type { DockRecord, DockRecordFilterParams } from '@/api/distribution'
import { useUIStore } from '@/store/uiStore'
import { useAuthStore } from '@/store/authStore'
import { EditDockModal } from './EditDockModal'
import { ConfirmModal } from '@/components/common/ConfirmModal'

export function DockedProducts() {
  const { addToast } = useUIStore()
  const { user } = useAuthStore()
  const isAdmin = Boolean(user?.is_admin)
  const [loading, setLoading] = useState(true)
  const [records, setRecords] = useState<DockRecord[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)
  const [totalPages, setTotalPages] = useState(0)
  const [searchText, setSearchText] = useState('')
  const [showFilters, setShowFilters] = useState(false)
  const [filters, setFilters] = useState<DockRecordFilterParams>({
    status: null,
    level: null,
    allow_sub_dock: null,
  })
  const [editModalOpen, setEditModalOpen] = useState(false)
  const [selectedRecord, setSelectedRecord] = useState<DockRecord | null>(null)
  const [priceModalOpen, setPriceModalOpen] = useState(false)
  const [priceModalRecord, setPriceModalRecord] = useState<DockRecord | null>(null)
  const [subDockPriceInput, setSubDockPriceInput] = useState('')
  const [subDockVisibility, setSubDockVisibility] = useState('public')
  const [priceSubmitting, setPriceSubmitting] = useState(false)
  const [isEditMode, setIsEditMode] = useState(false)
  const [deleteRecord, setDeleteRecord] = useState<DockRecord | null>(null)
  const [deletingRecord, setDeletingRecord] = useState(false)

  // 提货地址弹窗状态
  const [pickupModalOpen, setPickupModalOpen] = useState(false)
  const [pickupUrl, setPickupUrl] = useState('')
  const [pickupLoading, setPickupLoading] = useState(false)
  const [pickupRecord, setPickupRecord] = useState<DockRecord | null>(null)

  // 加载数据
  const loadData = useCallback(async (
    p: number = page,
    ps: number = pageSize,
    search: string = searchText,
    currentFilters: DockRecordFilterParams = filters,
  ) => {
    setLoading(true)
    try {
      const result = await getDockRecords(p, ps, search, currentFilters)
      setRecords(result.list)
      setTotal(result.total)
      setPage(result.page)
      setPageSize(result.page_size)
      setTotalPages(result.total_pages)
    } catch {
      addToast({ type: 'error', message: '加载对接记录失败' })
    } finally {
      setLoading(false)
    }
  }, [searchText, filters, page, pageSize, addToast])

  useEffect(() => {
    loadData(1, pageSize)
  }, [])

  // 搜索防抖
  useEffect(() => {
    const timer = setTimeout(() => {
      loadData(1, pageSize)
    }, 300)
    return () => clearTimeout(timer)
  }, [searchText])

  // 修改已开放的下级对接设置
  const handleEditSubDock = (record: DockRecord) => {
    setPriceModalRecord(record)
    setSubDockPriceInput(record.sub_dock_price || '')
    setSubDockVisibility(record.sub_dock_visibility || 'public')
    setIsEditMode(true)
    setPriceModalOpen(true)
  }

  // 切换开放对接
  const handleToggleSubDock = async (record: DockRecord) => {
    const newAllow = !record.allow_sub_dock
    if (newAllow) {
      setPriceModalRecord(record)
      setSubDockPriceInput(record.sub_dock_price || '')
      setSubDockVisibility(record.sub_dock_visibility || 'public')
      setIsEditMode(false)
      setPriceModalOpen(true)
      return
    }
    try {
      const result = await toggleSubDock(record.id, false)
      if (result.success) {
        addToast({ type: 'success', message: '已关闭下级对接' })
        loadData(page, pageSize)
      } else {
        addToast({ type: 'error', message: result.message || '操作失败' })
      }
    } catch {
      addToast({ type: 'error', message: '操作失败' })
    }
  }

  // 提交开放对接价格
  const handlePriceSubmit = async () => {
    if (!priceModalRecord) return
    if (!subDockPriceInput.trim()) {
      addToast({ type: 'warning', message: '请输入对接价格' })
      return
    }
    setPriceSubmitting(true)
    try {
      const result = await toggleSubDock(priceModalRecord.id, true, subDockPriceInput.trim(), subDockVisibility)
      if (result.success) {
        addToast({ type: 'success', message: isEditMode ? '下级对接设置已更新' : '已开放下级对接' })
        setPriceModalOpen(false)
        loadData(page, pageSize)
      } else {
        addToast({ type: 'error', message: result.message || '操作失败' })
      }
    } catch {
      addToast({ type: 'error', message: '操作失败' })
    } finally {
      setPriceSubmitting(false)
    }
  }

  // 切换对接状态
  const handleToggleStatus = async (record: DockRecord) => {
    // 被上级禁用锁定的记录，分销商不可自行启用
    if (!record.status && record.owner_disabled) {
      addToast({ type: 'warning', message: '该对接记录已被上级禁用，无法自行启用，请联系上级分销商' })
      return
    }
    try {
      const updateData: Record<string, unknown> = { status: !record.status }
      // 禁用时设置禁用原因，启用时清空禁用原因
      if (record.status) {
        updateData.disable_reason = '分销商禁用'
      } else {
        updateData.disable_reason = ''
      }
      const result = await updateDockRecord(record.id, updateData)
      if (result.success) {
        addToast({ type: 'success', message: record.status ? '已停用' : '已启用' })
        loadData(page, pageSize)
      } else {
        addToast({ type: 'error', message: result.message || '操作失败' })
      }
    } catch {
      addToast({ type: 'error', message: '操作失败' })
    }
  }

  // 删除对接记录
  const handleDelete = async (record: DockRecord) => {
    setDeletingRecord(true)
    try {
      const result = await deleteDockRecord(record.id)
      if (result.success) {
        addToast({ type: 'success', message: '删除成功' })
        loadData(page, pageSize)
      } else {
        addToast({ type: 'error', message: result.message || '删除失败' })
      }
    } catch {
      addToast({ type: 'error', message: '删除失败' })
    } finally {
      setDeletingRecord(false)
    }
  }

  // 打开提货地址弹窗
  const handleOpenPickup = async (record: DockRecord) => {
    setPickupRecord(record)
    setPickupUrl('')
    setPickupModalOpen(true)
    setPickupLoading(true)
    try {
      const result = await getPickupUrl(record.id)
      if (result.success && result.data?.pickup_url) {
        setPickupUrl(result.data.pickup_url)
      } else {
        addToast({ type: 'error', message: result.message || '获取提货地址失败' })
      }
    } catch {
      addToast({ type: 'error', message: '获取提货地址失败' })
    } finally {
      setPickupLoading(false)
    }
  }

  // 复制提货地址
  const handleCopyPickupUrl = () => {
    if (!pickupUrl) return
    navigator.clipboard.writeText(pickupUrl).then(() => {
      addToast({ type: 'success', message: '提货地址已复制到剪贴板' })
    }).catch(() => {
      addToast({ type: 'error', message: '复制失败，请手动复制' })
    })
  }

  const handlePageChange = (newPage: number) => {
    if (newPage < 1 || newPage > totalPages) return
    loadData(newPage, pageSize)
  }

  const handlePageSizeChange = (newSize: number) => {
    setPageSize(newSize)
    loadData(1, newSize)
  }

  const handleFilterChange = (key: keyof DockRecordFilterParams, value: boolean | number | null) => {
    const nextFilters: DockRecordFilterParams = {
      ...filters,
      [key]: value,
    }
    setFilters(nextFilters)
    loadData(1, pageSize, searchText, nextFilters)
  }

  const handleResetFilters = () => {
    const emptyFilters: DockRecordFilterParams = {
      status: null,
      level: null,
      allow_sub_dock: null,
    }
    setFilters(emptyFilters)
    loadData(1, pageSize, searchText, emptyFilters)
  }

  const hasActiveFilters = Object.values(filters).some(value => value !== null && value !== undefined)

  const renderContactInfo = (record: DockRecord) => {
    const contactItems = [
      {
        key: 'wechat',
        label: '微信',
        value: record.contact_wechat,
        icon: MessageCircle,
        iconClassName: 'text-emerald-500',
      },
      {
        key: 'qq',
        label: 'QQ',
        value: record.contact_qq,
        icon: MessageSquare,
        iconClassName: 'text-sky-500',
      },
      {
        key: 'email',
        label: '邮箱',
        value: record.contact_email,
        icon: Mail,
        iconClassName: 'text-amber-500',
      },
    ].filter(item => Boolean(item.value))

    if (contactItems.length === 0) {
      return <span className="text-slate-400">-</span>
    }

    return (
      <div className="flex flex-col gap-1 min-w-[180px]">
        {contactItems.map(item => {
          const Icon = item.icon
          return (
            <div key={item.key} className="flex items-center gap-1.5 min-w-0 text-xs text-slate-600 dark:text-slate-300">
              <Icon className={`w-3.5 h-3.5 shrink-0 ${item.iconClassName}`} />
              <span className="shrink-0 text-slate-400">{item.label}</span>
              <span className="truncate" title={item.value || ''}>{item.value}</span>
            </div>
          )
        })}
      </div>
    )
  }

  return (
    <div className="space-y-4">
      {/* 页头 */}
      <div className="page-header flex-between flex-wrap gap-4">
        <div>
          <h1 className="page-title">对接的商品</h1>
          <p className="page-description">管理已对接的卡券商品</p>
        </div>
        <button onClick={() => loadData(page, pageSize)} className="btn-ios-secondary">
          <RefreshCw className="w-4 h-4" />
          刷新
        </button>
      </div>

      {/* 对接记录列表：搜索 + 表格 + 分页合卡，参照账号管理布局 */}
      <div
        className="vben-card flex flex-col"
        style={{ height: 'calc(100vh - 220px)', minHeight: '420px' }}
      >
        {/* 卡片头：标题 + 总数 + 搜索/筛选 */}
        <div className="vben-card-header flex-shrink-0 flex-wrap gap-3">
          <div className="flex items-center gap-2">
            <h2 className="vben-card-title">对接记录列表</h2>
            <span className="badge-primary">{total} 条记录</span>
          </div>
          <div className="flex items-center gap-2 flex-wrap justify-end">
            <div className="relative w-full sm:w-72">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
              <input
                type="text"
                value={searchText}
                onChange={(e) => setSearchText(e.target.value)}
                className="input-ios pl-9"
                placeholder="搜索对接名称..."
              />
            </div>
            <button
              onClick={() => setShowFilters(!showFilters)}
              className={`btn-ios-secondary btn-sm flex items-center gap-1 ${hasActiveFilters ? 'text-blue-600 border-blue-300' : ''}`}
            >
              <Filter className="w-4 h-4" />
              筛选
              {hasActiveFilters && <span className="ml-1 px-1.5 py-0.5 text-xs bg-blue-100 text-blue-600 rounded-full">已启用</span>}
            </button>
            {hasActiveFilters && (
              <button onClick={handleResetFilters} className="btn-ios-secondary btn-sm text-red-500">
                重置
              </button>
            )}
          </div>
        </div>

        {showFilters && (
          <div className="flex-shrink-0 px-4 py-3 border-b border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800/50">
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
              <div className="input-group">
                <label className="input-label">状态</label>
                <select
                  value={filters.status === null || filters.status === undefined ? '' : String(filters.status)}
                  onChange={(e) => handleFilterChange('status', e.target.value === '' ? null : e.target.value === 'true')}
                  className="input-ios"
                >
                  <option value="">全部</option>
                  <option value="true">已启用</option>
                  <option value="false">已停用</option>
                </select>
              </div>
              <div className="input-group">
                <label className="input-label">层级</label>
                <select
                  value={filters.level === null || filters.level === undefined ? '' : String(filters.level)}
                  onChange={(e) => handleFilterChange('level', e.target.value === '' ? null : Number(e.target.value))}
                  className="input-ios"
                >
                  <option value="">全部</option>
                  <option value="1">一级</option>
                  <option value="2">二级</option>
                </select>
              </div>
              <div className="input-group">
                <label className="input-label">开放对接</label>
                <select
                  value={filters.allow_sub_dock === null || filters.allow_sub_dock === undefined ? '' : String(filters.allow_sub_dock)}
                  onChange={(e) => handleFilterChange('allow_sub_dock', e.target.value === '' ? null : e.target.value === 'true')}
                  className="input-ios"
                >
                  <option value="">全部</option>
                  <option value="true">已开放</option>
                  <option value="false">未开放</option>
                </select>
              </div>
            </div>
          </div>
        )}

        {/* 表格主体：横向 + 纵向滚动，粘性表头 */}
        <div className="flex-1 overflow-x-auto overflow-y-auto scrollbar-visible">
          {loading ? (
            <div className="flex justify-center py-8">
              <RefreshCw className="w-6 h-6 animate-spin text-blue-500" />
            </div>
          ) : (
            <table className="table-ios min-w-[1540px]">
              <thead className="bg-slate-50 dark:bg-slate-700/50">
                <tr>
                  <th className="whitespace-nowrap sticky top-0 bg-slate-50 dark:bg-slate-700/50 z-10">ID</th>
                  {isAdmin && <th className="whitespace-nowrap sticky top-0 bg-slate-50 dark:bg-slate-700/50 z-10">所属用户</th>}
                  <th className="whitespace-nowrap sticky top-0 bg-slate-50 dark:bg-slate-700/50 z-10">对接名称</th>
                  <th className="whitespace-nowrap sticky top-0 bg-slate-50 dark:bg-slate-700/50 z-10">层级</th>
                  <th className="whitespace-nowrap sticky top-0 bg-slate-50 dark:bg-slate-700/50 z-10">卡券ID</th>
                  <th className="whitespace-nowrap sticky top-0 bg-slate-50 dark:bg-slate-700/50 z-10">卡券名称</th>
                  <th className="whitespace-nowrap sticky top-0 bg-slate-50 dark:bg-slate-700/50 z-10">规格</th>
                  <th className="whitespace-nowrap sticky top-0 bg-slate-50 dark:bg-slate-700/50 z-10">对接价格</th>
                  <th className="whitespace-nowrap sticky top-0 bg-slate-50 dark:bg-slate-700/50 z-10">最低售价</th>
                  <th className="whitespace-nowrap sticky top-0 bg-slate-50 dark:bg-slate-700/50 z-10">联系方式</th>
                  <th className="whitespace-nowrap sticky top-0 bg-slate-50 dark:bg-slate-700/50 z-10">发货次数</th>
                  <th className="whitespace-nowrap sticky top-0 bg-slate-50 dark:bg-slate-700/50 z-10">状态</th>
                  <th className="whitespace-nowrap sticky top-0 bg-slate-50 dark:bg-slate-700/50 z-10">开放对接</th>
                  <th className="whitespace-nowrap sticky top-0 bg-slate-50 dark:bg-slate-700/50 z-10">下级对接价</th>
                  <th className="whitespace-nowrap sticky top-0 bg-slate-50 dark:bg-slate-700/50 z-10">对接类型</th>
                  <th className="whitespace-nowrap sticky top-0 bg-slate-50 dark:bg-slate-700/50 z-10">备注</th>
                  <th className="whitespace-nowrap sticky top-0 bg-slate-50 dark:bg-slate-700/50 z-10">创建时间</th>
                  <th className="whitespace-nowrap sticky top-0 right-0 bg-slate-50 dark:bg-slate-700/50 z-20">操作</th>
                </tr>
              </thead>
              <tbody>
                {records.length === 0 ? (
                  <tr>
                    <td colSpan={isAdmin ? 18 : 17}>
                      <div className="empty-state py-12">
                        <PackageCheck className="empty-state-icon" />
                        <p className="text-slate-500 dark:text-slate-400">
                          {searchText ? '没有匹配的对接记录' : '暂无对接记录，请前往货源广场进行对接'}
                        </p>
                      </div>
                    </td>
                  </tr>
                ) : (
                  records.map(record => (
                    <tr key={record.id}>
                      <td className="whitespace-nowrap text-sm text-slate-500 dark:text-slate-400">{record.id}</td>
                      {isAdmin && (
                        <td className="whitespace-nowrap text-sm text-slate-600 dark:text-slate-300 max-w-[160px] truncate" title={record.owner_username || ''}>
                          {record.owner_username || '-'}
                        </td>
                      )}
                      <td className="whitespace-nowrap font-medium text-slate-900 dark:text-white">
                        {record.dock_name}
                      </td>
                      <td className="whitespace-nowrap">
                        <span className={`inline-block px-2 py-0.5 rounded text-xs font-medium ${
                          record.level === 2
                            ? 'bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-400'
                            : 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400'
                        }`}>
                          {record.level === 2 ? '二级' : '一级'}
                        </span>
                      </td>
                      <td className="whitespace-nowrap text-sm text-slate-500 dark:text-slate-400">{record.card_id}</td>
                      <td className="whitespace-nowrap text-sm text-slate-600 dark:text-slate-300 max-w-[220px] truncate" title={record.card_name || ''}>
                        {record.card_name || '-'}
                      </td>
                      <td className="whitespace-nowrap text-sm">
                        {record.is_multi_spec ? (
                          <span className="text-xs text-blue-600 dark:text-blue-400">{record.spec_name}: {record.spec_value}</span>
                        ) : (
                          <span className="text-slate-400">-</span>
                        )}
                      </td>
                      <td className="whitespace-nowrap text-sm">
                        {record.card_price ? (
                          <span className="text-slate-700 dark:text-slate-200">¥{record.card_price}</span>
                        ) : (
                          <span className="text-slate-400">-</span>
                        )}
                      </td>
                      <td className="whitespace-nowrap text-sm">
                        {record.min_price ? (
                          <span className="text-orange-600 dark:text-orange-400 font-medium">¥{record.min_price}</span>
                        ) : (
                          <span className="text-slate-400">-</span>
                        )}
                      </td>
                      <td className="whitespace-nowrap text-sm text-slate-600 dark:text-slate-300 align-top">
                        {renderContactInfo(record)}
                      </td>
                      <td className="whitespace-nowrap text-sm">
                        <span className="font-medium text-slate-700 dark:text-slate-200">
                          {record.delivery_count || 0}
                        </span>
                      </td>
                      <td className="whitespace-nowrap">
                        <div className="flex flex-col gap-0.5">
                          <button
                            onClick={() => handleToggleStatus(record)}
                            className={`inline-flex items-center gap-1.5 text-xs font-medium self-start ${
                              record.status
                                ? 'text-green-600 hover:text-green-700 dark:text-green-400'
                                : 'text-gray-400 hover:text-gray-500 dark:text-gray-500'
                            }`}
                            title="点击切换状态"
                          >
                            <span className={`status-dot ${record.status ? 'status-dot-success' : 'status-dot-danger'}`} />
                            {record.status ? '已启用' : '已停用'}
                          </button>
                          {!record.status && record.disable_reason && (
                            <span
                              className="text-[11px] text-red-500 dark:text-red-400 max-w-[160px] truncate"
                              title={record.disable_reason}
                            >
                              {record.disable_reason}
                            </span>
                          )}
                        </div>
                      </td>
                      <td className="whitespace-nowrap">
                        {record.level === 1 ? (
                          <button
                            onClick={() => handleToggleSubDock(record)}
                            className={`inline-block px-2 py-0.5 rounded text-xs font-medium cursor-pointer transition-colors ${
                              record.allow_sub_dock
                                ? 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400 hover:bg-green-200'
                                : 'bg-gray-100 text-gray-500 dark:bg-gray-800 dark:text-gray-400 hover:bg-gray-200'
                            }`}
                            title="点击切换是否允许下级对接"
                          >
                            {record.allow_sub_dock ? '已开放' : '未开放'}
                          </button>
                        ) : (
                          <span className="text-slate-400 text-xs">-</span>
                        )}
                      </td>
                      <td className="whitespace-nowrap text-sm">
                        {record.level === 1 && record.allow_sub_dock && record.sub_dock_price ? (
                          <span
                            onClick={() => handleEditSubDock(record)}
                            className="text-amber-600 dark:text-amber-400 font-medium cursor-pointer hover:underline"
                            title="点击修改下级对接设置"
                          >¥{record.sub_dock_price}</span>
                        ) : record.level === 1 && record.sub_dock_price ? (
                          <span className="text-amber-600 dark:text-amber-400 font-medium">¥{record.sub_dock_price}</span>
                        ) : (
                          <span className="text-slate-400">-</span>
                        )}
                      </td>
                      <td className="whitespace-nowrap text-sm">
                        {record.level === 1 && record.allow_sub_dock ? (
                          <span
                            onClick={() => handleEditSubDock(record)}
                            className={`inline-block px-2 py-0.5 rounded text-xs font-medium cursor-pointer hover:opacity-80 ${
                              record.sub_dock_visibility === 'dealer_only'
                                ? 'bg-orange-100 text-orange-700 dark:bg-orange-900/30 dark:text-orange-400'
                                : 'bg-cyan-100 text-cyan-700 dark:bg-cyan-900/30 dark:text-cyan-400'
                            }`}
                            title="点击修改下级对接设置"
                          >
                            {record.sub_dock_visibility === 'dealer_only' ? '仅分销商' : '所有人'}
                          </span>
                        ) : (
                          <span className="text-slate-400">-</span>
                        )}
                      </td>
                      <td className="whitespace-nowrap text-xs text-slate-500 max-w-[180px] truncate" title={record.remark || ''}>
                        {record.remark || '-'}
                      </td>
                      <td className="whitespace-nowrap text-xs text-slate-500">
                        {record.created_at ? new Date(record.created_at).toLocaleString('zh-CN') : '-'}
                      </td>
                      <td className="whitespace-nowrap sticky right-0 bg-white dark:bg-slate-900 z-10">
                        <div className="flex items-center gap-1">
                          <button
                            onClick={() => handleOpenPickup(record)}
                            className="p-1.5 rounded-lg hover:bg-emerald-50 dark:hover:bg-emerald-900/20 text-emerald-600 dark:text-emerald-400 transition-colors"
                            title="提货地址"
                          >
                            <Truck className="w-4 h-4" />
                          </button>
                          <button
                            onClick={() => { setSelectedRecord(record); setEditModalOpen(true) }}
                            className="p-1.5 rounded-lg hover:bg-blue-50 dark:hover:bg-blue-900/20 text-blue-600 dark:text-blue-400 transition-colors"
                            title="编辑"
                          >
                            <Pencil className="w-4 h-4" />
                          </button>
                          <button
                            onClick={() => setDeleteRecord(record)}
                            className="p-1.5 rounded-lg hover:bg-red-50 dark:hover:bg-red-900/20 text-red-500 dark:text-red-400 transition-colors"
                            title="删除"
                          >
                            <Trash2 className="w-4 h-4" />
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          )}
        </div>

        {/* 分页控件：固定底部 */}
        {total > 0 && (
          <div className="flex-shrink-0 flex flex-col sm:flex-row items-center justify-between px-4 py-3 border-t border-slate-200 dark:border-slate-700 gap-3">
            <div className="flex items-center gap-2 text-sm text-slate-500 dark:text-slate-400">
              <span>每页</span>
              <select
                value={pageSize}
                onChange={(e) => handlePageSizeChange(Number(e.target.value))}
                className="input-ios w-auto py-1 px-2 text-sm"
              >
                <option value={10}>10</option>
                <option value={20}>20</option>
                <option value={50}>50</option>
                <option value={100}>100</option>
              </select>
              <span>条，共 {total} 条</span>
            </div>
            <div className="flex items-center gap-2">
              <span className="text-sm text-slate-500 dark:text-slate-400">
                第 {page} / {totalPages || 1} 页
              </span>
              <button
                onClick={() => handlePageChange(page - 1)}
                disabled={page <= 1 || loading}
                className="btn-ios-secondary btn-sm"
              >
                上一页
              </button>
              <button
                onClick={() => handlePageChange(page + 1)}
                disabled={page >= totalPages || loading}
                className="btn-ios-secondary btn-sm"
              >
                下一页
              </button>
            </div>
          </div>
        )}
      </div>

      {/* 编辑弹窗 */}
      <EditDockModal
        isOpen={editModalOpen}
        onClose={() => setEditModalOpen(false)}
        onSuccess={() => loadData(page, pageSize)}
        record={selectedRecord}
      />

      {/* 开放对接价格弹窗 */}
      {priceModalOpen && priceModalRecord && (
        <div className="fixed inset-0 z-50 flex items-center justify-center">
          <div className="absolute inset-0 bg-black/50" onClick={() => setPriceModalOpen(false)} />
          <div className="relative w-full max-w-md mx-4 bg-white dark:bg-slate-800 rounded-xl shadow-2xl">
            <div className="flex items-center justify-between px-6 py-4 border-b border-slate-200 dark:border-slate-700">
              <h3 className="text-lg font-semibold text-slate-900 dark:text-white">
                {isEditMode ? '修改下级对接设置' : '开放下级对接'}
              </h3>
              <button
                onClick={() => setPriceModalOpen(false)}
                className="p-1.5 rounded-lg hover:bg-slate-100 dark:hover:bg-slate-700 transition-colors"
              >
                <X className="w-5 h-5 text-slate-500" />
              </button>
            </div>
            <div className="px-6 py-5 space-y-4">
              <div className="px-4 py-3 rounded-lg bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800">
                <p className="text-sm text-blue-700 dark:text-blue-400">
                  卡券：<strong>{priceModalRecord.card_name || priceModalRecord.dock_name}</strong>
                  {priceModalRecord.card_price && (
                    <span> · 对接价：¥{priceModalRecord.card_price}</span>
                  )}
                </p>
              </div>
              <div>
                <label className="input-label">
                  给下级的对接价格（元） <span className="text-red-500">*</span>
                </label>
                <input
                  type="text"
                  value={subDockPriceInput}
                  onChange={(e) => setSubDockPriceInput(e.target.value)}
                  className="input-ios"
                  placeholder="请输入对接价格"
                  autoFocus
                />
                <p className="text-xs text-gray-500 mt-1">
                  这是二级分销商的成本价，您的利润 = 对接价 - 您的成本价
                </p>
              </div>
              <div>
                <label className="input-label">
                  对接类型
                </label>
                <select
                  value={subDockVisibility}
                  onChange={(e) => setSubDockVisibility(e.target.value)}
                  className="input-ios"
                >
                  <option value="public">所有人可见</option>
                  <option value="dealer_only">仅分销商可见</option>
                </select>
                <p className="text-xs text-gray-500 mt-1">
                  选择“仅分销商可见”时，只有在货源管理中添加了您对接码的用户才能在分销商货源看到
                </p>
              </div>
            </div>
            <div className="flex items-center justify-end gap-3 px-6 py-4 border-t border-slate-200 dark:border-slate-700">
              <button onClick={() => setPriceModalOpen(false)} className="btn-ios-secondary">
                取消
              </button>
              <button
                onClick={handlePriceSubmit}
                disabled={priceSubmitting}
                className="btn-ios-primary"
              >
                {priceSubmitting ? (
                  <span className="flex items-center gap-2">
                    <RefreshCw className="w-4 h-4 animate-spin" />
                    提交中...
                  </span>
                ) : (
                  isEditMode ? '保存修改' : '确认开放'
                )}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* 提货地址弹窗（仅可通过按钮关闭） */}
      {pickupModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center">
          <div className="absolute inset-0 bg-black/50" />
          <div className="relative w-full max-w-lg mx-4 bg-white dark:bg-slate-800 rounded-xl shadow-2xl">
            <div className="flex items-center justify-between px-6 py-4 border-b border-slate-200 dark:border-slate-700">
              <h3 className="text-lg font-semibold text-slate-900 dark:text-white">提货地址</h3>
              <button
                onClick={() => setPickupModalOpen(false)}
                className="p-1.5 rounded-lg hover:bg-slate-100 dark:hover:bg-slate-700 transition-colors"
                title="关闭"
              >
                <X className="w-5 h-5 text-slate-500" />
              </button>
            </div>
            <div className="px-6 py-5 space-y-4">
              <div className="px-4 py-3 rounded-lg bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800">
                <p className="text-sm text-blue-700 dark:text-blue-400">
                  对接：<strong>{pickupRecord?.dock_name}</strong>
                  {pickupRecord?.card_name && <span> · 卡券：{pickupRecord.card_name}</span>}
                </p>
              </div>
              <div>
                <label className="input-label">免认证提货地址</label>
                {pickupLoading ? (
                  <div className="flex items-center gap-2 text-sm text-slate-400 py-3">
                    <RefreshCw className="w-4 h-4 animate-spin" />
                    生成中...
                  </div>
                ) : (
                  <div className="flex items-start gap-2">
                    <textarea
                      readOnly
                      value={pickupUrl}
                      rows={3}
                      className="input-ios font-mono text-xs break-all flex-1 resize-none"
                      onFocus={(e) => e.currentTarget.select()}
                    />
                    <button
                      onClick={handleCopyPickupUrl}
                      disabled={!pickupUrl}
                      className="btn-ios-secondary text-sm shrink-0"
                      title="复制地址"
                    >
                      <Copy className="w-4 h-4" />
                      复制
                    </button>
                  </div>
                )}
              </div>
              <div className="px-4 py-3 rounded-lg bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-800">
                <p className="text-xs text-amber-700 dark:text-amber-400 leading-relaxed">
                  说明：该地址无需登录即可访问，每次访问会按对接价格扣费并发放一张卡券，返回纯文本内容。
                  请妥善保管，避免泄露。每 5 秒最多提货一次。更换秘钥后旧地址将失效。
                </p>
              </div>
            </div>
            <div className="flex items-center justify-end gap-3 px-6 py-4 border-t border-slate-200 dark:border-slate-700">
              <button onClick={() => setPickupModalOpen(false)} className="btn-ios-secondary">
                关闭
              </button>
            </div>
          </div>
        </div>
      )}
      <ConfirmModal
        isOpen={!!deleteRecord}
        title="删除对接记录"
        message={`确定要删除对接记录「${deleteRecord?.dock_name || ''}」吗？`}
        confirmText="删除"
        type="danger"
        loading={deletingRecord}
        onConfirm={() => deleteRecord && handleDelete(deleteRecord).finally(() => setDeleteRecord(null))}
        onCancel={() => setDeleteRecord(null)}
      />
    </div>
  )
}
