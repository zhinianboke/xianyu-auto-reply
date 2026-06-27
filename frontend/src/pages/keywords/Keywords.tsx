import { useState, useEffect, useRef } from 'react'
import type { FormEvent, ChangeEvent } from 'react'
import { motion } from 'framer-motion'
import { MessageSquare, RefreshCw, Plus, Edit2, Trash2, Upload, Download, Info, Image, CheckSquare, Square, Search, ChevronLeft, ChevronRight } from 'lucide-react'
import { getKeywords, deleteKeyword, saveKeywords, updateKeyword, exportKeywords, importKeywords as importKeywordsApi, addImageKeyword } from '@/api/keywords'
import { getAccountDetails } from '@/api/accounts'
import { getItems } from '@/api/items'
import { useUIStore } from '@/store/uiStore'
import { PageLoading } from '@/components/common/Loading'
import { useAuthStore } from '@/store/authStore'
import { Select } from '@/components/common/Select'
import { ConfirmModal } from '@/components/common/ConfirmModal'
import type { Keyword, Account, Item } from '@/types'

/** 解析关键词文本域，按行保存是为了兼容旧表结构的一条关键词一条规则。 */
const parseKeywordLines = (value: string) => value.split(/\r?\n/).map(line => line.trim()).filter(Boolean)

/** 归一化关键词文本，保存为一条规则时仍按行保留用户维护习惯。 */
const normalizeKeywordText = (value: string) => parseKeywordLines(value).join('\n')

/** 查找同一次提交里的重复关键词，提前拦截可以避免整体保存后部分数据不可预期。 */
const findDuplicateKeywordLine = (keywordLines: string[]) => {
  const seen = new Set<string>()
  for (const keyword of keywordLines) {
    const key = keyword.toLowerCase()
    if (seen.has(key)) {
      return keyword
    }
    seen.add(key)
  }
  return ''
}

/** 生成关键词唯一键，前端校验要和后端同一商品下唯一的规则保持一致。 */
const buildKeywordRuleKey = (keyword: string, itemId?: string) =>
  `${keyword.trim().toLowerCase()}__${(itemId || '').trim().toLowerCase()}`

/** 展开规则里的多行关键词，用于列表展示和跨规则重复校验。 */
const getKeywordLineKeys = (keyword: Keyword) =>
  parseKeywordLines(keyword.keyword).map(line => buildKeywordRuleKey(line, keyword.item_id))

export function Keywords() {
  const { addToast } = useUIStore()
  const { isAuthenticated, token, _hasHydrated } = useAuthStore()
  const [loading, setLoading] = useState(true)
  const [keywords, setKeywords] = useState<Keyword[]>([])
  const [accounts, setAccounts] = useState<Account[]>([])
  const [items, setItems] = useState<Item[]>([])
  const [selectedAccount, setSelectedAccount] = useState('')
  const [formAccountId, setFormAccountId] = useState('')
  const [isModalOpen, setIsModalOpen] = useState(false)
  const [editingKeyword, setEditingKeyword] = useState<Keyword | null>(null)
  const [keywordText, setKeywordText] = useState('')
  const [replyText, setReplyText] = useState('')
  const [itemIdText, setItemIdText] = useState('')  // 绑定的商品ID（编辑时使用）
  const [selectedItemIds, setSelectedItemIds] = useState<string[]>([])  // 多选商品ID（新增时使用）
  const [itemSearchText, setItemSearchText] = useState('')  // 商品搜索
  const [saving, setSaving] = useState(false)
  const [importing, setImporting] = useState(false)
  const [exporting, setExporting] = useState(false)
  const importInputRef = useRef<HTMLInputElement | null>(null)
  
  // 图片关键词相关状态
  const [isImageModalOpen, setIsImageModalOpen] = useState(false)
  const [imageKeyword, setImageKeyword] = useState('')
  const [imageSelectedItemIds, setImageSelectedItemIds] = useState<string[]>([])  // 多选商品ID
  const [imageItemSearchText, setImageItemSearchText] = useState('')  // 商品搜索
  const [imageFile, setImageFile] = useState<File | null>(null)
  const [imagePreview, setImagePreview] = useState<string>('')
  const [savingImage, setSavingImage] = useState(false)
  const imageInputRef = useRef<HTMLInputElement | null>(null)
  
  // 图片预览弹窗状态
  const [isImagePreviewOpen, setIsImagePreviewOpen] = useState(false)
  const [previewImageUrl, setPreviewImageUrl] = useState('')

  // 批量选择删除状态
  const [selectedKeywordIds, setSelectedKeywordIds] = useState<Set<string>>(new Set())

  // 删除确认弹窗状态
  const [deleteConfirm, setDeleteConfirm] = useState<{ open: boolean; keyword: Keyword | null }>({ open: false, keyword: null })
  const [batchDeleteConfirm, setBatchDeleteConfirm] = useState(false)
  const [deleting, setDeleting] = useState(false)

  // 前端分页状态
  const [currentPage, setCurrentPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)

  // 计算分页数据
  const totalPages = Math.ceil(keywords.length / pageSize)
  const paginatedKeywords = keywords.slice((currentPage - 1) * pageSize, currentPage * pageSize)
  const getKeywordAccountId = (keyword: Keyword) => keyword.account_id || selectedAccount

  // 分页切换
  const handlePageChange = (newPage: number) => {
    if (newPage >= 1 && newPage <= totalPages) {
      setCurrentPage(newPage)
    }
  }

  // 每页条数切换
  const handlePageSizeChange = (newPageSize: number) => {
    setPageSize(newPageSize)
    setCurrentPage(1)
  }

  const loadKeywords = async () => {
    if (!_hasHydrated || !isAuthenticated || !token) {
      return
    }
    try {
      setLoading(true)
      // selectedAccount为空字符串时查询全部账号
      const data = await getKeywords(selectedAccount || undefined)
      // 确保 data 是数组，防止后端返回非数组或请求失败时出错
      setKeywords(Array.isArray(data) ? data : [])
      setCurrentPage(1) // 重置分页
    } catch {
      setKeywords([])
      addToast({ type: 'error', message: '加载关键词列表失败' })
    } finally {
      setLoading(false)
    }
  }

  const loadAccounts = async () => {
    if (!_hasHydrated || !isAuthenticated || !token) {
      return
    }
    try {
      setLoading(true)
      const data = await getAccountDetails()
      setAccounts(data)
      // 默认选择全部账号
      if (!selectedAccount && data.length > 0) {
        setSelectedAccount('')
      }
    } catch {
      // ignore
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    if (!_hasHydrated || !isAuthenticated || !token) return
    loadAccounts()
    loadKeywords() // 初始加载全部账号的关键词
  }, [_hasHydrated, isAuthenticated, token])

  useEffect(() => {
    if (!_hasHydrated || !isAuthenticated || !token) return
    loadKeywords()
    if (selectedAccount) {
      loadItems(selectedAccount)
    } else {
      setItems([])
    }
  }, [selectedAccount])

  useEffect(() => {
    if (!_hasHydrated || !isAuthenticated || !token || !isModalOpen) return
    if (formAccountId) {
      loadItems(formAccountId)
    } else {
      setItems([])
    }
  }, [formAccountId, isModalOpen, _hasHydrated, isAuthenticated, token])

  const loadItems = async (accountId: string) => {
    if (!accountId) {
      setItems([])
      return
    }
    try {
      const result = await getItems(accountId)
      setItems(result.data || [])
    } catch {
      setItems([])
    }
  }

  const openAddModal = () => {
    if (!selectedAccount) {
      addToast({ type: 'warning', message: '请先选择具体账号才能添加关键词' })
      return
    }
    setEditingKeyword(null)
    setFormAccountId(selectedAccount)
    setKeywordText('')
    setReplyText('')
    setItemIdText('')
    setSelectedItemIds([])
    setItemSearchText('')
    setIsModalOpen(true)
  }

  const openEditModal = (keyword: Keyword) => {
    // 图片关键词不支持编辑
    if (keyword.type === 'image') {
      addToast({ type: 'warning', message: '图片关键词不支持编辑，请删除后重新添加' })
      return
    }
    const accountId = getKeywordAccountId(keyword)
    if (!accountId) {
      addToast({ type: 'error', message: '未找到所属账号，无法编辑' })
      return
    }
    
    // 文本关键词：打开文本模态框
    setEditingKeyword(keyword)
    setFormAccountId(accountId)
    setKeywordText(keyword.keyword)
    setReplyText(keyword.reply)
    setItemIdText(keyword.item_id || '')
    setIsModalOpen(true)
  }

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()

    const submitAccountId = editingKeyword ? formAccountId : selectedAccount
    const keywordLines = parseKeywordLines(keywordText)
    const duplicateKeyword = findDuplicateKeywordLine(keywordLines)

    if (!submitAccountId) {
      addToast({ type: 'warning', message: '请先选择账号' })
      return
    }

    if (keywordLines.length === 0) {
      addToast({ type: 'warning', message: '请输入关键词' })
      return
    }

    if (duplicateKeyword) {
      addToast({ type: 'warning', message: `关键词"${duplicateKeyword}"重复，请检查后再保存` })
      return
    }

    if (!replyText.trim()) {
      addToast({ type: 'warning', message: '请输入回复内容' })
      return
    }

    try {
      setSaving(true)
      const normalizedKeywordText = normalizeKeywordText(keywordText)

      if (editingKeyword) {
        const sourceAccountId = getKeywordAccountId(editingKeyword)
        if (!sourceAccountId) {
          addToast({ type: 'error', message: '未找到原所属账号，无法保存' })
          return
        }
        // 编辑模式：多行关键词仍保存为同一条规则，方便后续在一个入口维护同回复内容。
        const result = await updateKeyword(
          sourceAccountId,
          editingKeyword.keyword,
          editingKeyword.item_id || '',
          {
            account_id: submitAccountId,
            keyword: normalizedKeywordText,
            reply: replyText.trim(),
            item_id: itemIdText.trim(),
          }
        )
        if (result.success === false) {
          addToast({ type: 'error', message: result.message || '更新失败' })
          return
        }
        addToast({ type: 'success', message: '关键词已更新' })
      } else {
        // 新增模式：每个商品只新增一条规则，避免多账号场景下同回复关键词被拆散后难以查找。
        const itemIdsToAdd = selectedItemIds.length > 0 ? selectedItemIds : ['']
        const existingKeywords = await getKeywords(submitAccountId)
        const existingKeys = new Set(existingKeywords.flatMap(getKeywordLineKeys))
        const conflictKeyword = itemIdsToAdd
          .flatMap(itemId => keywordLines.map(keyword => ({ keyword, item_id: itemId })))
          .find(k => existingKeys.has(buildKeywordRuleKey(k.keyword, k.item_id)))

        if (conflictKeyword) {
          const itemDesc = conflictKeyword.item_id ? `商品ID：${conflictKeyword.item_id}` : '通用关键词'
          addToast({ type: 'error', message: `关键词"${conflictKeyword.keyword}"（${itemDesc}）已存在` })
          return
        }

        const newKeywords = itemIdsToAdd.map(itemId => ({
          keyword: normalizedKeywordText,
          reply: replyText.trim(),
          item_id: itemId,
          type: 'text' as const,
        } as Keyword))
        const result = await saveKeywords(submitAccountId, [...existingKeywords, ...newKeywords])
        if (result.success === false) {
          addToast({ type: 'error', message: result.message || '添加失败' })
          return
        }

        addToast({ type: 'success', message: `成功添加 ${newKeywords.length} 条关键词规则` })
      }

      await loadKeywords()
      setIsModalOpen(false)
    } catch {
      addToast({ type: 'error', message: '保存关键词失败' })
    } finally {
      setSaving(false)
    }
  }

  const handleExport = async () => {
    if (!selectedAccount) {
      addToast({ type: 'warning', message: '请先选择账号' })
      return
    }

    try {
      setExporting(true)
      const blob = await exportKeywords(selectedAccount)
      const url = window.URL.createObjectURL(blob)
      const a = document.createElement('a')
      const date = new Date().toISOString().split('T')[0]
      a.href = url
      a.download = `keywords_${selectedAccount}_${date}.xlsx`
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      window.URL.revokeObjectURL(url)
      addToast({ type: 'success', message: '关键词导出成功' })
    } catch {
      addToast({ type: 'error', message: '关键词导出失败' })
    } finally {
      setExporting(false)
    }
  }

  const handleImportButtonClick = () => {
    if (!selectedAccount) {
      addToast({ type: 'warning', message: '请先选择账号' })
      return
    }
    importInputRef.current?.click()
  }

  const handleImportFileChange = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0]
    if (!file) return

    try {
      setImporting(true)
      const result = await importKeywordsApi(selectedAccount, file)
      if (result.success) {
        const info = (result.data as { added?: number; updated?: number } | undefined) || {}
        addToast({
          type: 'success',
          message: `导入成功：新增 ${info.added ?? 0} 条，更新 ${info.updated ?? 0} 条`,
        })
        await loadKeywords()
      } else {
        addToast({ type: 'error', message: result.message || '导入失败' })
      }
    } catch {
      addToast({ type: 'error', message: '导入关键词失败' })
    } finally {
      setImporting(false)
      event.target.value = ''
    }
  }

  const handleDelete = async (keyword: Keyword) => {
    setDeleting(true)
    try {
      const accountId = getKeywordAccountId(keyword)
      if (!accountId) {
        addToast({ type: 'error', message: '未找到所属账号，无法删除' })
        return
      }
      const result = await deleteKeyword(accountId, keyword.keyword, keyword.item_id || '', keyword.id)
      if (result.success === false) {
        addToast({ type: 'error', message: result.message || '删除失败' })
        return
      }
      addToast({ type: 'success', message: '删除成功' })
      setDeleteConfirm({ open: false, keyword: null })
      await loadKeywords()
    } catch {
      addToast({ type: 'error', message: '删除失败' })
    } finally {
      setDeleting(false)
    }
  }

  // 批量选择相关
  const getKeywordUniqueId = (keyword: Keyword) => keyword.id || `${getKeywordAccountId(keyword)}_${keyword.keyword}_${keyword.item_id || ''}`

  const toggleKeywordSelect = (keyword: Keyword) => {
    const id = getKeywordUniqueId(keyword)
    setSelectedKeywordIds((prev) => {
      const next = new Set(prev)
      if (next.has(id)) {
        next.delete(id)
      } else {
        next.add(id)
      }
      return next
    })
  }

  const toggleSelectAllKeywords = () => {
    if (selectedKeywordIds.size === keywords.length) {
      setSelectedKeywordIds(new Set())
    } else {
      setSelectedKeywordIds(new Set(keywords.map(getKeywordUniqueId)))
    }
  }

  const handleBatchDelete = async () => {
    if (selectedKeywordIds.size === 0) {
      addToast({ type: 'warning', message: '请先选择要删除的关键词' })
      return
    }

    setDeleting(true)
    let successCount = 0
    let failCount = 0
    let firstErrorMessage = ''

    for (const keyword of keywords) {
      if (selectedKeywordIds.has(getKeywordUniqueId(keyword))) {
        try {
          const accountId = getKeywordAccountId(keyword)
          if (!accountId) {
            failCount++
            if (!firstErrorMessage) {
              firstErrorMessage = '存在未找到所属账号的关键词，无法删除'
            }
            continue
          }
          const result = await deleteKeyword(accountId, keyword.keyword, keyword.item_id || '', keyword.id)
          if (result.success === false) {
            failCount++
            if (!firstErrorMessage) {
              firstErrorMessage = result.message || '删除失败'
            }
            continue
          }
          successCount++
        } catch {
          failCount++
          if (!firstErrorMessage) {
            firstErrorMessage = '删除失败'
          }
        }
      }
    }

    if (failCount === 0) {
      addToast({ type: 'success', message: `成功删除 ${successCount} 个关键词` })
    } else if (successCount > 0) {
      addToast({ type: 'warning', message: `${`删除 ${successCount} 个成功，${failCount} 个失败`}${firstErrorMessage ? `：${firstErrorMessage}` : ''}` })
    } else {
      addToast({ type: 'error', message: firstErrorMessage || '删除失败' })
    }

    setSelectedKeywordIds(new Set())
    setBatchDeleteConfirm(false)
    setDeleting(false)
    await loadKeywords()
  }

  // 图片关键词功能
  const openImageModal = () => {
    if (!selectedAccount) {
      addToast({ type: 'warning', message: '请先选择账号' })
      return
    }
    setImageKeyword('')
    setImageSelectedItemIds([])
    setImageItemSearchText('')
    setImageFile(null)
    setImagePreview('')
    setIsImageModalOpen(true)
  }

  const handleImageFileChange = (e: ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return

    // 验证文件类型
    if (!file.type.startsWith('image/')) {
      addToast({ type: 'error', message: '请选择图片文件' })
      return
    }

    // 验证文件大小 (5MB)
    if (file.size > 5 * 1024 * 1024) {
      addToast({ type: 'error', message: '图片大小不能超过5MB' })
      return
    }

    setImageFile(file)
    // 生成预览
    const reader = new FileReader()
    reader.onload = (event) => {
      setImagePreview(event.target?.result as string)
    }
    reader.readAsDataURL(file)
  }

  const handleImageSubmit = async (e: FormEvent) => {
    e.preventDefault()
    if (!imageKeyword.trim()) {
      addToast({ type: 'warning', message: '请输入关键词' })
      return
    }
    if (!imageFile) {
      addToast({ type: 'warning', message: '请选择图片' })
      return
    }

    setSavingImage(true)
    try {
      // 支持多选商品
      const itemIdsToAdd = imageSelectedItemIds.length > 0 ? imageSelectedItemIds : ['']
      let successCount = 0
      let failCount = 0
      let lastErrorMsg = ''

      for (const itemId of itemIdsToAdd) {
        try {
          const result = await addImageKeyword(
            selectedAccount,
            imageKeyword.trim(),
            imageFile,
            itemId || undefined
          )
          // 兼容新旧响应格式
          const isSuccess = result?.success === true || 
            (result as unknown as { keyword?: string }).keyword !== undefined
          if (isSuccess) {
            successCount++
          } else {
            failCount++
            lastErrorMsg = result?.message || '添加失败'
          }
        } catch {
          failCount++
        }
      }

      if (failCount === 0) {
        addToast({ type: 'success', message: `成功添加 ${successCount} 条图片关键词` })
        setIsImageModalOpen(false)
        loadKeywords()
      } else if (successCount > 0) {
        addToast({ type: 'warning', message: `添加 ${successCount} 条成功，${failCount} 条失败` })
        setIsImageModalOpen(false)
        loadKeywords()
      } else {
        addToast({ type: 'error', message: lastErrorMsg || '添加失败' })
      }
    } catch (err) {
      const error = err as { response?: { data?: { detail?: string; message?: string } } }
      addToast({ type: 'error', message: error.response?.data?.message || error.response?.data?.detail || '添加图片关键词失败' })
    } finally {
      setSavingImage(false)
    }
  }

  if (loading && accounts.length === 0) {
    return <PageLoading />
  }

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="page-title">自动回复</h1>
          <p className="page-description">管理关键词自动回复规则</p>
        </div>
        <div className="flex flex-wrap gap-3">
          {selectedKeywordIds.size > 0 && (
            <button
              type="button"
              onClick={() => setBatchDeleteConfirm(true)}
              className="btn-ios-danger"
            >
              <Trash2 className="w-4 h-4" />
              删除选中 ({selectedKeywordIds.size})
            </button>
          )}
          <button
            type="button"
            onClick={openAddModal}
            className="btn-ios-primary"
          >
            <Plus className="w-4 h-4" />
            添加文本关键词
          </button>
          <button
            type="button"
            onClick={openImageModal}
            className="btn-ios-primary"
          >
            <Image className="w-4 h-4" />
            添加图片关键词
          </button>
          <button
            type="button"
            onClick={handleExport}
            disabled={!selectedAccount || exporting}
            className="btn-ios-secondary"
          >
            <Download className="w-4 h-4" />
            导出
          </button>
          <button
            type="button"
            onClick={handleImportButtonClick}
            disabled={!selectedAccount || importing}
            className="btn-ios-secondary "
          >
            <Upload className="w-4 h-4" />
            导入
          </button>
          <button onClick={loadKeywords} className="btn-ios-secondary ">
            <RefreshCw className="w-4 h-4" />
            刷新
          </button>
          <input
            ref={importInputRef}
            type="file"
            accept=".xlsx,.xls"
            className="hidden"
            onChange={handleImportFileChange}
          />
        </div>
      </div>

      {/* Account Select */}
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        className="vben-card"
      >
        <div className="vben-card-body">
          <div className="max-w-md">
            <label className="input-label">选择账号</label>
            <Select
              value={selectedAccount}
              onChange={setSelectedAccount}
              options={
                accounts.length === 0
                  ? [{ value: '', label: '暂无账号', key: 'empty' }]
                  : [
                      { value: '', label: '全部账号', key: 'all' },
                      ...accounts.map((account) => ({
                        value: account.id,
                        label: account.note ? `${account.id} (${account.note})` : account.id,
                        key: account.pk?.toString() || account.id,
                      }))
                    ]
              }
              placeholder="选择账号"
            />
          </div>
        </div>
      </motion.div>

      {/* 变量提示说明 */}
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.05 }}
        className="vben-card flex flex-col"
        style={{ height: 'calc(100vh - 280px)', minHeight: '400px' }}
      >
        <div className="vben-card-header flex-shrink-0">
          <h2 className="vben-card-title flex items-center gap-2">
            <MessageSquare className="w-4 h-4" />
            关键词列表
          </h2>
          <span className="badge-primary">{keywords.length} 个关键词</span>
        </div>
        <div className="flex-1 overflow-auto">
          <table className="table-ios">
            <thead className="sticky top-0 bg-white dark:bg-slate-800 z-10">
              <tr>
                <th className="w-10">
                  <button
                    onClick={toggleSelectAllKeywords}
                    className="p-1 hover:bg-gray-100 dark:hover:bg-gray-700 rounded"
                    title={selectedKeywordIds.size === keywords.length ? '取消全选' : '全选'}
                  >
                    {selectedKeywordIds.size === keywords.length && keywords.length > 0 ? (
                      <CheckSquare className="w-4 h-4 text-blue-600 dark:text-blue-400" />
                    ) : (
                      <Square className="w-4 h-4 text-gray-400" />
                    )}
                  </button>
                </th>
                <th>所属账号</th>
                <th>关键词</th>
                <th>商品ID</th>
                <th>回复内容</th>
                <th>类型</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr>
                  <td colSpan={7} className="text-center py-8 text-gray-500">
                    加载中...
                  </td>
                </tr>
              ) : keywords.length === 0 ? (
                <tr>
                  <td colSpan={7} className="text-center py-8 text-gray-500">
                    <div className="flex flex-col items-center gap-2">
                      <MessageSquare className="w-12 h-12 text-gray-300" />
                      <p>暂无关键词，点击上方按钮添加</p>
                    </div>
                  </td>
                </tr>
              ) : (
                paginatedKeywords.map((keyword) => (
                  <tr key={getKeywordUniqueId(keyword)} className={selectedKeywordIds.has(getKeywordUniqueId(keyword)) ? 'bg-blue-50 dark:bg-blue-900/20' : ''}>
                    <td>
                      <button
                        onClick={() => toggleKeywordSelect(keyword)}
                        className="p-1 hover:bg-gray-100 dark:hover:bg-gray-700 rounded"
                      >
                        {selectedKeywordIds.has(getKeywordUniqueId(keyword)) ? (
                          <CheckSquare className="w-4 h-4 text-blue-600 dark:text-blue-400" />
                        ) : (
                          <Square className="w-4 h-4 text-gray-400" />
                        )}
                      </button>
                    </td>
                    <td>
                      <span className="text-xs text-slate-600 dark:text-slate-300">
                        {keyword.account_id || selectedAccount || '-'}
                      </span>
                    </td>
                    <td className="font-medium">
                      <div className="flex max-w-[360px] flex-wrap gap-1.5">
                        {parseKeywordLines(keyword.keyword).map((keywordLine) => (
                          <code
                            key={keywordLine}
                            className="bg-blue-50 dark:bg-blue-900/30 text-blue-600 dark:text-blue-400 px-2 py-1 rounded"
                          >
                            {keywordLine}
                          </code>
                        ))}
                      </div>
                    </td>
                    <td>
                      {keyword.item_id ? (
                        <span className="text-xs text-slate-500 dark:text-slate-400">{keyword.item_id}</span>
                      ) : (
                        <span className="text-xs text-gray-400">通用</span>
                      )}
                    </td>
                    <td className="max-w-[300px]">
                      {keyword.type === 'image' ? (
                        <button
                          onClick={() => {
                            setPreviewImageUrl(keyword.image_url || '')
                            setIsImagePreviewOpen(true)
                          }}
                          className="text-blue-600 dark:text-blue-400 hover:underline text-sm"
                        >
                          查看大图
                        </button>
                      ) : (
                        <p className="truncate text-slate-600 dark:text-slate-300" title={keyword.reply}>
                          {keyword.reply || <span className="text-gray-400">不回复</span>}
                        </p>
                      )}
                    </td>
                    <td>
                      {keyword.type === 'image' ? (
                        <span className="badge-primary">图片</span>
                      ) : (
                        <span className="badge-gray">文本</span>
                      )}
                    </td>
                    <td>
                      <div className="">
                        <button
                          onClick={() => openEditModal(keyword)}
                          className="p-2 rounded-lg hover:bg-slate-100 dark:hover:bg-slate-700 transition-colors"
                          title="编辑"
                        >
                          <Edit2 className="w-4 h-4 text-blue-500 dark:text-blue-400" />
                        </button>
                        <button
                          onClick={() => setDeleteConfirm({ open: true, keyword })}
                          className="p-2 rounded-lg hover:bg-red-50 dark:hover:bg-red-900/30 transition-colors"
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

        {/* 分页控件 */}
        {keywords.length > 0 && (
          <div className="flex-shrink-0 flex flex-col sm:flex-row items-center justify-between px-4 py-3 border-t border-gray-200 dark:border-gray-700 gap-3">
            <div className="flex items-center gap-2 text-sm text-gray-500">
              <span>每页</span>
              <select
                value={pageSize}
                onChange={(e) => handlePageSizeChange(Number(e.target.value))}
                className="px-2 py-1 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-800 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              >
                <option value={10}>10</option>
                <option value={20}>20</option>
                <option value={50}>50</option>
                <option value={100}>100</option>
              </select>
              <span>条，共 {keywords.length} 条</span>
            </div>
            <div className="flex items-center gap-2">
              <span className="text-sm text-gray-500">
                第 {currentPage} / {totalPages || 1} 页
              </span>
              <button
                onClick={() => handlePageChange(currentPage - 1)}
                disabled={currentPage <= 1}
                className="p-2 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                <ChevronLeft className="w-5 h-5" />
              </button>
              <button
                onClick={() => handlePageChange(currentPage + 1)}
                disabled={currentPage >= totalPages}
                className="p-2 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                <ChevronRight className="w-5 h-5" />
              </button>
            </div>
          </div>
        )}
      </motion.div>

      {isModalOpen && (
        <div className="modal-overlay">
          <div className="modal-content">
            <div className="modal-header flex items-center justify-between">
              <h2 className="text-lg font-semibold">
                {editingKeyword ? '编辑关键词' : '添加关键词'}
              </h2>
              <button
                type="button"
                onClick={() => setIsModalOpen(false)}
                className="p-1 hover:bg-slate-100 dark:hover:bg-slate-700 rounded-lg transition-colors"
              >
                <svg className="w-5 h-5 text-slate-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>
            <form onSubmit={handleSubmit} className="flex flex-col flex-1 min-h-0">
              <div className="modal-body space-y-4 overflow-y-auto">
                <div>
                  <label className="input-label">所属账号</label>
                  {editingKeyword ? (
                    <Select
                      value={formAccountId}
                      onChange={(value) => {
                        if (value !== formAccountId) {
                          setFormAccountId(value)
                          setItemIdText('')
                        }
                      }}
                      options={accounts.map((account) => ({
                        value: account.id,
                        label: account.note ? `${account.id} (${account.note})` : account.id,
                        key: account.pk?.toString() || account.id,
                      }))}
                      placeholder="选择所属账号"
                    />
                  ) : (
                    <input
                      type="text"
                      value={formAccountId || selectedAccount}
                      disabled
                      className="input-ios bg-slate-100 dark:bg-slate-700 cursor-not-allowed"
                    />
                  )}
                </div>
                <div>
                  <label className="input-label">关键词</label>
                  <textarea
                    value={keywordText}
                    onChange={(e) => setKeywordText(e.target.value)}
                    className="input-ios h-24 resize-none"
                    placeholder="请输入关键词，一行一个"
                  />
                  <p className="text-xs text-slate-500 dark:text-slate-400 mt-1">
                    一行一个关键词，多个关键词会对应同一条回复内容
                  </p>
                </div>
                <div>
                  <label className="input-label">商品ID（可选）</label>
                  {editingKeyword ? (
                    // 编辑模式：单选
                    <>
                      <select
                        value={itemIdText}
                        onChange={(e) => setItemIdText(e.target.value)}
                        className="input-ios"
                      >
                        <option value="">通用关键词（所有商品）</option>
                        {items.map((item) => (
                          <option key={item.item_id} value={item.item_id}>
                            {item.item_id} - {item.title}
                          </option>
                        ))}
                      </select>
                      <p className="text-xs text-slate-500 dark:text-slate-400 mt-1">
                        绑定商品ID后，此关键词仅在该商品对话中生效
                      </p>
                    </>
                  ) : (
                    // 新增模式：多选
                    <>
                      <div className="relative mb-2">
                        <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
                        <input
                          type="text"
                          value={itemSearchText}
                          onChange={(e) => setItemSearchText(e.target.value)}
                          placeholder="搜索商品..."
                          className="input-ios pl-9 py-2 text-sm"
                        />
                      </div>
                      <div className="flex items-center justify-between mb-1">
                        <span className="text-xs text-gray-500">
                          {selectedItemIds.length === 0 ? '未选择' : `已选 ${selectedItemIds.length} 个`}
                        </span>
                        <button
                          type="button"
                          onClick={() => {
                            const filteredItemIds = items
                              .filter((item) => {
                                if (!itemSearchText) return true
                                const search = itemSearchText.toLowerCase()
                                return (item.title || '').toLowerCase().includes(search) || item.item_id.includes(search)
                              })
                              .map((item) => item.item_id)
                            if (selectedItemIds.length === filteredItemIds.length) {
                              setSelectedItemIds([])
                            } else {
                              setSelectedItemIds(filteredItemIds)
                            }
                          }}
                          className="text-xs text-blue-600 hover:text-blue-700"
                        >
                          {selectedItemIds.length === items.filter((item) => {
                            if (!itemSearchText) return true
                            const search = itemSearchText.toLowerCase()
                            return (item.title || '').toLowerCase().includes(search) || item.item_id.includes(search)
                          }).length && items.length > 0 ? '取消全选' : '全选商品'}
                        </button>
                      </div>
                      <div className="border border-gray-200 dark:border-gray-700 rounded-lg max-h-32 overflow-y-auto">
                        <label className="flex items-center gap-3 p-2 hover:bg-gray-50 dark:hover:bg-gray-800 cursor-pointer border-b border-gray-100 dark:border-gray-700">
                          <input
                            type="checkbox"
                            checked={selectedItemIds.length === 0}
                            onChange={() => setSelectedItemIds([])}
                            className="w-4 h-4 rounded border-gray-300"
                          />
                          <span className="text-sm text-gray-700 dark:text-gray-300">通用关键词（所有商品）</span>
                        </label>
                        {items
                          .filter((item) => {
                            if (!itemSearchText) return true
                            const search = itemSearchText.toLowerCase()
                            return (item.title || '').toLowerCase().includes(search) || item.item_id.includes(search)
                          })
                          .map((item) => (
                            <label
                              key={item.item_id}
                              className="flex items-center gap-3 p-2 hover:bg-gray-50 dark:hover:bg-gray-800 cursor-pointer border-b border-gray-100 dark:border-gray-700 last:border-b-0"
                            >
                              <input
                                type="checkbox"
                                checked={selectedItemIds.includes(item.item_id)}
                                onChange={() => {
                                  setSelectedItemIds((prev) =>
                                    prev.includes(item.item_id)
                                      ? prev.filter((id) => id !== item.item_id)
                                      : [...prev, item.item_id]
                                  )
                                }}
                                className="w-4 h-4 rounded border-gray-300"
                              />
                              <span className="text-sm text-gray-700 dark:text-gray-300 truncate">
                                {item.item_id} - {item.title}
                              </span>
                            </label>
                          ))}
                      </div>
                      <p className="text-xs text-slate-500 dark:text-slate-400 mt-1">
                        {selectedItemIds.length === 0
                          ? '未选择商品，将创建通用关键词'
                          : `已选择 ${selectedItemIds.length} 个商品，将创建 ${selectedItemIds.length} 条关键词`}
                      </p>
                    </>
                  )}
                </div>
                <div>
                  <label className="input-label">回复内容</label>
                  <textarea
                    value={replyText}
                    onChange={(e) => setReplyText(e.target.value)}
                    className="input-ios h-28 resize-none"
                    placeholder="请输入自动回复内容，留空表示不回复"
                  />
                  <p className="text-xs text-slate-500 dark:text-slate-400 mt-1">
                    回复内容留空时，匹配到关键词但不会自动回复，可用于屏蔽特定消息
                  </p>
                  <p className="text-xs text-blue-500 dark:text-blue-400 mt-1">
                    💡 支持变量：{'{send_user_name}'} 用户昵称、{'{send_user_id}'} 用户ID、{'{send_message}'} 用户消息内容
                  </p>
                  <p className="text-xs text-blue-500 dark:text-blue-400 mt-1">
                    💡 使用 ###### 分隔可拆分为多条消息依次发送，例如：第一条消息######第二条消息
                  </p>
                </div>

              </div>
              <div className="modal-footer">
                <button
                  type="button"
                  onClick={() => setIsModalOpen(false)}
                  className="btn-ios-secondary"
                  disabled={saving}
                >
                  取消
                </button>
                <button
                  type="submit"
                  className="btn-ios-primary"
                  disabled={saving}
                >
                  {saving ? '保存中...' : '保存'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* 图片关键词弹窗 */}
      {isImageModalOpen && (
        <div className="modal-overlay">
          <div className="modal-content max-w-lg">
            <div className="modal-header flex items-center justify-between">
              <h2 className="text-lg font-semibold flex items-center gap-2">
                <Image className="w-5 h-5 text-blue-500" />
                添加图片关键词
              </h2>
              <button
                type="button"
                onClick={() => setIsImageModalOpen(false)}
                className="p-1 hover:bg-slate-100 dark:hover:bg-slate-700 rounded-lg transition-colors"
              >
                <svg className="w-5 h-5 text-slate-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>
            <form onSubmit={handleImageSubmit} className="flex flex-col flex-1 min-h-0">
              <div className="modal-body space-y-4 overflow-y-auto">
                {/* 关键词输入 */}
                <div>
                  <label className="input-label">关键词 <span className="text-red-500">*</span></label>
                  <input
                    type="text"
                    value={imageKeyword}
                    onChange={(e) => setImageKeyword(e.target.value)}
                    className="input-ios"
                    placeholder="例如：图片、照片"
                  />
                  <p className="text-xs text-slate-500 dark:text-slate-400 mt-1">用户发送此关键词时将回复上传的图片</p>
                </div>

                {/* 图片上传区域 */}
                <div>
                  <label className="input-label">上传图片 <span className="text-red-500">*</span></label>
                  <div 
                    className="border-2 border-dashed border-slate-300 dark:border-slate-600 rounded-lg p-4 text-center hover:border-blue-400 dark:hover:border-blue-500 transition-colors cursor-pointer"
                    onClick={() => imageInputRef.current?.click()}
                  >
                    {imagePreview ? (
                      <div className="flex flex-col items-center">
                        <img src={imagePreview} alt="预览" className="max-h-32 rounded-lg mb-2" />
                        <p className="text-sm text-slate-600 dark:text-slate-400">{imageFile?.name}</p>
                        <p className="text-xs text-blue-500 mt-1">点击更换图片</p>
                      </div>
                    ) : (
                      <div className="py-4">
                        <Image className="w-10 h-10 text-slate-400 mx-auto mb-2" />
                        <p className="text-sm text-slate-600 dark:text-slate-400">点击选择图片</p>
                        <p className="text-xs text-slate-400 dark:text-slate-500 mt-1">支持 JPG、PNG、GIF，不超过 5MB</p>
                      </div>
                    )}
                  </div>
                  <input
                    ref={imageInputRef}
                    type="file"
                    accept="image/*"
                    className="hidden"
                    onChange={handleImageFileChange}
                  />
                </div>

                {/* 关联商品 */}
                <div>
                  <label className="input-label">关联商品（可选）</label>
                  <div className="relative mb-2">
                    <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
                    <input
                      type="text"
                      value={imageItemSearchText}
                      onChange={(e) => setImageItemSearchText(e.target.value)}
                      placeholder="搜索商品..."
                      className="input-ios pl-9 py-2 text-sm"
                    />
                  </div>
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-xs text-gray-500">
                      {imageSelectedItemIds.length === 0 ? '未选择' : `已选 ${imageSelectedItemIds.length} 个`}
                    </span>
                    <button
                      type="button"
                      onClick={() => {
                        const filteredItemIds = items
                          .filter((item) => {
                            if (!imageItemSearchText) return true
                            const search = imageItemSearchText.toLowerCase()
                            return (item.title || '').toLowerCase().includes(search) || item.item_id.includes(search)
                          })
                          .map((item) => item.item_id)
                        if (imageSelectedItemIds.length === filteredItemIds.length) {
                          setImageSelectedItemIds([])
                        } else {
                          setImageSelectedItemIds(filteredItemIds)
                        }
                      }}
                      className="text-xs text-blue-600 hover:text-blue-700"
                    >
                      {imageSelectedItemIds.length === items.filter((item) => {
                        if (!imageItemSearchText) return true
                        const search = imageItemSearchText.toLowerCase()
                        return (item.title || '').toLowerCase().includes(search) || item.item_id.includes(search)
                      }).length && items.length > 0 ? '取消全选' : '全选商品'}
                    </button>
                  </div>
                  <div className="border border-gray-200 dark:border-gray-700 rounded-lg max-h-32 overflow-y-auto">
                    <label className="flex items-center gap-3 p-2 hover:bg-gray-50 dark:hover:bg-gray-800 cursor-pointer border-b border-gray-100 dark:border-gray-700">
                      <input
                        type="checkbox"
                        checked={imageSelectedItemIds.length === 0}
                        onChange={() => setImageSelectedItemIds([])}
                        className="w-4 h-4 rounded border-gray-300"
                      />
                      <span className="text-sm text-gray-700 dark:text-gray-300">通用关键词（所有商品）</span>
                    </label>
                    {items
                      .filter((item) => {
                        if (!imageItemSearchText) return true
                        const search = imageItemSearchText.toLowerCase()
                        return (item.title || '').toLowerCase().includes(search) || item.item_id.includes(search)
                      })
                      .map((item) => (
                        <label
                          key={item.item_id}
                          className="flex items-center gap-3 p-2 hover:bg-gray-50 dark:hover:bg-gray-800 cursor-pointer border-b border-gray-100 dark:border-gray-700 last:border-b-0"
                        >
                          <input
                            type="checkbox"
                            checked={imageSelectedItemIds.includes(item.item_id)}
                            onChange={() => {
                              setImageSelectedItemIds((prev) =>
                                prev.includes(item.item_id)
                                  ? prev.filter((id) => id !== item.item_id)
                                  : [...prev, item.item_id]
                              )
                            }}
                            className="w-4 h-4 rounded border-gray-300"
                          />
                          <span className="text-sm text-gray-700 dark:text-gray-300 truncate">
                            {item.item_id} - {item.title}
                          </span>
                        </label>
                      ))}
                  </div>
                  <p className="text-xs text-slate-500 dark:text-slate-400 mt-1">
                    {imageSelectedItemIds.length === 0
                      ? '未选择商品，将创建通用关键词'
                      : `已选择 ${imageSelectedItemIds.length} 个商品，将创建 ${imageSelectedItemIds.length} 条关键词`}
                  </p>
                </div>

                {/* 说明提示 */}
                <div className="bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-lg p-3">
                  <div className="flex items-start gap-2">
                    <Info className="w-4 h-4 text-blue-500 mt-0.5 flex-shrink-0" />
                    <div className="text-sm text-blue-700 dark:text-blue-300">
                      <p className="font-medium mb-1">说明：</p>
                      <ul className="list-disc list-inside space-y-0.5 text-xs">
                        <li>图片关键词优先级高于文本关键词</li>
                        <li>用户发送匹配的关键词时，系统将回复上传的图片</li>
                        <li>图片将被转换为适合聊天的格式</li>
                      </ul>
                    </div>
                  </div>
                </div>
              </div>
              <div className="modal-footer">
                <button
                  type="button"
                  onClick={() => setIsImageModalOpen(false)}
                  className="btn-ios-secondary"
                  disabled={savingImage}
                >
                  取消
                </button>
                <button
                  type="submit"
                  className="btn-ios-primary"
                  disabled={savingImage}
                >
                  {savingImage ? '添加中...' : '添加图片关键词'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* 图片预览弹窗 */}
      {isImagePreviewOpen && (
        <div
          className="fixed inset-0 bg-black/80 flex items-center justify-center z-50 p-4"
          onClick={() => setIsImagePreviewOpen(false)}
        >
          <div className="relative max-w-4xl max-h-[90vh]" onClick={(e) => e.stopPropagation()}>
            <button
              onClick={() => setIsImagePreviewOpen(false)}
              className="absolute -top-10 right-0 text-white hover:text-gray-300 text-sm"
            >
              关闭 ✕
            </button>
            <img
              src={previewImageUrl}
              alt="关键词图片"
              className="max-w-full max-h-[90vh] object-contain rounded-lg"
            />
          </div>
        </div>
      )}

      {/* 删除确认弹窗 */}
      <ConfirmModal
        isOpen={deleteConfirm.open}
        title="删除确认"
        message="确定要删除这个关键词吗？删除后无法恢复。"
        confirmText="删除"
        cancelText="取消"
        type="danger"
        loading={deleting}
        onConfirm={() => deleteConfirm.keyword && handleDelete(deleteConfirm.keyword)}
        onCancel={() => setDeleteConfirm({ open: false, keyword: null })}
      />

      {/* 批量删除确认弹窗 */}
      <ConfirmModal
        isOpen={batchDeleteConfirm}
        title="批量删除确认"
        message={`确定要删除选中的 ${selectedKeywordIds.size} 个关键词吗？删除后无法恢复。`}
        confirmText="删除"
        cancelText="取消"
        type="danger"
        loading={deleting}
        onConfirm={handleBatchDelete}
        onCancel={() => setBatchDeleteConfirm(false)}
      />
    </div>
  )
}
