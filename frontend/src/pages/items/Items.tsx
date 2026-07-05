import { useEffect, useState, useRef } from 'react'
import { CheckSquare, Download, Edit2, ExternalLink, Loader2, Package, PackageX, RefreshCw, Search, Square, Trash2, X, Settings, Plus, MessageSquare, Bot, ChevronLeft, ChevronRight, ImagePlus, Unlink } from 'lucide-react'
import { batchDeleteItems, batchOfflineItems, deleteItem, fetchAllItemsFromAccessibleAccounts, fetchAllItemsFromAccount, getItemsPaginated, updateItem, updateItemMultiQuantityDelivery, updateItemMultiSpec, getItemDefaultReply, saveItemDefaultReply, deleteItemDefaultReply, batchSaveItemDefaultReply, batchDeleteItemDefaultReply, getItemAiPrompt, saveItemAiPrompt, batchDeleteItemAiPrompt, batchSaveItemAiPrompt, uploadItemDefaultReplyImage, uploadBatchDefaultReplyImage, type ItemFilterParams } from '@/api/items'
import { getAccountDetails } from '@/api/accounts'
import { batchClearItemRelations } from '@/api/cards'
import { ItemCardRelationModal } from './ItemCardRelationModal'
import { useUIStore } from '@/store/uiStore'
import { PageLoading } from '@/components/common/Loading'
import { useAuthStore } from '@/store/authStore'
import { Select } from '@/components/common/Select'
import { ConfirmModal } from '@/components/common/ConfirmModal'
import type { Account, Item } from '@/types'

type ItemBooleanFilterKey = 'is_polished' | 'is_multi_spec' | 'multi_quantity_delivery'


export function Items() {
  const { addToast } = useUIStore()
  const { isAuthenticated, token, _hasHydrated } = useAuthStore()
  const [loading, setLoading] = useState(true)
  const [items, setItems] = useState<Item[]>([])
  const [accounts, setAccounts] = useState<Account[]>([])
  const [selectedAccount, setSelectedAccount] = useState('')
  const [searchKeyword, setSearchKeyword] = useState('')
  const [selectedIds, setSelectedIds] = useState<Set<string | number>>(new Set())
  const [fetchingType, setFetchingType] = useState<'single' | 'all' | null>(null)
  
  // 分页状态
  const [pagination, setPagination] = useState({
    page: 1,
    pageSize: 20,
    total: 0,
    totalPages: 0,
  })
  const [itemsLoading, setItemsLoading] = useState(false)
  
  // 筛选状态
  const [filters, setFilters] = useState<ItemFilterParams>({
    is_polished: null,
    is_multi_spec: null,
    multi_quantity_delivery: null,
  })

  // 编辑弹窗状态
  const [editingItem, setEditingItem] = useState<Item | null>(null)
  const [editDetail, setEditDetail] = useState('')
  const [editPrice, setEditPrice] = useState('')
  const [editSaving, setEditSaving] = useState(false)

  // 卡券关联选择弹窗
  const [relationItem, setRelationItem] = useState<Item | null>(null)
  
  // 图片预览弹窗状态
  const [isImagePreviewOpen, setIsImagePreviewOpen] = useState(false)
  const [previewImageUrl] = useState('')

  // 商品默认回复弹窗状态
  const [defaultReplyItem, setDefaultReplyItem] = useState<Item | null>(null)
  const [defaultReplyContent, setDefaultReplyContent] = useState('')
  const [defaultReplyImage, setDefaultReplyImage] = useState('')
  const [defaultReplyEnabled, setDefaultReplyEnabled] = useState(true)
  const [defaultReplyOnce, setDefaultReplyOnce] = useState(false)
  const [defaultReplyType, setDefaultReplyType] = useState<'text' | 'api'>('text')
  const [defaultReplyApiUrl, setDefaultReplyApiUrl] = useState('')
  const [defaultReplyApiTimeout, setDefaultReplyApiTimeout] = useState(80)
  const [loadingDefaultReply, setLoadingDefaultReply] = useState(false)
  const [savingDefaultReply, setSavingDefaultReply] = useState(false)
  const [defaultReplyImageUploading, setDefaultReplyImageUploading] = useState(false)
  const defaultReplyImageInputRef = useRef<HTMLInputElement>(null)

  // 批量新增默认回复弹窗状态
  const [showBatchDefaultReplyModal, setShowBatchDefaultReplyModal] = useState(false)
  const [batchSelectedItemIds, setBatchSelectedItemIds] = useState<string[]>([])
  const [batchReplyContent, setBatchReplyContent] = useState('')
  const [batchReplyImage, setBatchReplyImage] = useState('')
  const [batchReplyEnabled, setBatchReplyEnabled] = useState(true)
  const [batchReplyOnce, setBatchReplyOnce] = useState(false)
  const [batchReplyType, setBatchReplyType] = useState<'text' | 'api'>('text')
  const [batchReplyApiUrl, setBatchReplyApiUrl] = useState('')
  const [batchReplyApiTimeout, setBatchReplyApiTimeout] = useState(80)
  const [savingBatchReply, setSavingBatchReply] = useState(false)
  const [batchItemSearch, setBatchItemSearch] = useState('')
  const [batchReplyImageUploading, setBatchReplyImageUploading] = useState(false)
  const batchReplyImageInputRef = useRef<HTMLInputElement>(null)

  // AI提示词弹窗状态
  const [aiPromptItem, setAiPromptItem] = useState<Item | null>(null)
  const [aiPromptContent, setAiPromptContent] = useState('')
  const [loadingAiPrompt, setLoadingAiPrompt] = useState(false)
  const [savingAiPrompt, setSavingAiPrompt] = useState(false)

  // 批量新增AI提示词弹窗状态
  const [showBatchAiPromptModal, setShowBatchAiPromptModal] = useState(false)
  const [batchAiPromptSelectedItemIds, setBatchAiPromptSelectedItemIds] = useState<string[]>([])
  const [batchAiPromptContent, setBatchAiPromptContent] = useState('')
  const [savingBatchAiPrompt, setSavingBatchAiPrompt] = useState(false)
  const [batchAiPromptItemSearch, setBatchAiPromptItemSearch] = useState('')

  // 确认弹窗状态
  const [deleteItemConfirm, setDeleteItemConfirm] = useState<{ open: boolean; item: Item | null }>({ open: false, item: null })
  const [batchDeleteItemConfirm, setBatchDeleteItemConfirm] = useState(false)
  const [batchOfflineConfirm, setBatchOfflineConfirm] = useState(false)
  const [offlining, setOfflining] = useState(false)
  const [deleteDefaultReplyConfirm, setDeleteDefaultReplyConfirm] = useState(false)
  const [batchDeleteDefaultReplyConfirm, setBatchDeleteDefaultReplyConfirm] = useState(false)
  const [deleteAiPromptConfirm, setDeleteAiPromptConfirm] = useState(false)
  const [batchDeleteAiPromptConfirm, setBatchDeleteAiPromptConfirm] = useState(false)
  const [batchClearCardRelationsConfirm, setBatchClearCardRelationsConfirm] = useState(false)
  const [deleting, setDeleting] = useState(false)
  // const hasSearchEffectInitializedRef = useRef(false)  // 已改为手动查询，不再需要
  const skipNextSearchEffectRef = useRef(false)

  const loadItems = async (
    page: number = pagination.page,
    pageSize: number = pagination.pageSize,
    currentFilters: ItemFilterParams = filters,
    currentKeyword: string = searchKeyword,
  ) => {
    if (!_hasHydrated || !isAuthenticated || !token) {
      return
    }
    try {
      setItemsLoading(true)
      const trimmedKeyword = currentKeyword.trim()
      const result = await getItemsPaginated(page, pageSize, selectedAccount || undefined, {
        ...currentFilters,
        keyword: trimmedKeyword || null,
      })
      if (result.success) {
        setItems(result.data || [])
        setPagination({
          page: result.page,
          pageSize: result.page_size,
          total: result.total,
          totalPages: result.total_pages,
        })
      }
    } catch {
      addToast({ type: 'error', message: '加载商品列表失败' })
    } finally {
      setItemsLoading(false)
      setLoading(false)
    }
  }

  // 分页切换
  const handlePageChange = (newPage: number) => {
    if (newPage >= 1 && newPage <= pagination.totalPages) {
      loadItems(newPage, pagination.pageSize, filters)
    }
  }

  // 每页条数切换
  const handlePageSizeChange = (newPageSize: number) => {
    setPagination(prev => ({ ...prev, pageSize: newPageSize }))
    loadItems(1, newPageSize, filters)
  }
  
  // 筛选条件变更
  const handleFilterChange = (key: ItemBooleanFilterKey, value: boolean | null) => {
    const newFilters = { ...filters, [key]: value }
    setFilters(newFilters)
    loadItems(1, pagination.pageSize, newFilters)
  }
  
  // 重置筛选条件
  const handleResetFilters = () => {
    const emptyFilters: ItemFilterParams = {
      is_polished: null,
      is_multi_spec: null,
      multi_quantity_delivery: null,
    }
    setFilters(emptyFilters)
    skipNextSearchEffectRef.current = !!searchKeyword.trim()
    setSearchKeyword('')
    loadItems(1, pagination.pageSize, emptyFilters, '')
  }
  
  // 检查是否有筛选条件
  const hasActiveFilters = Object.values(filters).some(v => v !== null) || !!searchKeyword.trim()

  const handleFetchItems = async () => {
    if (!selectedAccount) {
      addToast({ type: 'warning', message: '请先选择账号后再获取商品' })
      return
    }

    setFetchingType('single')

    try {
      // 使用获取所有页的接口，后端会自动遍历所有页
      const result = await fetchAllItemsFromAccount(selectedAccount)

      if (result.success) {
        const totalCount = (result as { total_count?: number }).total_count || 0
        const savedCount = (result as { saved_count?: number }).saved_count || 0
        addToast({ type: 'success', message: `成功获取商品，共 ${totalCount} 件，保存 ${savedCount} 件` })
        await loadItems()
      } else {
        addToast({ type: 'error', message: result.message || '获取商品失败' })
      }
    } catch {
      addToast({ type: 'error', message: '获取商品失败' })
    } finally {
      setFetchingType(null)
    }
  }

  const handleFetchAllItems = async () => {
    setFetchingType('all')

    try {
      const result = await fetchAllItemsFromAccessibleAccounts()

      if (result.success) {
        const totalCount = result.total_count || 0
        const savedCount = result.saved_count || 0
        const accountCount = result.account_count || 0
        const successAccountCount = result.success_account_count || 0
        const failedAccountCount = result.failed_account_count || 0
        const firstFailedAccount = result.failed_accounts?.[0]
        const message = failedAccountCount > 0
          ? `已获取 ${successAccountCount}/${accountCount} 个账号商品，共 ${totalCount} 件，保存 ${savedCount} 件；失败 ${failedAccountCount} 个账号${firstFailedAccount ? `，例如：${firstFailedAccount}` : ''}`
          : `成功获取 ${accountCount} 个账号商品，共 ${totalCount} 件，保存 ${savedCount} 件`
        addToast({
          type: failedAccountCount > 0 ? 'warning' : 'success',
          message,
        })
        await loadItems()
      } else {
        addToast({ type: 'error', message: result.message || '获取所有账号商品失败' })
      }
    } catch {
      addToast({ type: 'error', message: '获取所有账号商品失败' })
    } finally {
      setFetchingType(null)
    }
  }

  const loadAccounts = async () => {
    if (!_hasHydrated || !isAuthenticated || !token) {
      return
    }
    try {
      const data = await getAccountDetails()
      setAccounts(data)
    } catch {
      // ignore
    }
  }

  useEffect(() => {
    if (!_hasHydrated || !isAuthenticated || !token) return
    loadAccounts()
  }, [_hasHydrated, isAuthenticated, token])

  useEffect(() => {
    if (!_hasHydrated || !isAuthenticated || !token) return
    loadItems(1, pagination.pageSize, filters)
  }, [_hasHydrated, isAuthenticated, token, selectedAccount])

  // 搜索关键词变更时自动触发查询（已改为手动点击查询按钮）
  // useEffect(() => {
  //   if (!hasSearchEffectInitializedRef.current) {
  //     hasSearchEffectInitializedRef.current = true
  //     return
  //   }
  //   if (!_hasHydrated || !isAuthenticated || !token) return
  //   if (skipNextSearchEffectRef.current) {
  //     skipNextSearchEffectRef.current = false
  //     return
  //   }

  //   const timer = window.setTimeout(() => {
  //     loadItems(1, pagination.pageSize, filters, searchKeyword)
  //   }, 300)

  //   return () => {
  //     window.clearTimeout(timer)
  //   }
  // }, [searchKeyword])

  const handleDelete = async (item: Item) => {
    setDeleting(true)
    try {
      await deleteItem(item.cookie_id, item.item_id)
      addToast({ type: 'success', message: '删除成功' })
      setDeleteItemConfirm({ open: false, item: null })
      loadItems()
    } catch {
      addToast({ type: 'error', message: '删除失败' })
    } finally {
      setDeleting(false)
    }
  }

  // 批量选择相关
  const toggleSelect = (id: string | number) => {
    setSelectedIds((prev) => {
      const next = new Set(prev)
      if (next.has(id)) {
        next.delete(id)
      } else {
        next.add(id)
      }
      return next
    })
  }

  const toggleSelectAll = () => {
    if (selectedIds.size === filteredItems.length) {
      setSelectedIds(new Set())
    } else {
      setSelectedIds(new Set(filteredItems.map((item) => item.id)))
    }
  }

  const handleBatchDelete = async () => {
    if (selectedIds.size === 0) {
      addToast({ type: 'warning', message: '请先选择要删除的商品' })
      return
    }
    setDeleting(true)
    try {
      // 将选中的 ID 转换为 { cookie_id, item_id } 格式
      const itemsToDelete = items
        .filter((item) => selectedIds.has(item.id))
        .map((item) => ({ cookie_id: item.cookie_id, item_id: item.item_id }))
      const result = await batchDeleteItems(itemsToDelete)
      if (result.success) {
        addToast({ type: 'success', message: result.message || `成功删除 ${selectedIds.size} 个商品` })
        setSelectedIds(new Set())
        setBatchDeleteItemConfirm(false)
        loadItems()
      } else {
        setBatchDeleteItemConfirm(false)
        addToast({ type: 'error', message: result.message || '删除失败' })
      }
    } catch {
      setBatchDeleteItemConfirm(false)
      addToast({ type: 'error', message: '批量删除失败' })
    } finally {
      setDeleting(false)
    }
  }

  // ==================== 批量下架 ====================

  // 打开批量下架确认框（账号下拉复用顶部「筛选账号」，必须选具体账号）
  const openBatchOffline = () => {
    if (selectedIds.size === 0) {
      addToast({ type: 'warning', message: '请先选择要下架的商品' })
      return
    }
    if (!selectedAccount) {
      addToast({ type: 'warning', message: '请先在顶部「筛选账号」选择具体账号后再下架' })
      return
    }
    setBatchOfflineConfirm(true)
  }

  // 执行批量下架（调用闲鱼接口，使用所选账号的Cookie）
  const handleBatchOffline = async () => {
    const itemIds = items
      .filter((item) => selectedIds.has(item.id))
      .map((item) => item.item_id)
    if (itemIds.length === 0) {
      addToast({ type: 'warning', message: '未找到选中的商品' })
      setBatchOfflineConfirm(false)
      return
    }
    setOfflining(true)
    try {
      const result = await batchOfflineItems(selectedAccount, itemIds)
      const data = result.data as
        | { results?: { item_id: string; success: boolean }[]; fail_count?: number }
        | undefined
      const failCount = data?.fail_count ?? 0
      if (result.success) {
        if (failCount > 0) {
          // 部分成功：用 warning 提示，并列出失败的商品ID（最多展示5个）
          const failedIds = (data?.results || []).filter((r) => !r.success).map((r) => r.item_id)
          const preview = failedIds.slice(0, 5).join('、')
          const suffix = failedIds.length > 5 ? ` 等 ${failedIds.length} 个` : ''
          addToast({
            type: 'warning',
            message: `${result.message || '下架完成'}${preview ? `；失败商品：${preview}${suffix}` : ''}`,
          })
        } else {
          addToast({ type: 'success', message: result.message || '下架成功' })
        }
        setSelectedIds(new Set())
        setBatchOfflineConfirm(false)
        loadItems()
      } else {
        setBatchOfflineConfirm(false)
        addToast({ type: 'error', message: result.message || '下架失败' })
      }
    } catch {
      setBatchOfflineConfirm(false)
      addToast({ type: 'error', message: '批量下架失败' })
    } finally {
      setOfflining(false)
    }
  }

  // 切换多数量发货状态
  const handleToggleMultiQuantity = async (item: Item) => {
    try {
      const newStatus = !item.multi_quantity_delivery
      await updateItemMultiQuantityDelivery(item.cookie_id, item.item_id, newStatus)
      addToast({ type: 'success', message: `多数量发货已${newStatus ? '开启' : '关闭'}` })
      loadItems()
    } catch {
      addToast({ type: 'error', message: '操作失败' })
    }
  }

  // 切换多规格状态
  const handleToggleMultiSpec = async (item: Item) => {
    try {
      const newStatus = !(item.is_multi_spec || item.has_sku)
      await updateItemMultiSpec(item.cookie_id, item.item_id, newStatus)
      addToast({ type: 'success', message: `多规格已${newStatus ? '开启' : '关闭'}` })
      loadItems()
    } catch {
      addToast({ type: 'error', message: '操作失败' })
    }
  }

  // 打开编辑弹窗
  const handleEdit = (item: Item) => {
    setEditingItem(item)
    setEditDetail(item.item_detail || item.desc || '')
    setEditPrice(item.item_price || item.price || '')
  }

  // 保存编辑
  const handleSaveEdit = async () => {
    if (!editingItem) return
    setEditSaving(true)
    try {
      await updateItem(editingItem.cookie_id, editingItem.item_id, {
        item_detail: editDetail,
        price: editPrice,
      })
      addToast({ type: 'success', message: '商品信息已更新' })
      setEditingItem(null)
      loadItems()
    } catch {
      addToast({ type: 'error', message: '更新失败' })
    } finally {
      setEditSaving(false)
    }
  }

  // 打开卡券关联选择弹窗
  const handleOpenDeliveryConfig = (item: Item) => {
    setRelationItem(item)
  }


  // ==================== 商品默认回复 ====================
  
  // 打开默认回复配置弹窗
  const handleOpenDefaultReply = async (item: Item) => {
    setDefaultReplyItem(item)
    setDefaultReplyImage('')
    setLoadingDefaultReply(true)
    try {
      const result = await getItemDefaultReply(item.cookie_id, item.item_id)
      if (result.success && result.data) {
        setDefaultReplyContent(result.data.reply_content || '')
        setDefaultReplyImage(result.data.reply_image || '')
        setDefaultReplyEnabled(result.data.enabled ?? true)
        setDefaultReplyOnce(result.data.reply_once ?? false)
        setDefaultReplyType((result.data.reply_type as 'text' | 'api') || 'text')
        setDefaultReplyApiUrl(result.data.api_url || '')
        setDefaultReplyApiTimeout(result.data.api_timeout || 80)
      } else {
        setDefaultReplyContent('')
        setDefaultReplyImage('')
        setDefaultReplyEnabled(true)
        setDefaultReplyOnce(false)
        setDefaultReplyType('text')
        setDefaultReplyApiUrl('')
        setDefaultReplyApiTimeout(80)
      }
    } catch {
      setDefaultReplyContent('')
      setDefaultReplyImage('')
      setDefaultReplyEnabled(true)
      setDefaultReplyOnce(false)
      setDefaultReplyType('text')
      setDefaultReplyApiUrl('')
      setDefaultReplyApiTimeout(80)
    } finally {
      setLoadingDefaultReply(false)
    }
  }

  // 关闭默认回复配置弹窗
  const closeDefaultReply = () => {
    setDefaultReplyItem(null)
    setDefaultReplyContent('')
    setDefaultReplyImage('')
    setDefaultReplyEnabled(true)
    setDefaultReplyOnce(false)
    setDefaultReplyType('text')
    setDefaultReplyApiUrl('')
    setDefaultReplyApiTimeout(80)
  }

  // 保存默认回复配置
  const handleSaveDefaultReply = async () => {
    if (!defaultReplyItem) return
    if (defaultReplyType === 'api' && !defaultReplyApiUrl.trim()) {
      addToast({ type: 'warning', message: '请输入 API 地址' })
      return
    }
    setSavingDefaultReply(true)
    try {
      const result = await saveItemDefaultReply(
        defaultReplyItem.cookie_id,
        defaultReplyItem.item_id,
        {
          reply_content: defaultReplyContent,
          reply_image: defaultReplyImage,
          enabled: defaultReplyEnabled,
          reply_once: defaultReplyOnce,
          reply_type: defaultReplyType,
          api_url: defaultReplyApiUrl,
          api_timeout: defaultReplyApiTimeout,
        }
      )
      if (result.success) {
        addToast({ type: 'success', message: '商品默认回复已保存' })
        closeDefaultReply()
        loadItems() // 刷新商品列表
      } else {
        addToast({ type: 'error', message: result.message || '保存失败' })
      }
    } catch {
      addToast({ type: 'error', message: '保存失败' })
    } finally {
      setSavingDefaultReply(false)
    }
  }

  // 上传商品默认回复图片
  const handleDefaultReplyImageUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file || !defaultReplyItem) return
    
    if (!file.type.startsWith('image/')) {
      addToast({ type: 'error', message: '只支持上传图片文件' })
      return
    }
    
    if (file.size > 5 * 1024 * 1024) {
      addToast({ type: 'error', message: '图片大小不能超过5MB' })
      return
    }
    
    try {
      setDefaultReplyImageUploading(true)
      const result = await uploadItemDefaultReplyImage(defaultReplyItem.cookie_id, defaultReplyItem.item_id, file)
      if (result.success && result.image_url) {
        setDefaultReplyImage(result.image_url)
        addToast({ type: 'success', message: '图片上传成功' })
      } else {
        addToast({ type: 'error', message: result.message || '图片上传失败' })
      }
    } catch {
      addToast({ type: 'error', message: '图片上传失败' })
    } finally {
      setDefaultReplyImageUploading(false)
      if (defaultReplyImageInputRef.current) {
        defaultReplyImageInputRef.current.value = ''
      }
    }
  }

  // 删除默认回复配置
  const handleDeleteDefaultReply = async () => {
    if (!defaultReplyItem) return
    setSavingDefaultReply(true)
    try {
      const result = await deleteItemDefaultReply(defaultReplyItem.cookie_id, defaultReplyItem.item_id)
      if (result.success) {
        addToast({ type: 'success', message: '商品默认回复已删除' })
        setDeleteDefaultReplyConfirm(false)
        closeDefaultReply()
        loadItems() // 刷新商品列表
      } else {
        addToast({ type: 'error', message: result.message || '删除失败' })
      }
    } catch {
      addToast({ type: 'error', message: '删除失败' })
    } finally {
      setSavingDefaultReply(false)
    }
  }

  // ==================== 批量新增默认回复 ====================

  // 打开批量新增默认回复弹窗
  const openBatchDefaultReplyModal = () => {
    if (!selectedAccount) {
      addToast({ type: 'warning', message: '请先选择账号' })
      return
    }
    setBatchSelectedItemIds([])
    setBatchReplyContent('')
    setBatchReplyImage('')
    setBatchReplyEnabled(true)
    setBatchReplyOnce(false)
    setBatchReplyType('text')
    setBatchReplyApiUrl('')
    setBatchReplyApiTimeout(80)
    setShowBatchDefaultReplyModal(true)
  }

  // 关闭批量新增默认回复弹窗
  const closeBatchDefaultReplyModal = () => {
    setShowBatchDefaultReplyModal(false)
    setBatchSelectedItemIds([])
    setBatchReplyContent('')
    setBatchReplyImage('')
    setBatchReplyEnabled(true)
    setBatchReplyOnce(false)
    setBatchReplyType('text')
    setBatchReplyApiUrl('')
    setBatchReplyApiTimeout(80)
    setBatchItemSearch('')
  }

  // 切换商品选择
  const toggleBatchItemSelect = (itemId: string) => {
    setBatchSelectedItemIds((prev) => {
      if (prev.includes(itemId)) {
        return prev.filter((id) => id !== itemId)
      } else {
        return [...prev, itemId]
      }
    })
  }

  // 全选/取消全选
  const toggleBatchSelectAll = () => {
    const currentAccountItems = filteredItems.filter((item) => item.cookie_id === selectedAccount)
    if (batchSelectedItemIds.length === currentAccountItems.length) {
      setBatchSelectedItemIds([])
    } else {
      setBatchSelectedItemIds(currentAccountItems.map((item) => item.item_id))
    }
  }

  // 保存批量默认回复
  const handleSaveBatchDefaultReply = async () => {
    if (!selectedAccount) {
      addToast({ type: 'warning', message: '请先选择账号' })
      return
    }
    if (batchSelectedItemIds.length === 0) {
      addToast({ type: 'warning', message: '请选择至少一个商品' })
      return
    }
    if (batchReplyType === 'api') {
      if (!batchReplyApiUrl.trim()) {
        addToast({ type: 'warning', message: '请输入 API 地址' })
        return
      }
    } else if (!batchReplyContent.trim() && !batchReplyImage.trim()) {
      addToast({ type: 'warning', message: '请输入回复内容或上传图片' })
      return
    }

    setSavingBatchReply(true)
    try {
      const result = await batchSaveItemDefaultReply(selectedAccount, {
        item_ids: batchSelectedItemIds,
        reply_content: batchReplyContent,
        reply_image: batchReplyImage,
        enabled: batchReplyEnabled,
        reply_once: batchReplyOnce,
        reply_type: batchReplyType,
        api_url: batchReplyApiUrl,
        api_timeout: batchReplyApiTimeout,
      })
      if (result.success) {
        addToast({ type: 'success', message: result.message || '批量保存成功' })
        closeBatchDefaultReplyModal()
        loadItems()
      } else {
        addToast({ type: 'error', message: result.message || '保存失败' })
      }
    } catch {
      addToast({ type: 'error', message: '保存失败' })
    } finally {
      setSavingBatchReply(false)
    }
  }

  // 上传批量默认回复图片
  const handleBatchReplyImageUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file || !selectedAccount) return
    
    if (!file.type.startsWith('image/')) {
      addToast({ type: 'error', message: '只支持上传图片文件' })
      return
    }
    
    if (file.size > 5 * 1024 * 1024) {
      addToast({ type: 'error', message: '图片大小不能超过5MB' })
      return
    }
    
    try {
      setBatchReplyImageUploading(true)
      const result = await uploadBatchDefaultReplyImage(selectedAccount, file)
      if (result.success && result.image_url) {
        setBatchReplyImage(result.image_url)
        addToast({ type: 'success', message: '图片上传成功' })
      } else {
        addToast({ type: 'error', message: result.message || '图片上传失败' })
      }
    } catch {
      addToast({ type: 'error', message: '图片上传失败' })
    } finally {
      setBatchReplyImageUploading(false)
      if (batchReplyImageInputRef.current) {
        batchReplyImageInputRef.current.value = ''
      }
    }
  }

  // 批量删除默认回复
  const handleBatchDeleteDefaultReply = async () => {
    if (!selectedAccount) {
      addToast({ type: 'warning', message: '请先选择账号' })
      return
    }
    if (selectedIds.size === 0) {
      addToast({ type: 'warning', message: '请先选择要删除默认回复的商品' })
      return
    }
    
    // 获取选中商品的item_id
    const selectedItemIds = items
      .filter((item) => selectedIds.has(item.id) && item.cookie_id === selectedAccount)
      .map((item) => item.item_id)
    
    if (selectedItemIds.length === 0) {
      addToast({ type: 'warning', message: '请选择当前账号下的商品' })
      return
    }

    setDeleting(true)
    try {
      const result = await batchDeleteItemDefaultReply(selectedAccount, selectedItemIds)
      if (result.success) {
        addToast({ type: 'success', message: result.message || '批量删除成功' })
        setSelectedIds(new Set())
        setBatchDeleteDefaultReplyConfirm(false)
        loadItems()
      } else {
        addToast({ type: 'error', message: result.message || '删除失败' })
      }
    } catch {
      addToast({ type: 'error', message: '删除失败' })
    } finally {
      setDeleting(false)
    }
  }

  // ==================== AI提示词 ====================

  // 打开AI提示词配置弹窗
  const handleOpenAiPrompt = async (item: Item) => {
    setAiPromptItem(item)
    setLoadingAiPrompt(true)
    try {
      const result = await getItemAiPrompt(item.cookie_id, item.item_id)
      if (result.success && result.data) {
        setAiPromptContent(result.data.ai_prompt || '')
      } else {
        setAiPromptContent('')
      }
    } catch {
      setAiPromptContent('')
    } finally {
      setLoadingAiPrompt(false)
    }
  }

  // 关闭AI提示词配置弹窗
  const closeAiPrompt = () => {
    setAiPromptItem(null)
    setAiPromptContent('')
  }

  // 保存AI提示词配置
  const handleSaveAiPrompt = async () => {
    if (!aiPromptItem) return
    setSavingAiPrompt(true)
    try {
      const result = await saveItemAiPrompt(
        aiPromptItem.cookie_id,
        aiPromptItem.item_id,
        aiPromptContent
      )
      if (result.success) {
        addToast({ type: 'success', message: '商品AI提示词已保存' })
        closeAiPrompt()
        loadItems()
      } else {
        addToast({ type: 'error', message: result.message || '保存失败' })
      }
    } catch {
      addToast({ type: 'error', message: '保存失败' })
    } finally {
      setSavingAiPrompt(false)
    }
  }

  // 删除AI提示词配置
  const handleDeleteAiPrompt = async () => {
    if (!aiPromptItem) return
    setSavingAiPrompt(true)
    try {
      const result = await saveItemAiPrompt(
        aiPromptItem.cookie_id,
        aiPromptItem.item_id,
        ''
      )
      if (result.success) {
        addToast({ type: 'success', message: '商品AI提示词已删除' })
        setDeleteAiPromptConfirm(false)
        closeAiPrompt()
        loadItems()
      } else {
        addToast({ type: 'error', message: result.message || '删除失败' })
      }
    } catch {
      addToast({ type: 'error', message: '删除失败' })
    } finally {
      setSavingAiPrompt(false)
    }
  }

  // 批量删除AI提示词
  const handleBatchDeleteAiPrompt = async () => {
    if (!selectedAccount) {
      addToast({ type: 'warning', message: '请先选择账号' })
      return
    }
    if (selectedIds.size === 0) {
      addToast({ type: 'warning', message: '请先选择要删除AI提示词的商品' })
      return
    }

    // 获取选中商品的item_id
    const selectedItemIds = items
      .filter((item) => selectedIds.has(item.id) && item.cookie_id === selectedAccount)
      .map((item) => item.item_id)

    if (selectedItemIds.length === 0) {
      addToast({ type: 'warning', message: '请选择当前账号下的商品' })
      return
    }

    setDeleting(true)
    try {
      const result = await batchDeleteItemAiPrompt(selectedAccount, selectedItemIds)
      if (result.success) {
        addToast({ type: 'success', message: result.message || '批量删除成功' })
        setSelectedIds(new Set())
        setBatchDeleteAiPromptConfirm(false)
        loadItems()
      } else {
        addToast({ type: 'error', message: result.message || '删除失败' })
      }
    } catch {
      addToast({ type: 'error', message: '删除失败' })
    } finally {
      setDeleting(false)
    }
  }

  // ==================== 批量清空关联卡券 ====================

  const handleBatchClearCardRelations = async () => {
    if (selectedIds.size === 0) {
      addToast({ type: 'warning', message: '请先选择要清空关联卡券的商品' })
      return
    }

    // 获取选中商品的item_id
    const selectedItemIds = items
      .filter((item) => selectedIds.has(item.id))
      .map((item) => item.item_id)

    if (selectedItemIds.length === 0) {
      addToast({ type: 'warning', message: '未找到选中的商品' })
      return
    }

    setDeleting(true)
    try {
      const result = await batchClearItemRelations(selectedItemIds)
      if (result.success) {
        addToast({ type: 'success', message: result.message || '清空关联卡券成功' })
        setSelectedIds(new Set())
        setBatchClearCardRelationsConfirm(false)
        loadItems()
      } else {
        addToast({ type: 'error', message: result.message || '清空失败' })
      }
    } catch {
      addToast({ type: 'error', message: '清空关联卡券失败' })
    } finally {
      setDeleting(false)
    }
  }

  // ==================== 批量新增AI提示词 ====================

  // 打开批量新增AI提示词弹窗
  const openBatchAiPromptModal = () => {
    if (!selectedAccount) {
      addToast({ type: 'warning', message: '请先选择账号' })
      return
    }
    setBatchAiPromptSelectedItemIds([])
    setBatchAiPromptContent('')
    setBatchAiPromptItemSearch('')
    setShowBatchAiPromptModal(true)
  }

  // 关闭批量新增AI提示词弹窗
  const closeBatchAiPromptModal = () => {
    setShowBatchAiPromptModal(false)
    setBatchAiPromptSelectedItemIds([])
    setBatchAiPromptContent('')
    setBatchAiPromptItemSearch('')
  }

  // 切换商品选择（AI提示词）
  const toggleBatchAiPromptItemSelect = (itemId: string) => {
    setBatchAiPromptSelectedItemIds((prev) => {
      if (prev.includes(itemId)) {
        return prev.filter((id) => id !== itemId)
      } else {
        return [...prev, itemId]
      }
    })
  }

  // 全选/取消全选（AI提示词）
  const toggleBatchAiPromptSelectAll = () => {
    const currentAccountItems = filteredItems.filter((item) => item.cookie_id === selectedAccount)
    const filteredBySearch = currentAccountItems.filter((item) => {
      if (!batchAiPromptItemSearch) return true
      const search = batchAiPromptItemSearch.toLowerCase()
      const title = (item.item_title || item.title || '').toLowerCase()
      return title.includes(search) || item.item_id.includes(search)
    })
    if (batchAiPromptSelectedItemIds.length === filteredBySearch.length) {
      setBatchAiPromptSelectedItemIds([])
    } else {
      setBatchAiPromptSelectedItemIds(filteredBySearch.map((item) => item.item_id))
    }
  }

  // 保存批量AI提示词
  const handleSaveBatchAiPrompt = async () => {
    if (!selectedAccount) {
      addToast({ type: 'warning', message: '请先选择账号' })
      return
    }
    if (batchAiPromptSelectedItemIds.length === 0) {
      addToast({ type: 'warning', message: '请选择至少一个商品' })
      return
    }
    if (!batchAiPromptContent.trim()) {
      addToast({ type: 'warning', message: '请输入AI提示词内容' })
      return
    }

    setSavingBatchAiPrompt(true)
    try {
      const result = await batchSaveItemAiPrompt(selectedAccount, {
        item_ids: batchAiPromptSelectedItemIds,
        ai_prompt: batchAiPromptContent,
      })
      if (result.success) {
        addToast({ type: 'success', message: result.message || '批量保存成功' })
        closeBatchAiPromptModal()
        loadItems()
      } else {
        addToast({ type: 'error', message: result.message || '保存失败' })
      }
    } catch {
      addToast({ type: 'error', message: '保存失败' })
    } finally {
      setSavingBatchAiPrompt(false)
    }
  }

  // ==================== 批量发货配置 ====================

  const filteredItems = items

  if (loading) {
    return <PageLoading />
  }

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="page-header flex-between flex-wrap gap-4">
        <div>
          <h1 className="page-title">商品管理</h1>
          <p className="page-description">管理各账号的商品信息</p>
        </div>
        <div className="flex flex-wrap gap-2">
          {selectedIds.size > 0 && (
            <>
              <button onClick={() => setBatchDeleteItemConfirm(true)} className="btn-ios-danger">
                <Trash2 className="w-4 h-4" />
                删除选中 ({selectedIds.size})
              </button>
              <button onClick={openBatchOffline} className="btn-ios-secondary">
                <PackageX className="w-4 h-4" />
                下架选中 ({selectedIds.size})
              </button>
              <button onClick={() => setBatchDeleteDefaultReplyConfirm(true)} className="btn-ios-secondary">
                <Trash2 className="w-4 h-4" />
                删除默认回复
              </button>
              <button onClick={() => setBatchDeleteAiPromptConfirm(true)} className="btn-ios-secondary">
                <Trash2 className="w-4 h-4" />
                删除AI提示词
              </button>
              <button onClick={() => setBatchClearCardRelationsConfirm(true)} className="btn-ios-secondary">
                <Unlink className="w-4 h-4" />
                清空关联卡券
              </button>
            </>
          )}
          <button
            onClick={openBatchDefaultReplyModal}
            className="btn-ios-primary"
          >
            <Plus className="w-4 h-4" />
            新增默认回复
          </button>
          <button
            onClick={openBatchAiPromptModal}
            className="btn-ios-primary"
          >
            <Plus className="w-4 h-4" />
            新增AI提示词
          </button>
          <button
            onClick={handleFetchAllItems}
            disabled={fetchingType !== null}
            className="btn-ios-primary"
          >
            {fetchingType === 'all' ? (
              <>
                <Loader2 className="w-4 h-4 animate-spin" />
                获取全部中...
              </>
            ) : (
              <>
                <Download className="w-4 h-4" />
                获取所有账号商品
              </>
            )}
          </button>
          <button
            onClick={handleFetchItems}
            disabled={fetchingType !== null}
            className="btn-ios-primary"
          >
            {fetchingType === 'single' ? (
              <>
                <Loader2 className="w-4 h-4 animate-spin" />
                获取中...
              </>
            ) : (
              <>
                <Download className="w-4 h-4" />
                获取商品
              </>
            )}
          </button>
          <button onClick={() => loadItems()} className="btn-ios-secondary">
            <RefreshCw className="w-4 h-4" />
            刷新
          </button>
        </div>
      </div>

      {/* Filters */}
      <div className="vben-card">
        <div className="vben-card-body">
          <div className="flex flex-wrap items-end gap-4">
            <div className="input-group min-w-[200px]">
              <label className="input-label">筛选账号</label>
              <Select
                value={selectedAccount}
                onChange={setSelectedAccount}
                options={[
                  { value: '', label: '所有账号', key: 'all' },
                  ...accounts.map((account) => ({
                    value: account.id,
                    label: account.note ? `${account.id} (${account.note})` : account.id,
                    key: account.pk?.toString() || account.id,
                  })),
                ]}
                placeholder="所有账号"
              />
            </div>
            <div className="input-group min-w-[240px] flex-1">
              <label className="input-label">搜索商品</label>
              <div className="relative">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
                <input
                  type="text"
                  value={searchKeyword}
                  onChange={(e) => setSearchKeyword(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') {
                      loadItems(1, pagination.pageSize, filters, searchKeyword)
                    }
                  }}
                  placeholder="搜索商品ID、标题或详情..."
                  className="input-ios pl-9"
                />
              </div>
            </div>
            <div className="input-group min-w-[140px]">
              <label className="input-label">是否擦亮</label>
              <select
                value={filters.is_polished === null ? '' : String(filters.is_polished)}
                onChange={(e) => handleFilterChange('is_polished', e.target.value === '' ? null : e.target.value === 'true')}
                className="input-ios"
              >
                <option value="">全部</option>
                <option value="true">已擦亮</option>
                <option value="false">未擦亮</option>
              </select>
            </div>
            <div className="input-group min-w-[140px]">
              <label className="input-label">多规格</label>
              <select
                value={filters.is_multi_spec === null ? '' : String(filters.is_multi_spec)}
                onChange={(e) => handleFilterChange('is_multi_spec', e.target.value === '' ? null : e.target.value === 'true')}
                className="input-ios"
              >
                <option value="">全部</option>
                <option value="true">开启</option>
                <option value="false">关闭</option>
              </select>
            </div>
            <div className="input-group min-w-[140px]">
              <label className="input-label">多数量发货</label>
              <select
                value={filters.multi_quantity_delivery === null ? '' : String(filters.multi_quantity_delivery)}
                onChange={(e) => handleFilterChange('multi_quantity_delivery', e.target.value === '' ? null : e.target.value === 'true')}
                className="input-ios"
              >
                <option value="">全部</option>
                <option value="true">开启</option>
                <option value="false">关闭</option>
              </select>
            </div>
            {/* 查询/重置按钮统一放在筛选行最右侧 */}
            <div className="flex items-end gap-2 ml-auto">
              <button
                onClick={() => loadItems(1, pagination.pageSize, filters, searchKeyword)}
                className="btn-ios-primary whitespace-nowrap"
                disabled={itemsLoading}
              >
                <Search className="w-4 h-4" />
                查询
              </button>
              {hasActiveFilters && (
                <button onClick={handleResetFilters} className="btn-ios-secondary text-red-500 whitespace-nowrap">
                  重置筛选
                </button>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Items List */}
      <div className="vben-card flex flex-col" style={{ height: 'calc(100vh - 320px)', minHeight: '400px' }}>
        <div className="vben-card-header flex-shrink-0">
          <h2 className="vben-card-title ">
            <Package className="w-4 h-4" />
            商品列表
          </h2>
          <span className="badge-primary">{pagination.total} 个商品</span>
        </div>
        <div className="flex-1 overflow-x-auto overflow-y-auto">
          {itemsLoading ? (
            <div className="flex justify-center py-8">
              <RefreshCw className="w-6 h-6 animate-spin text-blue-500" />
            </div>
          ) : (
            <table className="table-ios">
              <thead className="sticky top-0 bg-white dark:bg-slate-800 z-10">
                <tr>
                  <th className="w-10">
                    <button
                      onClick={toggleSelectAll}
                      className="p-1 hover:bg-gray-100 rounded"
                      title={selectedIds.size === filteredItems.length ? '取消全选' : '全选'}
                    >
                      {selectedIds.size === filteredItems.length && filteredItems.length > 0 ? (
                        <CheckSquare className="w-4 h-4 text-blue-600 dark:text-blue-400" />
                      ) : (
                        <Square className="w-4 h-4 text-gray-400" />
                      )}
                    </button>
                  </th>
                  <th className="min-w-[150px]">账号ID</th>
                  <th className="min-w-[160px]">商品ID</th>
                  <th className="min-w-[260px]">商品标题</th>
                  <th className="min-w-[80px]">价格</th>
                  <th className="min-w-[100px] text-center">是否擦亮</th>
                  <th className="min-w-[100px] text-center">多规格</th>
                  <th className="min-w-[120px] text-center">多数量发货</th>
                  <th className="min-w-[110px] text-center">关联卡券</th>
                  <th className="min-w-[110px] text-center">默认回复</th>
                  <th className="min-w-[110px] text-center">AI提示词</th>
                  <th className="min-w-[170px]">创建时间</th>
                  <th className="min-w-[170px]">更新时间</th>
                  <th className="sticky right-0 bg-slate-50 dark:bg-slate-800 min-w-[70px]">操作</th>
              </tr>
            </thead>
            <tbody>
              {filteredItems.length === 0 ? (
                <tr>
                  <td colSpan={14}>
                    <div className="empty-state py-8">
                      <Package className="empty-state-icon" />
                      <p className="text-gray-500">暂无商品数据</p>
                    </div>
                  </td>
                </tr>
              ) : (
                filteredItems.map((item) => (
                  <tr key={item.id} className={selectedIds.has(item.id) ? 'bg-blue-50' : ''}>
                    <td>
                      <button
                        onClick={() => toggleSelect(item.id)}
                        className="p-1 hover:bg-gray-100 rounded"
                      >
                        {selectedIds.has(item.id) ? (
                          <CheckSquare className="w-4 h-4 text-blue-600 dark:text-blue-400" />
                        ) : (
                          <Square className="w-4 h-4 text-gray-400" />
                        )}
                      </button>
                    </td>
                    <td className="font-medium text-blue-600 dark:text-blue-400">
                      {(() => {
                        const account = accounts.find(acc => acc.id === item.cookie_id)
                        return account?.note ? `${item.cookie_id} (${account.note})` : item.cookie_id
                      })()}
                    </td>
                    <td className="text-xs text-gray-500">
                      <a
                        href={`https://www.goofish.com/item?id=${item.item_id}`}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="hover:text-blue-500 flex items-center gap-1"
                      >
                        {item.item_id}
                        <ExternalLink className="w-3 h-3" />
                      </a>
                    </td>
                    <td className="max-w-[280px]">
                      <div
                        className="font-medium line-clamp-2 cursor-help"
                        title={item.item_title || item.title || '-'}
                      >
                        {item.item_title || item.title || '-'}
                      </div>
                      {(item.item_detail || item.desc) && (
                        <div
                          className="text-xs text-gray-400 line-clamp-1 mt-0.5 cursor-help"
                          title={item.item_detail || item.desc}
                        >
                          {item.item_detail || item.desc}
                        </div>
                      )}
                    </td>
                    <td className="text-amber-600 font-medium">
                      {item.item_price || (item.price ? `¥${item.price}` : '-')}
                    </td>
                    <td>
                      <span
                        className={`px-2 py-1 rounded text-xs font-medium ${
                          item.is_polished
                            ? 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400'
                            : 'bg-gray-100 text-gray-500 dark:bg-gray-800 dark:text-gray-400'
                        }`}
                      >
                        {item.is_polished ? '已擦亮' : '未擦亮'}
                      </span>
                    </td>
                    <td>
                      <button
                        onClick={() => handleToggleMultiSpec(item)}
                        className={`px-2 py-1 rounded text-xs font-medium transition-colors ${
                          (item.is_multi_spec || item.has_sku)
                            ? 'bg-green-100 text-green-700 hover:bg-green-200 dark:bg-green-900/30 dark:text-green-400'
                            : 'bg-gray-100 text-gray-500 hover:bg-gray-200 dark:bg-gray-800 dark:text-gray-400'
                        }`}
                        title={(item.is_multi_spec || item.has_sku) ? '点击关闭多规格' : '点击开启多规格'}
                      >
                        {(item.is_multi_spec || item.has_sku) ? '已开启' : '已关闭'}
                      </button>
                    </td>
                    <td>
                      <button
                        onClick={() => handleToggleMultiQuantity(item)}
                        className={`px-2 py-1 rounded text-xs font-medium transition-colors ${
                          item.multi_quantity_delivery
                            ? 'bg-green-100 text-green-700 hover:bg-green-200 dark:bg-green-900/30 dark:text-green-400'
                            : 'bg-gray-100 text-gray-500 hover:bg-gray-200 dark:bg-gray-800 dark:text-gray-400'
                        }`}
                        title={item.multi_quantity_delivery ? '点击关闭多数量发货' : '点击开启多数量发货'}
                      >
                        {item.multi_quantity_delivery ? '已开启' : '已关闭'}
                      </button>
                    </td>
                    <td>
                      <button
                        onClick={() => handleOpenDeliveryConfig(item)}
                        className={`px-2 py-1 rounded text-xs font-medium transition-colors flex items-center gap-1 ${
                          item.has_card
                            ? 'bg-green-100 text-green-700 hover:bg-green-200 dark:bg-green-900/30 dark:text-green-400'
                            : 'bg-gray-100 text-gray-500 hover:bg-gray-200 dark:bg-gray-800 dark:text-gray-400'
                        }`}
                        title={item.has_card ? '已关联卡券' : '点击查看关联卡券'}
                      >
                        <Settings className="w-3 h-3" />
                        {item.has_card ? '已配置' : '未配置'}
                      </button>
                    </td>
                    <td>
                      <button
                        onClick={() => handleOpenDefaultReply(item)}
                        className={`px-2 py-1 rounded text-xs font-medium transition-colors flex items-center gap-1 ${
                          item.has_default_reply && item.default_reply_enabled
                            ? 'bg-green-100 text-green-700 hover:bg-green-200 dark:bg-green-900/30 dark:text-green-400'
                            : item.has_default_reply
                            ? 'bg-yellow-100 text-yellow-700 hover:bg-yellow-200 dark:bg-yellow-900/30 dark:text-yellow-400'
                            : 'bg-gray-100 text-gray-500 hover:bg-gray-200 dark:bg-gray-800 dark:text-gray-400'
                        }`}
                        title={item.has_default_reply ? (item.default_reply_enabled ? '已开启默认回复' : '已配置但未启用') : '点击配置默认回复'}
                      >
                        <MessageSquare className="w-3 h-3" />
                        {item.has_default_reply ? (item.default_reply_enabled ? '已配置' : '已关闭') : '未配置'}
                      </button>
                    </td>
                    <td>
                      <button
                        onClick={() => handleOpenAiPrompt(item)}
                        className={`px-2 py-1 rounded text-xs font-medium transition-colors flex items-center gap-1 ${
                          item.has_ai_prompt
                            ? 'bg-green-100 text-green-700 hover:bg-green-200 dark:bg-green-900/30 dark:text-green-400'
                            : 'bg-gray-100 text-gray-500 hover:bg-gray-200 dark:bg-gray-800 dark:text-gray-400'
                        }`}
                        title={item.has_ai_prompt ? '已配置AI提示词' : '点击配置AI提示词'}
                      >
                        <Bot className="w-3 h-3" />
                        {item.has_ai_prompt ? '已配置' : '未配置'}
                      </button>
                    </td>
                    <td className="text-gray-500 text-xs">
                      {item.created_at ? new Date(item.created_at).toLocaleString() : '-'}
                    </td>
                    <td className="text-gray-500 text-xs">
                      {item.updated_at ? new Date(item.updated_at).toLocaleString() : '-'}
                    </td>
                    <td className="sticky right-0 bg-white dark:bg-slate-900">
                      <div className="flex gap-1">
                        <button
                          onClick={() => handleEdit(item)}
                          className="table-action-btn hover:!bg-blue-50"
                          title="编辑"
                        >
                          <Edit2 className="w-4 h-4 text-blue-500" />
                        </button>
                        <button
                          onClick={() => setDeleteItemConfirm({ open: true, item })}
                          className="table-action-btn hover:!bg-red-50"
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
          )}
        </div>
        
        {/* 分页控件 */}
        {pagination.total > 0 && (
          <div className="flex-shrink-0 flex flex-col sm:flex-row items-center justify-between px-4 py-3 border-t border-gray-200 dark:border-gray-700 gap-3">
            <div className="flex items-center gap-2 text-sm text-gray-500">
              <span>每页</span>
              <select
                value={pagination.pageSize}
                onChange={(e) => handlePageSizeChange(Number(e.target.value))}
                disabled={itemsLoading}
                className="px-2 py-1 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-800 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              >
                <option value={10}>10</option>
                <option value={20}>20</option>
                <option value={50}>50</option>
                <option value={100}>100</option>
              </select>
              <span>条，共 {pagination.total} 条</span>
            </div>
            <div className="flex items-center gap-2">
              <span className="text-sm text-gray-500">
                第 {pagination.page} / {pagination.totalPages} 页
              </span>
              <button
                onClick={() => handlePageChange(pagination.page - 1)}
                disabled={pagination.page <= 1 || itemsLoading}
                className="p-2 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                <ChevronLeft className="w-5 h-5" />
              </button>
              <button
                onClick={() => handlePageChange(pagination.page + 1)}
                disabled={pagination.page >= pagination.totalPages || itemsLoading}
                className="p-2 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                <ChevronRight className="w-5 h-5" />
              </button>
            </div>
          </div>
        )}
      </div>

      {/* 卡券关联选择弹窗 */}
      {relationItem && (
        <ItemCardRelationModal
          itemId={relationItem.item_id}
          itemName={relationItem.item_title || relationItem.title || relationItem.item_id}
          onClose={() => setRelationItem(null)}
          onSaved={() => {
            setRelationItem(null)
            loadItems()
          }}
        />
      )}

      {/* 编辑弹窗 */}
      {editingItem && (
        <div className="modal-overlay">
          <div className="modal-content max-w-lg">
            <div className="modal-header">
              <h2 className="modal-title">编辑商品</h2>
              <button onClick={() => setEditingItem(null)} className="modal-close">
                <X className="w-4 h-4" />
              </button>
            </div>
            <div className="modal-body space-y-4">
              <div className="input-group">
                <label className="input-label">商品ID</label>
                <input
                  type="text"
                  value={editingItem.item_id}
                  disabled
                  className="input-ios bg-slate-100 dark:bg-slate-700"
                />
              </div>
              <div className="input-group">
                <label className="input-label">商品标题</label>
                <input
                  type="text"
                  value={editingItem.item_title || editingItem.title || ''}
                  disabled
                  className="input-ios bg-slate-100 dark:bg-slate-700"
                />
              </div>
              <div className="input-group">
                <label className="input-label">商品价格(没有同步闲鱼功能)</label>
                <input
                  type="text"
                  value={editPrice}
                  onChange={(e) => setEditPrice(e.target.value)}
                  className="input-ios"
                  placeholder="输入商品价格，如：99.00"
                />
              </div>
              <div className="input-group">
                <label className="input-label">商品详情(没有同步闲鱼功能)</label>
                <textarea
                  value={editDetail}
                  onChange={(e) => setEditDetail(e.target.value)}
                  className="input-ios h-32 resize-none"
                  placeholder="输入商品详情..."
                />
              </div>
            </div>
            <div className="modal-footer">
              <button
                type="button"
                onClick={() => setEditingItem(null)}
                className="btn-ios-secondary"
                disabled={editSaving}
              >
                取消
              </button>
              <button
                onClick={handleSaveEdit}
                className="btn-ios-primary"
                disabled={editSaving}
              >
                {editSaving ? (
                  <span className="flex items-center gap-2">
                    <Loader2 className="w-4 h-4 animate-spin" />
                    保存中...
                  </span>
                ) : (
                  '保存'
                )}
              </button>
            </div>
          </div>
        </div>
      )}


      {/* 商品默认回复配置弹窗 */}
      {defaultReplyItem && (
        <div className="modal-overlay" style={{ zIndex: 60 }}>
          <div className="modal-content max-w-lg">
            <div className="modal-header flex items-center justify-between">
              <div>
                <h2 className="modal-title flex items-center gap-2">
                  <MessageSquare className="w-5 h-5 text-purple-500" />
                  商品默认回复
                </h2>
                <p className="text-sm text-gray-500 mt-1 truncate max-w-[300px]">
                  {defaultReplyItem.item_title || defaultReplyItem.title || defaultReplyItem.item_id}
                </p>
              </div>
              <button onClick={closeDefaultReply} className="modal-close">
                <X className="w-4 h-4" />
              </button>
            </div>
            <div className="modal-body space-y-4">
              {loadingDefaultReply ? (
                <div className="flex items-center justify-center py-8">
                  <Loader2 className="w-6 h-6 animate-spin text-purple-500" />
                </div>
              ) : (
                <>
                  <div className="flex items-center gap-3">
                    <input
                      type="checkbox"
                      id="defaultReplyEnabled"
                      checked={defaultReplyEnabled}
                      onChange={(e) => setDefaultReplyEnabled(e.target.checked)}
                      className="w-4 h-4 rounded border-gray-300"
                    />
                    <label htmlFor="defaultReplyEnabled" className="font-medium text-gray-900 dark:text-white">
                      启用商品默认回复
                    </label>
                  </div>

                  {/* 回复类型选择 */}
                  <div className="input-group">
                    <label className="input-label">回复类型</label>
                    <div className="flex gap-2">
                      {([
                        { value: 'text', label: '默认回复' },
                        { value: 'api', label: 'API接口' },
                      ] as const).map((opt) => (
                        <button
                          key={opt.value}
                          type="button"
                          onClick={() => setDefaultReplyType(opt.value)}
                          disabled={!defaultReplyEnabled}
                          className={`flex-1 px-3 py-2 rounded-lg text-sm font-medium transition-colors border disabled:opacity-50 disabled:cursor-not-allowed ${
                            defaultReplyType === opt.value
                              ? 'bg-purple-600 text-white border-purple-600'
                              : 'bg-white dark:bg-slate-700 text-slate-600 dark:text-slate-300 border-slate-300 dark:border-slate-600 hover:border-purple-400'
                          }`}
                        >
                          {opt.label}
                        </button>
                      ))}
                    </div>
                  </div>

                  {/* API 接口配置（仅 API 类型显示） */}
                  {defaultReplyType === 'api' && (
                    <>
                      <div className="input-group">
                        <label className="input-label">API 地址</label>
                        <input
                          type="text"
                          value={defaultReplyApiUrl}
                          onChange={(e) => setDefaultReplyApiUrl(e.target.value)}
                          className="input-ios"
                          placeholder="https://example.com/api/reply"
                          disabled={!defaultReplyEnabled}
                        />
                      </div>
                      <div className="input-group">
                        <label className="input-label">超时时间（秒）</label>
                        <input
                          type="number"
                          min={1}
                          max={120}
                          value={defaultReplyApiTimeout}
                          onChange={(e) => setDefaultReplyApiTimeout(Number(e.target.value) || 80)}
                          className="input-ios"
                          placeholder="80"
                          disabled={!defaultReplyEnabled}
                        />
                      </div>
                      <div className="p-3 bg-purple-50 dark:bg-purple-900/20 rounded-lg space-y-2">
                        <p className="text-xs text-purple-600 dark:text-purple-400">
                          <strong>调用说明：</strong>触发默认回复时，系统会向上述地址发起 <code className="bg-purple-100 dark:bg-purple-800 px-1 rounded">POST</code> 请求，请求体为 JSON：
                        </p>
                        <pre className="text-xs bg-purple-100 dark:bg-purple-800 p-2 rounded overflow-x-auto whitespace-pre-wrap break-all">{`{
  "account_id": "闲鱼账号标识",
  "message": "买家发来的消息内容"
}`}</pre>
                        <p className="text-xs text-purple-600 dark:text-purple-400">
                          <strong>返回格式：</strong>兼容以下两种，任选其一：
                        </p>
                        <pre className="text-xs bg-purple-100 dark:bg-purple-800 p-2 rounded overflow-x-auto whitespace-pre-wrap break-all">{`// 方式一：JSON
{ "success": true, "reply": "要发送给买家的内容" }

// 方式二：纯文本
要发送给买家的内容`}</pre>
                        <p className="text-xs text-amber-600 dark:text-amber-400">
                          返回内容支持用 <code className="bg-purple-100 dark:bg-purple-800 px-1 rounded">######</code> 分隔为多条消息依次发送。接口调用失败、超时或返回空内容时，将不发送任何回复。
                        </p>
                      </div>
                    </>
                  )}

                  {/* 文本回复内容（API 类型时隐藏） */}
                  {defaultReplyType !== 'api' && (
                  <div className="input-group">
                    <label className="input-label">回复内容</label>
                    <textarea
                      value={defaultReplyContent}
                      onChange={(e) => setDefaultReplyContent(e.target.value)}
                      className="input-ios h-32 resize-none"
                      placeholder="输入该商品的默认回复内容..."
                      disabled={!defaultReplyEnabled}
                    />
                    <p className="text-xs text-gray-500 mt-1">
                      支持变量：{'{send_user_name}'} 用户昵称、{'{send_user_id}'} 用户ID、{'{send_message}'} 用户消息内容、{'{item_id}'} 商品ID<br />
                      多条消息：使用 <code className="bg-gray-100 dark:bg-gray-700 px-1 rounded">######</code> 分隔，将拆分为多条消息依次发送<br />
                      例如：第一条消息######第二条消息
                    </p>
                  </div>
                  )}
                  
                  {/* 图片上传（默认回复类型显示，与文本一起） */}
                  {defaultReplyType !== 'api' && (
                  <div className="input-group">
                    <label className="input-label">回复图片（可选）</label>
                    <input
                      ref={defaultReplyImageInputRef}
                      type="file"
                      accept="image/*"
                      onChange={handleDefaultReplyImageUpload}
                      className="hidden"
                      disabled={!defaultReplyEnabled}
                    />
                    {defaultReplyImage ? (
                      <div className="relative inline-block">
                        <img
                          src={defaultReplyImage}
                          alt="回复图片"
                          className="max-w-[200px] max-h-[150px] rounded-lg border border-slate-200 dark:border-slate-700"
                        />
                        <button
                          type="button"
                          onClick={() => setDefaultReplyImage('')}
                          disabled={!defaultReplyEnabled}
                          className="absolute -top-2 -right-2 w-6 h-6 bg-red-500 text-white rounded-full flex items-center justify-center hover:bg-red-600 disabled:opacity-50"
                        >
                          <X className="w-3 h-3" />
                        </button>
                      </div>
                    ) : (
                      <button
                        type="button"
                        onClick={() => defaultReplyImageInputRef.current?.click()}
                        disabled={defaultReplyImageUploading || !defaultReplyEnabled}
                        className="flex items-center gap-2 px-4 py-2 border-2 border-dashed border-slate-300 dark:border-slate-600 rounded-lg hover:border-purple-500 dark:hover:border-purple-400 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                      >
                        {defaultReplyImageUploading ? (
                          <>
                            <Loader2 className="w-4 h-4 animate-spin" />
                            <span className="text-sm text-slate-500">上传中...</span>
                          </>
                        ) : (
                          <>
                            <ImagePlus className="w-4 h-4 text-slate-400" />
                            <span className="text-sm text-slate-500">点击上传图片</span>
                          </>
                        )}
                      </button>
                    )}
                    <p className="text-xs text-slate-500 dark:text-slate-400 mt-1">
                      支持 JPG、PNG、GIF 格式，最大 5MB
                    </p>
                    <p className="text-xs text-amber-600 dark:text-amber-400 mt-1">
                      发送顺序：如果同时配置了图片和文字，将先发送图片，再发送文字内容
                    </p>
                  </div>
                  )}

                  <div className="flex items-center gap-3">
                    <input
                      type="checkbox"
                      id="defaultReplyOnce"
                      checked={defaultReplyOnce}
                      onChange={(e) => setDefaultReplyOnce(e.target.checked)}
                      className="w-4 h-4 rounded border-gray-300"
                      disabled={!defaultReplyEnabled}
                    />
                    <label htmlFor="defaultReplyOnce" className="text-gray-700 dark:text-gray-300">
                      只回复一次（同一用户咨询该商品只回复一次）
                    </label>
                  </div>
                  <div className="p-3 bg-purple-50 dark:bg-purple-900/20 rounded-lg text-sm text-purple-600 dark:text-purple-400">
                    <strong>说明：</strong>
                    <ul className="list-disc list-inside mt-1 space-y-1">
                      <li>商品默认回复优先级高于账号默认回复</li>
                      <li>回复优先级：关键词 &gt; AI回复 &gt; 商品默认回复 &gt; 账号默认回复</li>
                    </ul>
                  </div>
                </>
              )}
            </div>
            <div className="modal-footer flex justify-between">
              <button
                onClick={() => setDeleteDefaultReplyConfirm(true)}
                className="btn-ios-danger"
                disabled={savingDefaultReply || loadingDefaultReply}
              >
                删除配置
              </button>
              <div className="flex gap-2">
                <button onClick={closeDefaultReply} className="btn-ios-secondary" disabled={savingDefaultReply}>
                  取消
                </button>
                <button
                  onClick={handleSaveDefaultReply}
                  className="btn-ios-primary"
                  disabled={savingDefaultReply || loadingDefaultReply}
                >
                  {savingDefaultReply ? (
                    <span className="flex items-center gap-2">
                      <Loader2 className="w-4 h-4 animate-spin" />
                      保存中...
                    </span>
                  ) : (
                    '保存'
                  )}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* 图片预览弹窗 */}
      {isImagePreviewOpen && (
        <div className="modal-overlay" style={{ zIndex: 70 }}>
          <div className="modal-content max-w-4xl p-4">
            <div className="flex justify-between items-center mb-4">
              <h3 className="text-lg font-semibold">图片预览</h3>
              <button
                onClick={() => setIsImagePreviewOpen(false)}
                className="p-1 hover:bg-gray-100 dark:hover:bg-gray-800 rounded-lg"
              >
                <X className="w-5 h-5 text-gray-500" />
              </button>
            </div>
            <div className="flex justify-center">
              <img
                src={previewImageUrl}
                alt="预览"
                className="max-w-full max-h-[70vh] object-contain rounded-lg"
              />
            </div>
          </div>
        </div>
      )}

      {/* AI提示词配置弹窗 */}
      {aiPromptItem && (
        <div className="modal-overlay" style={{ zIndex: 60 }}>
          <div className="modal-content max-w-lg">
            <div className="modal-header flex items-center justify-between">
              <div>
                <h2 className="modal-title flex items-center gap-2">
                  <Bot className="w-5 h-5 text-blue-500" />
                  商品AI提示词
                </h2>
                <p className="text-sm text-gray-500 mt-1 truncate max-w-[300px]">
                  {aiPromptItem.item_title || aiPromptItem.title || aiPromptItem.item_id}
                </p>
              </div>
              <button onClick={closeAiPrompt} className="modal-close">
                <X className="w-4 h-4" />
              </button>
            </div>
            <div className="modal-body space-y-4">
              {loadingAiPrompt ? (
                <div className="flex items-center justify-center py-8">
                  <Loader2 className="w-6 h-6 animate-spin text-blue-500" />
                </div>
              ) : (
                <>
                  <div className="input-group">
                    <label className="input-label">AI提示词内容</label>
                    <textarea
                      value={aiPromptContent}
                      onChange={(e) => setAiPromptContent(e.target.value)}
                      className="input-ios h-40 resize-none"
                      placeholder="想写什么就直接写，没有格式要求"
                    />
                  </div>
                  <div className="p-3 bg-blue-50 dark:bg-blue-900/20 rounded-lg text-sm text-blue-600 dark:text-blue-400">
                    <strong>说明：</strong>
                    <ul className="list-disc list-inside mt-1 space-y-1">
                      <li>想写什么就直接写，没有格式要求</li>
                      <li>商品AI提示词会与系统提示词合并使用</li>
                      <li>可以用于补充商品特有的回复要求或注意事项</li>
                      <li>例如：特殊发货说明、售后政策、使用方法等</li>
                    </ul>
                  </div>
                </>
              )}
            </div>
            <div className="modal-footer flex justify-between">
              <button
                onClick={() => setDeleteAiPromptConfirm(true)}
                className="btn-ios-danger"
                disabled={savingAiPrompt || loadingAiPrompt || !aiPromptContent}
              >
                删除配置
              </button>
              <div className="flex gap-2">
                <button onClick={closeAiPrompt} className="btn-ios-secondary" disabled={savingAiPrompt}>
                  取消
                </button>
                <button
                  onClick={handleSaveAiPrompt}
                  className="btn-ios-primary"
                  disabled={savingAiPrompt || loadingAiPrompt}
                >
                  {savingAiPrompt ? (
                    <span className="flex items-center gap-2">
                      <Loader2 className="w-4 h-4 animate-spin" />
                      保存中...
                    </span>
                  ) : (
                    '保存'
                  )}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* 批量新增默认回复弹窗 */}
      {showBatchDefaultReplyModal && (
        <div className="modal-overlay" style={{ zIndex: 60 }}>
          <div className="modal-content max-w-2xl">
            <div className="modal-header flex items-center justify-between">
              <div>
                <h2 className="modal-title flex items-center gap-2">
                  <MessageSquare className="w-5 h-5 text-purple-500" />
                  批量新增默认回复
                </h2>
                <p className="text-sm text-gray-500 mt-1">
                  为多个商品配置相同的默认回复
                </p>
              </div>
              <button onClick={closeBatchDefaultReplyModal} className="modal-close">
                <X className="w-4 h-4" />
              </button>
            </div>
            <div className="modal-body space-y-4">
              {/* 商品选择区域 */}
              <div className="input-group">
                <div className="flex items-center justify-between mb-2">
                  <label className="input-label mb-0">选择商品</label>
                  <button
                    type="button"
                    onClick={toggleBatchSelectAll}
                    className="text-sm text-blue-600 hover:text-blue-700"
                  >
                    {batchSelectedItemIds.length === filteredItems.filter((item) => item.cookie_id === selectedAccount).length
                      ? '取消全选'
                      : '全选'}
                  </button>
                </div>
                {/* 商品搜索框 */}
                <div className="relative mb-2">
                  <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
                  <input
                    type="text"
                    value={batchItemSearch}
                    onChange={(e) => setBatchItemSearch(e.target.value)}
                    placeholder="搜索商品标题或ID..."
                    className="input-ios pl-9 py-2 text-sm"
                  />
                </div>
                <div className="border border-gray-200 dark:border-gray-700 rounded-lg max-h-48 overflow-y-auto">
                  {filteredItems
                    .filter((item) => item.cookie_id === selectedAccount)
                    .filter((item) => {
                      if (!batchItemSearch) return true
                      const search = batchItemSearch.toLowerCase()
                      const title = (item.item_title || item.title || '').toLowerCase()
                      return title.includes(search) || item.item_id.includes(search)
                    }).length === 0 ? (
                    <div className="p-4 text-center text-gray-500">
                      {batchItemSearch ? '未找到匹配的商品' : '当前账号暂无商品'}
                    </div>
                  ) : (
                    filteredItems
                      .filter((item) => item.cookie_id === selectedAccount)
                      .filter((item) => {
                        if (!batchItemSearch) return true
                        const search = batchItemSearch.toLowerCase()
                        const title = (item.item_title || item.title || '').toLowerCase()
                        return title.includes(search) || item.item_id.includes(search)
                      })
                      .map((item) => (
                        <label
                          key={item.item_id}
                          className="flex items-center gap-3 p-3 hover:bg-gray-50 dark:hover:bg-gray-800 cursor-pointer border-b border-gray-100 dark:border-gray-700 last:border-b-0"
                        >
                          <input
                            type="checkbox"
                            checked={batchSelectedItemIds.includes(item.item_id)}
                            onChange={() => toggleBatchItemSelect(item.item_id)}
                            className="w-4 h-4 rounded border-gray-300"
                          />
                          <div className="flex-1 min-w-0">
                            <p className="text-sm font-medium text-gray-900 dark:text-white truncate">
                              {item.item_title || item.title || item.item_id}
                            </p>
                            <p className="text-xs text-gray-500 truncate">
                              ID: {item.item_id}
                            </p>
                          </div>
                        </label>
                      ))
                  )}
                </div>
                <p className="text-xs text-gray-500 mt-1">
                  已选择 {batchSelectedItemIds.length} 个商品
                </p>
              </div>

              {/* 启用开关 */}
              <div className="flex items-center gap-3">
                <input
                  type="checkbox"
                  id="batchReplyEnabled"
                  checked={batchReplyEnabled}
                  onChange={(e) => setBatchReplyEnabled(e.target.checked)}
                  className="w-4 h-4 rounded border-gray-300"
                />
                <label htmlFor="batchReplyEnabled" className="font-medium text-gray-900 dark:text-white">
                  启用默认回复
                </label>
              </div>

              {/* 回复类型选择 */}
              <div className="input-group">
                <label className="input-label">回复类型</label>
                <div className="flex gap-2">
                  {([
                    { value: 'text', label: '默认回复' },
                    { value: 'api', label: 'API接口' },
                  ] as const).map((opt) => (
                    <button
                      key={opt.value}
                      type="button"
                      onClick={() => setBatchReplyType(opt.value)}
                      disabled={!batchReplyEnabled}
                      className={`flex-1 px-3 py-2 rounded-lg text-sm font-medium transition-colors border disabled:opacity-50 disabled:cursor-not-allowed ${
                        batchReplyType === opt.value
                          ? 'bg-purple-600 text-white border-purple-600'
                          : 'bg-white dark:bg-slate-700 text-slate-600 dark:text-slate-300 border-slate-300 dark:border-slate-600 hover:border-purple-400'
                      }`}
                    >
                      {opt.label}
                    </button>
                  ))}
                </div>
              </div>

              {/* API 接口配置（仅 API 类型显示） */}
              {batchReplyType === 'api' && (
                <>
                  <div className="input-group">
                    <label className="input-label">API 地址</label>
                    <input
                      type="text"
                      value={batchReplyApiUrl}
                      onChange={(e) => setBatchReplyApiUrl(e.target.value)}
                      className="input-ios"
                      placeholder="https://example.com/api/reply"
                      disabled={!batchReplyEnabled}
                    />
                  </div>
                  <div className="input-group">
                    <label className="input-label">超时时间（秒）</label>
                    <input
                      type="number"
                      min={1}
                      max={120}
                      value={batchReplyApiTimeout}
                      onChange={(e) => setBatchReplyApiTimeout(Number(e.target.value) || 80)}
                      className="input-ios"
                      placeholder="80"
                      disabled={!batchReplyEnabled}
                    />
                  </div>
                  <div className="p-3 bg-purple-50 dark:bg-purple-900/20 rounded-lg space-y-2">
                    <p className="text-xs text-purple-600 dark:text-purple-400">
                      <strong>调用说明：</strong>触发默认回复时，系统会向上述地址发起 <code className="bg-purple-100 dark:bg-purple-800 px-1 rounded">POST</code> 请求，请求体为 JSON：
                    </p>
                    <pre className="text-xs bg-purple-100 dark:bg-purple-800 p-2 rounded overflow-x-auto whitespace-pre-wrap break-all">{`{
  "account_id": "闲鱼账号标识",
  "message": "买家发来的消息内容"
}`}</pre>
                    <p className="text-xs text-purple-600 dark:text-purple-400">
                      <strong>返回格式：</strong>兼容以下两种，任选其一：
                    </p>
                    <pre className="text-xs bg-purple-100 dark:bg-purple-800 p-2 rounded overflow-x-auto whitespace-pre-wrap break-all">{`// 方式一：JSON
{ "success": true, "reply": "要发送给买家的内容" }

// 方式二：纯文本
要发送给买家的内容`}</pre>
                    <p className="text-xs text-amber-600 dark:text-amber-400">
                      返回内容支持用 <code className="bg-purple-100 dark:bg-purple-800 px-1 rounded">######</code> 分隔为多条消息依次发送。所有选中商品将使用相同的 API 配置。接口调用失败、超时或返回空内容时，将不发送任何回复。
                    </p>
                  </div>
                </>
              )}

              {/* 回复内容（API 类型时隐藏） */}
              {batchReplyType !== 'api' && (
              <div className="input-group">
                <label className="input-label">回复内容</label>
                <textarea
                  value={batchReplyContent}
                  onChange={(e) => setBatchReplyContent(e.target.value)}
                  className="input-ios h-32 resize-none"
                  placeholder="输入默认回复内容..."
                  disabled={!batchReplyEnabled}
                />
                <p className="text-xs text-gray-500 mt-1">
                  支持变量：{'{send_user_name}'} 用户昵称、{'{send_user_id}'} 用户ID、{'{send_message}'} 用户消息内容、{'{item_id}'} 商品ID<br />
                  多条消息：使用 <code className="bg-gray-100 dark:bg-gray-700 px-1 rounded">######</code> 分隔，将拆分为多条消息依次发送<br />
                  例如：第一条消息######第二条消息
                </p>
              </div>
              )}

              {/* 图片上传（API 类型时隐藏） */}
              {batchReplyType !== 'api' && (
              <div className="input-group">
                <label className="input-label">回复图片（可选）</label>
                <input
                  ref={batchReplyImageInputRef}
                  type="file"
                  accept="image/*"
                  onChange={handleBatchReplyImageUpload}
                  className="hidden"
                  disabled={!batchReplyEnabled}
                />
                {batchReplyImage ? (
                  <div className="relative inline-block">
                    <img
                      src={batchReplyImage}
                      alt="回复图片"
                      className="max-w-[200px] max-h-[150px] rounded-lg border border-slate-200 dark:border-slate-700"
                    />
                    <button
                      type="button"
                      onClick={() => setBatchReplyImage('')}
                      disabled={!batchReplyEnabled}
                      className="absolute -top-2 -right-2 w-6 h-6 bg-red-500 text-white rounded-full flex items-center justify-center hover:bg-red-600 disabled:opacity-50"
                    >
                      <X className="w-3 h-3" />
                    </button>
                  </div>
                ) : (
                  <button
                    type="button"
                    onClick={() => batchReplyImageInputRef.current?.click()}
                    disabled={batchReplyImageUploading || !batchReplyEnabled}
                    className="flex items-center gap-2 px-4 py-2 border-2 border-dashed border-slate-300 dark:border-slate-600 rounded-lg hover:border-purple-500 dark:hover:border-purple-400 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    {batchReplyImageUploading ? (
                      <>
                        <Loader2 className="w-4 h-4 animate-spin" />
                        <span className="text-sm text-slate-500">上传中...</span>
                      </>
                    ) : (
                      <>
                        <ImagePlus className="w-4 h-4 text-slate-400" />
                        <span className="text-sm text-slate-500">点击上传图片</span>
                      </>
                    )}
                  </button>
                )}
                <p className="text-xs text-slate-500 dark:text-slate-400 mt-1">
                  支持 JPG、PNG、GIF 格式，最大 5MB，所有选中商品将使用相同图片
                </p>
                <p className="text-xs text-amber-600 dark:text-amber-400 mt-1">
                  发送顺序：如果同时配置了图片和文字，将先发送图片，再发送文字内容
                </p>
              </div>
              )}

              {/* 只回复一次 */}
              <div className="flex items-center gap-3">
                <input
                  type="checkbox"
                  id="batchReplyOnce"
                  checked={batchReplyOnce}
                  onChange={(e) => setBatchReplyOnce(e.target.checked)}
                  className="w-4 h-4 rounded border-gray-300"
                  disabled={!batchReplyEnabled}
                />
                <label htmlFor="batchReplyOnce" className="text-gray-700 dark:text-gray-300">
                  只回复一次（同一用户咨询该商品只回复一次）
                </label>
              </div>

              {/* 说明 */}
              <div className="p-3 bg-purple-50 dark:bg-purple-900/20 rounded-lg text-sm text-purple-600 dark:text-purple-400">
                <strong>说明：</strong>
                <ul className="list-disc list-inside mt-1 space-y-1">
                  <li>已存在配置的商品将被更新，不存在的将新增</li>
                  <li>商品默认回复优先级高于账号默认回复</li>
                </ul>
              </div>
            </div>
            <div className="modal-footer flex justify-end gap-2">
              <button onClick={closeBatchDefaultReplyModal} className="btn-ios-secondary" disabled={savingBatchReply}>
                取消
              </button>
              <button
                onClick={handleSaveBatchDefaultReply}
                className="btn-ios-primary"
                disabled={savingBatchReply || batchSelectedItemIds.length === 0}
              >
                {savingBatchReply ? (
                  <span className="flex items-center gap-2">
                    <Loader2 className="w-4 h-4 animate-spin" />
                    保存中...
                  </span>
                ) : (
                  `保存 (${batchSelectedItemIds.length})`
                )}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* 批量新增AI提示词弹窗 */}
      {showBatchAiPromptModal && (
        <div className="modal-overlay" style={{ zIndex: 60 }}>
          <div className="modal-content max-w-2xl">
            <div className="modal-header flex items-center justify-between">
              <div>
                <h2 className="modal-title flex items-center gap-2">
                  <Bot className="w-5 h-5 text-blue-500" />
                  批量新增AI提示词
                </h2>
                <p className="text-sm text-gray-500 mt-1">
                  为多个商品配置相同的AI提示词
                </p>
              </div>
              <button onClick={closeBatchAiPromptModal} className="modal-close">
                <X className="w-4 h-4" />
              </button>
            </div>
            <div className="modal-body space-y-4">
              {/* 商品选择区域 */}
              <div className="input-group">
                <div className="flex items-center justify-between mb-2">
                  <label className="input-label mb-0">选择商品</label>
                  <button
                    type="button"
                    onClick={toggleBatchAiPromptSelectAll}
                    className="text-sm text-blue-600 hover:text-blue-700"
                  >
                    {batchAiPromptSelectedItemIds.length === filteredItems.filter((item) => item.cookie_id === selectedAccount).filter((item) => {
                      if (!batchAiPromptItemSearch) return true
                      const search = batchAiPromptItemSearch.toLowerCase()
                      const title = (item.item_title || item.title || '').toLowerCase()
                      return title.includes(search) || item.item_id.includes(search)
                    }).length
                      ? '取消全选'
                      : '全选'}
                  </button>
                </div>
                {/* 商品搜索框 */}
                <div className="relative mb-2">
                  <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
                  <input
                    type="text"
                    value={batchAiPromptItemSearch}
                    onChange={(e) => setBatchAiPromptItemSearch(e.target.value)}
                    placeholder="搜索商品标题或ID..."
                    className="input-ios pl-9 py-2 text-sm"
                  />
                </div>
                <div className="border border-gray-200 dark:border-gray-700 rounded-lg max-h-48 overflow-y-auto">
                  {filteredItems
                    .filter((item) => item.cookie_id === selectedAccount)
                    .filter((item) => {
                      if (!batchAiPromptItemSearch) return true
                      const search = batchAiPromptItemSearch.toLowerCase()
                      const title = (item.item_title || item.title || '').toLowerCase()
                      return title.includes(search) || item.item_id.includes(search)
                    }).length === 0 ? (
                    <div className="p-4 text-center text-gray-500">
                      {batchAiPromptItemSearch ? '未找到匹配的商品' : '当前账号暂无商品'}
                    </div>
                  ) : (
                    filteredItems
                      .filter((item) => item.cookie_id === selectedAccount)
                      .filter((item) => {
                        if (!batchAiPromptItemSearch) return true
                        const search = batchAiPromptItemSearch.toLowerCase()
                        const title = (item.item_title || item.title || '').toLowerCase()
                        return title.includes(search) || item.item_id.includes(search)
                      })
                      .map((item) => (
                        <label
                          key={item.item_id}
                          className="flex items-center gap-3 p-3 hover:bg-gray-50 dark:hover:bg-gray-800 cursor-pointer border-b border-gray-100 dark:border-gray-700 last:border-b-0"
                        >
                          <input
                            type="checkbox"
                            checked={batchAiPromptSelectedItemIds.includes(item.item_id)}
                            onChange={() => toggleBatchAiPromptItemSelect(item.item_id)}
                            className="w-4 h-4 rounded border-gray-300"
                          />
                          <div className="flex-1 min-w-0">
                            <p className="text-sm font-medium text-gray-900 dark:text-white truncate">
                              {item.item_title || item.title || item.item_id}
                            </p>
                            <p className="text-xs text-gray-500 truncate">
                              ID: {item.item_id}
                            </p>
                          </div>
                        </label>
                      ))
                  )}
                </div>
                <p className="text-xs text-gray-500 mt-1">
                  已选择 {batchAiPromptSelectedItemIds.length} 个商品
                </p>
              </div>

              {/* AI提示词内容 */}
              <div className="input-group">
                <label className="input-label">AI提示词内容</label>
                <textarea
                  value={batchAiPromptContent}
                  onChange={(e) => setBatchAiPromptContent(e.target.value)}
                  className="input-ios h-40 resize-none"
                  placeholder="想写什么就直接写，没有格式要求"
                />
              </div>

              {/* 说明 */}
              <div className="p-3 bg-blue-50 dark:bg-blue-900/20 rounded-lg text-sm text-blue-600 dark:text-blue-400">
                <strong>说明：</strong>
                <ul className="list-disc list-inside mt-1 space-y-1">
                  <li>想写什么就直接写，没有格式要求</li>
                  <li>已存在配置的商品将被更新，不存在的将新增</li>
                  <li>商品AI提示词会与系统提示词合并使用</li>
                  <li>可以用于补充商品特有的回复要求或注意事项</li>
                </ul>
              </div>
            </div>
            <div className="modal-footer flex justify-end gap-2">
              <button onClick={closeBatchAiPromptModal} className="btn-ios-secondary" disabled={savingBatchAiPrompt}>
                取消
              </button>
              <button
                onClick={handleSaveBatchAiPrompt}
                className="btn-ios-primary"
                disabled={savingBatchAiPrompt || batchAiPromptSelectedItemIds.length === 0}
              >
                {savingBatchAiPrompt ? (
                  <span className="flex items-center gap-2">
                    <Loader2 className="w-4 h-4 animate-spin" />
                    保存中...
                  </span>
                ) : (
                  `保存 (${batchAiPromptSelectedItemIds.length})`
                )}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* 删除商品确认弹窗 */}
      <ConfirmModal
        isOpen={deleteItemConfirm.open}
        title="删除确认"
        message="确定要删除这个商品吗？删除后无法恢复。"
        confirmText="删除"
        cancelText="取消"
        type="danger"
        loading={deleting}
        onConfirm={() => deleteItemConfirm.item && handleDelete(deleteItemConfirm.item)}
        onCancel={() => setDeleteItemConfirm({ open: false, item: null })}
      />

      {/* 批量删除商品确认弹窗 */}
      <ConfirmModal
        isOpen={batchDeleteItemConfirm}
        title="批量删除确认"
        message={`确定要删除选中的 ${selectedIds.size} 个商品吗？删除后无法恢复。`}
        confirmText="删除"
        cancelText="取消"
        type="danger"
        loading={deleting}
        onConfirm={handleBatchDelete}
        onCancel={() => setBatchDeleteItemConfirm(false)}
      />

      {/* 批量下架确认弹窗 */}
      <ConfirmModal
        isOpen={batchOfflineConfirm}
        title="批量下架确认"
        message={`确定要用账号「${selectedAccount}」下架选中的 ${selectedIds.size} 个商品吗？下架后商品将从在卖中移除（可在卖家后台重新上架）。`}
        confirmText="下架"
        cancelText="取消"
        type="warning"
        loading={offlining}
        onConfirm={handleBatchOffline}
        onCancel={() => setBatchOfflineConfirm(false)}
      />


      {/* 删除默认回复确认弹窗 */}
      <ConfirmModal
        isOpen={deleteDefaultReplyConfirm}
        title="删除确认"
        message="确定要删除该商品的默认回复配置吗？"
        confirmText="删除"
        cancelText="取消"
        type="danger"
        loading={savingDefaultReply}
        onConfirm={handleDeleteDefaultReply}
        onCancel={() => setDeleteDefaultReplyConfirm(false)}
      />

      {/* 批量删除默认回复确认弹窗 */}
      <ConfirmModal
        isOpen={batchDeleteDefaultReplyConfirm}
        title="批量删除确认"
        message={`确定要删除选中商品的默认回复配置吗？`}
        confirmText="删除"
        cancelText="取消"
        type="danger"
        loading={deleting}
        onConfirm={handleBatchDeleteDefaultReply}
        onCancel={() => setBatchDeleteDefaultReplyConfirm(false)}
      />

      {/* 删除AI提示词确认弹窗 */}
      <ConfirmModal
        isOpen={deleteAiPromptConfirm}
        title="删除确认"
        message="确定要删除该商品的AI提示词配置吗？"
        confirmText="删除"
        cancelText="取消"
        type="danger"
        loading={savingAiPrompt}
        onConfirm={handleDeleteAiPrompt}
        onCancel={() => setDeleteAiPromptConfirm(false)}
      />

      {/* 批量删除AI提示词确认弹窗 */}
      <ConfirmModal
        isOpen={batchDeleteAiPromptConfirm}
        title="批量删除确认"
        message={`确定要删除选中商品的AI提示词配置吗？`}
        confirmText="删除"
        cancelText="取消"
        type="danger"
        loading={deleting}
        onConfirm={handleBatchDeleteAiPrompt}
        onCancel={() => setBatchDeleteAiPromptConfirm(false)}
      />

      {/* 批量清空关联卡券确认弹窗 */}
      <ConfirmModal
        isOpen={batchClearCardRelationsConfirm}
        title="清空关联卡券确认"
        message={`确定要清空选中的 ${selectedIds.size} 个商品的卡券关联关系吗？此操作不会删除卡券本身，仅解除关联。`}
        confirmText="清空"
        cancelText="取消"
        type="danger"
        loading={deleting}
        onConfirm={handleBatchClearCardRelations}
        onCancel={() => setBatchClearCardRelationsConfirm(false)}
      />
    </div>
  )
}
