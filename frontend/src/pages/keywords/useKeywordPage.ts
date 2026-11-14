/** 自动回复页面原有关键词状态与操作，API配置通过独立组件管理。 */
import { useState, useEffect } from 'react'
import type { FormEvent } from 'react'
import { getKeywords, deleteKeyword, saveKeywords, updateKeyword } from '@/api/keywords'
import { getAccountDetails } from '@/api/accounts'
import { getItems } from '@/api/items'
import { useUIStore } from '@/store/uiStore'
import { useAuthStore } from '@/store/authStore'
import type { Keyword, Account, Item } from '@/types'
import { getUserSetting } from '@/api/settings'
import { DEFAULT_LOCATION_TITLE, type LocationContactReplyValue } from '@/pages/common/LocationContactReplyFields'
import { useKeywordImageForm } from './useKeywordImageForm'
import { useKeywordTransfer } from './useKeywordTransfer'

/** 解析关键词文本域，按行保存是为了兼容旧表结构的一条关键词一条规则。 */
export const parseKeywordLines = (value: string) => value.split(/\r?\n/).map(line => line.trim()).filter(Boolean)

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

export function useKeywordPage() {
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
  const [replyType, setReplyType] = useState<'text' | 'external_contact'>('text')
  const [location, setLocation] = useState<LocationContactReplyValue>({
    location_name: '',
    location_longitude: '',
    location_latitude: '',
    location_title: DEFAULT_LOCATION_TITLE,
    location_subtitle: '',
  })
  const [itemIdText, setItemIdText] = useState('')  // 绑定的商品ID（编辑时使用）
  const [selectedItemIds, setSelectedItemIds] = useState<string[]>([])  // 多选商品ID（新增时使用）
  const [itemSearchText, setItemSearchText] = useState('')  // 商品搜索
  const [saving, setSaving] = useState(false)
  
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
    setReplyType('text')
    setLocation({ location_name: '', location_longitude: '', location_latitude: '', location_title: DEFAULT_LOCATION_TITLE, location_subtitle: '' })
    setItemIdText('')
    setSelectedItemIds([])
    setItemSearchText('')
    setIsModalOpen(true)
  }

  const openExternalContactModal = () => {
    if (!selectedAccount) {
      addToast({ type: 'warning', message: '请先选择具体账号才能添加关键词' })
      return
    }
    openAddModal()
    setReplyType('external_contact')
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
    setReplyType(keyword.type === 'external_contact' ? 'external_contact' : 'text')
    setLocation({
      location_name: keyword.location_name || '',
      location_longitude: keyword.location_longitude || '',
      location_latitude: keyword.location_latitude || '',
      location_title: keyword.location_title || DEFAULT_LOCATION_TITLE,
      location_subtitle: keyword.location_subtitle || '',
    })
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

    if (replyType === 'external_contact') {
      try {
        const [urlResult, secretResult] = await Promise.all([
          getUserSetting('location_chat.remote_url'),
          getUserSetting('location_chat.remote_secret_key'),
        ])
        if (!urlResult.value?.trim() || !secretResult.value?.trim()) {
          addToast({ type: 'warning', message: '请先到个人设置的远程URL配置中填写位置聊天配置的远程URL和秘钥' })
          return
        }
      } catch {
        addToast({ type: 'error', message: '无法读取个人设置，请先配置位置聊天远程URL和秘钥' })
        return
      }

      if (!location.location_title.trim()) {
        setLocation((current) => ({ ...current, location_title: DEFAULT_LOCATION_TITLE }))
      }
    }

    // 回复内容允许留空：留空表示命中关键词但不回复，用于屏蔽特定消息

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
            type: replyType,
            ...location,
            location_title: location.location_title.trim() || DEFAULT_LOCATION_TITLE,
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
          type: replyType,
          ...location,
          location_title: location.location_title.trim() || DEFAULT_LOCATION_TITLE,
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

  const imageForm = useKeywordImageForm(selectedAccount, loadKeywords)
  const transfer = useKeywordTransfer(selectedAccount, loadKeywords)

  return { loading, setLoading, keywords, setKeywords, accounts, setAccounts, items, setItems, selectedAccount, setSelectedAccount, formAccountId, setFormAccountId, isModalOpen, setIsModalOpen, editingKeyword, setEditingKeyword, keywordText, setKeywordText, replyText, setReplyText, replyType, setReplyType, location, setLocation, itemIdText, setItemIdText, selectedItemIds, setSelectedItemIds, itemSearchText, setItemSearchText, saving, setSaving, isImagePreviewOpen, setIsImagePreviewOpen, previewImageUrl, setPreviewImageUrl, selectedKeywordIds, setSelectedKeywordIds, deleteConfirm, setDeleteConfirm, batchDeleteConfirm, setBatchDeleteConfirm, deleting, setDeleting, currentPage, setCurrentPage, pageSize, setPageSize, totalPages, paginatedKeywords, getKeywordAccountId, handlePageChange, handlePageSizeChange, loadKeywords, loadAccounts, loadItems, openAddModal, openExternalContactModal, openEditModal, handleSubmit, handleDelete, getKeywordUniqueId, toggleKeywordSelect, toggleSelectAllKeywords, handleBatchDelete, ...imageForm, ...transfer }
}
