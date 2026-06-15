import { useState, useEffect, useRef } from 'react'
import type { FormEvent, ChangeEvent } from 'react'
import { MessageSquare, RefreshCw, Plus, Upload, Download, Info, Image } from 'lucide-react'
import { Button, Empty, Form, Input, Modal, Popconfirm, Select as ArcoSelect, Space, Table, Tag, Tooltip, type TableColumnProps } from '@arco-design/web-react'
import { getKeywords, deleteKeyword, addKeyword, updateKeyword, exportKeywords, importKeywords as importKeywordsApi, addImageKeyword } from '@/api/keywords'
import { getAccounts } from '@/api/accounts'
import { getItems } from '@/api/items'
import { useUIStore } from '@/store/uiStore'
import { PageLoading } from '@/components/common/Loading'
import { useAuthStore } from '@/store/authStore'
import type { Keyword, Account, Item } from '@/types'

interface KeywordTableRow extends Keyword {
  key: string | number
}

export function Keywords() {
  const { addToast } = useUIStore()
  const { isAuthenticated, token, _hasHydrated } = useAuthStore()
  const [loading, setLoading] = useState(true)
  const [keywords, setKeywords] = useState<Keyword[]>([])
  const [accounts, setAccounts] = useState<Account[]>([])
  const [items, setItems] = useState<Item[]>([])
  const [selectedAccount, setSelectedAccount] = useState('')
  const [isModalOpen, setIsModalOpen] = useState(false)
  const [editingKeyword, setEditingKeyword] = useState<Keyword | null>(null)
  const [keywordText, setKeywordText] = useState('')
  const [replyText, setReplyText] = useState('')
  const [itemIdText, setItemIdText] = useState('')  // 绑定的商品ID
  const [saving, setSaving] = useState(false)
  const [importing, setImporting] = useState(false)
  const [exporting, setExporting] = useState(false)
  const importInputRef = useRef<HTMLInputElement | null>(null)

  // 图片关键词相关状态
  const [isImageModalOpen, setIsImageModalOpen] = useState(false)
  const [imageKeyword, setImageKeyword] = useState('')
  const [imageItemId, setImageItemId] = useState('')
  const [imageFile, setImageFile] = useState<File | null>(null)
  const [imagePreview, setImagePreview] = useState<string>('')
  const [savingImage, setSavingImage] = useState(false)
  const imageInputRef = useRef<HTMLInputElement | null>(null)

  // 图片预览弹窗状态
  const [isImagePreviewOpen, setIsImagePreviewOpen] = useState(false)
  const [previewImageUrl, setPreviewImageUrl] = useState('')

  const loadKeywords = async () => {
    if (!_hasHydrated || !isAuthenticated || !token) {
      return
    }
    if (!selectedAccount) {
      setKeywords([])
      setLoading(false)
      return
    }
    try {
      setLoading(true)
      const data = await getKeywords(selectedAccount)
      // 确保 data 是数组，防止后端返回非数组或请求失败时出错
      setKeywords(Array.isArray(data) ? data : [])
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
      const data = await getAccounts()
      setAccounts(data)
      if (data.length > 0) {
        if (!selectedAccount) {
          setSelectedAccount(data[0].id)
        }
      } else {
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
  }, [_hasHydrated, isAuthenticated, token])

  useEffect(() => {
    if (!_hasHydrated || !isAuthenticated || !token) return
    if (selectedAccount) {
      loadKeywords()
      loadItems()
    }
  }, [_hasHydrated, isAuthenticated, token, selectedAccount])

  const loadItems = async () => {
    if (!selectedAccount) {
      setItems([])
      return
    }
    try {
      const result = await getItems(selectedAccount)
      setItems(result.data || [])
    } catch {
      setItems([])
    }
  }

  const openAddModal = () => {
    if (!selectedAccount) {
      addToast({ type: 'warning', message: '请先选择账号' })
      return
    }
    setEditingKeyword(null)
    setKeywordText('')
    setReplyText('')
    setItemIdText('')
    setIsModalOpen(true)
  }

  const openEditModal = (keyword: Keyword) => {
    // 图片关键词不支持编辑
    if (keyword.type === 'image') {
      addToast({ type: 'warning', message: '图片关键词不支持编辑，请删除后重新添加' })
      return
    }

    setEditingKeyword(keyword)
    setKeywordText(keyword.keyword)
    setReplyText(keyword.reply)
    setItemIdText(keyword.item_id || '')
    setIsModalOpen(true)
  }

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()

    if (!selectedAccount) {
      addToast({ type: 'warning', message: '请先选择账号' })
      return
    }

    if (!keywordText.trim()) {
      addToast({ type: 'warning', message: '请输入关键词' })
      return
    }

    if (!replyText.trim()) {
      addToast({ type: 'warning', message: '请输入回复内容' })
      return
    }

    try {
      setSaving(true)

      if (editingKeyword) {
        const result = await updateKeyword(
          selectedAccount,
          editingKeyword.keyword,
          editingKeyword.item_id || '',
          {
            keyword: keywordText.trim(),
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
        const result = await addKeyword(selectedAccount, {
          keyword: keywordText.trim(),
          reply: replyText.trim(),
          item_id: itemIdText.trim(),
        })
        if (result.success === false) {
          addToast({ type: 'error', message: result.message || '添加失败' })
          return
        }
        addToast({ type: 'success', message: '关键词已添加' })
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
      // 后端返回 { msg, total, added, updated } 格式
      const resultData = result as unknown as { msg?: string; added?: number; updated?: number; success?: boolean; message?: string }
      if (resultData.msg || resultData.added !== undefined) {
        addToast({
          type: 'success',
          message: `导入成功：新增 ${resultData.added ?? 0} 条，更新 ${resultData.updated ?? 0} 条`,
        })
        await loadKeywords()
      } else if (resultData.success === false) {
        addToast({ type: 'error', message: resultData.message || '导入失败' })
      } else {
        addToast({ type: 'error', message: '导入失败' })
      }
    } catch {
      addToast({ type: 'error', message: '导入关键词失败' })
    } finally {
      setImporting(false)
      event.target.value = ''
    }
  }

  const handleDelete = async (keyword: Keyword) => {
    try {
      await deleteKeyword(selectedAccount, keyword.keyword, keyword.item_id || '')
      addToast({ type: 'success', message: '删除成功' })
      loadKeywords()
    } catch {
      addToast({ type: 'error', message: '删除失败' })
    }
  }

  // 图片关键词功能
  const openImageModal = () => {
    if (!selectedAccount) {
      addToast({ type: 'warning', message: '请先选择账号' })
      return
    }
    setImageKeyword('')
    setImageItemId('')
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
      const result = await addImageKeyword(
        selectedAccount,
        imageKeyword.trim(),
        imageFile,
        imageItemId.trim() || undefined
      )
      // 后端返回 { msg, keyword, image_url, item_id }
      if (result && (result as unknown as { keyword?: string }).keyword) {
        addToast({ type: 'success', message: '图片关键词添加成功' })
        setIsImageModalOpen(false)
        loadKeywords()
      } else {
        addToast({ type: 'error', message: '添加失败' })
      }
    } catch (err) {
      const error = err as { response?: { data?: { detail?: string } } }
      addToast({ type: 'error', message: error.response?.data?.detail || '添加图片关键词失败' })
    } finally {
      setSavingImage(false)
    }
  }

  const columns: TableColumnProps<KeywordTableRow>[] = [
    {
      title: '关键词',
      dataIndex: 'keyword',
      width: 180,
      render: (value: string) => (
        <code>
          {value}
        </code>
      ),
    },
    {
      title: '商品ID',
      dataIndex: 'item_id',
      width: 180,
      render: (itemId?: string) => (
        itemId ? (
          <span className="text-xs text-slate-500 dark:text-slate-400">{itemId}</span>
        ) : (
          <span className="text-xs text-gray-400">通用</span>
        )
      ),
    },
    {
      title: '回复内容',
      dataIndex: 'reply',
      width: 320,
      render: (_value, keyword) => (
        keyword.type === 'image' ? (
          <Button
            type="text"
            className="accounts-table-action-btn"
            onClick={() => {
              setPreviewImageUrl(keyword.image_url || '')
              setIsImagePreviewOpen(true)
            }}
          >
            查看大图
          </Button>
        ) : (
          <p className="truncate text-slate-600 dark:text-slate-300" title={keyword.reply}>
            {keyword.reply || <span className="text-gray-400">不回复</span>}
          </p>
        )
      ),
    },
    {
      title: '类型',
      dataIndex: 'type',
      width: 100,
      render: (type?: string) => (
        type === 'image' ? (
          <Tag color="arcoblue" style={{ borderRadius: 4 }}>图片</Tag>
        ) : (
          <Tag color="gray" style={{ borderRadius: 4 }}>文本</Tag>
        )
      ),
    },
    {
      title: '操作',
      dataIndex: 'operation',
      width: 140,
      fixed: 'right',
      render: (_value, keyword) => (
        <Space size={4}>
          <Button
            type="text"
            size="mini"
            onClick={() => openEditModal(keyword)}
            disabled={keyword.type === 'image'}
          >
            编辑
          </Button>
          <Popconfirm
            title="确定要删除这个关键词吗？"
            okText="删除"
            cancelText="取消"
            okButtonProps={{ status: 'danger' }}
            onOk={() => handleDelete(keyword)}
          >
            <Button
              type="text"
              size="mini"
              className="!text-red-500 hover:!text-red-500"
            >
              删除
            </Button>
          </Popconfirm>
        </Space>
      ),
    },
  ]

  const tableData: KeywordTableRow[] = keywords.map((keyword, index) => ({
    ...keyword,
    key: keyword.id || `keyword-${index}`,
  }))

  if (loading && accounts.length === 0) {
    return <PageLoading />
  }

  return (
    <div className="space-y-4">
      {/* Keywords List */}
      <div
        className="vben-card"
      >

        {/* 标题区 */}
        <div className="accounts-page-intro">
          <h1 className="page-title">自动回复</h1>
          <p className="page-description">管理关键词自动回复规则</p>
        </div>

        {/* 筛选区 */}
        <div className="table-toolbar">
          <div className="table-filter-row table-filter-row--lined">
            <Form layout="inline" className="table-filter-form">
              <Form.Item label="选择账号">
                <ArcoSelect
                  allowClear
                  value={selectedAccount || undefined}
                  onChange={(value) => setSelectedAccount(value || '')}
                  placeholder="所有账号"
                  style={{ width: 180 }}
                  options={[
                    { value: '', label: '所有账号' },
                    ...accounts.map((account) => ({
                      value: account.id,
                      label: account.id,
                    })),
                  ]}
                />
              </Form.Item>
            </Form>
            <div className="reply-toolbar-actions">
              <Tooltip
                trigger="click"
                position="top"
                color="#eef6ff"
                className="reply-variable-popover"
                content={(
                  <div className="reply-variable-tooltip-content">
                    <div className="reply-variable-tooltip-title">支持变量替换</div>
                    <div className="reply-variable-tooltip-row">
                      <code>{'{send_user_name}'}</code>
                      <span>用户昵称</span>
                    </div>
                    <div className="reply-variable-tooltip-row">
                      <code>{'{send_user_id}'}</code>
                      <span>用户ID</span>
                    </div>
                    <div className="reply-variable-tooltip-row">
                      <code>{'{send_message}'}</code>
                      <span>用户消息内容</span>
                    </div>
                  </div>
                )}
              >
                <Button className="reply-variable-trigger" aria-label="查看变量说明">
                  <Info />
                  <span>变量说明</span>
                </Button>
              </Tooltip>
              <Button
                type="primary"
                onClick={openAddModal}
                className="accounts-header-btn"
              >
                <Plus />
                <span>添加文本关键词</span>
              </Button>
              <Button
                type="primary"
                onClick={openImageModal}
                className="accounts-header-btn"
              >
                <Image className="w-4 h-4" />
                添加图片关键词
              </Button>
            </div>
          </div>

          {/* 按钮区 */}
          <div className="table-action-row">
            <Space className="batch-actions">
              <Button
                onClick={handleExport}
                disabled={!selectedAccount || exporting}
                className="accounts-header-btn"
              >
                <Upload />
                导出
              </Button>
              <Button
                onClick={handleImportButtonClick}
                disabled={!selectedAccount || importing}
                className="accounts-header-btn"
              >
                <Download />
                导入
              </Button>
              <Button onClick={loadKeywords} className="accounts-header-btn">
                <RefreshCw />
                刷新
              </Button>
              <input
                ref={importInputRef}
                type="file"
                accept=".xlsx,.xls"
                className="hidden"
                onChange={handleImportFileChange}
              />
            </Space>
          </div>
        </div>
        <Table
          rowKey="key"
          columns={columns}
          data={selectedAccount && !loading ? tableData : []}
          pagination={false}
          border={false}
          scroll={{ x: 920 }}
          className="accounts-arco-table table-main"
          noDataElement={(
            <Empty
              icon={<MessageSquare className="w-12 h-12 text-gray-300" />}
              description={!selectedAccount ? '请先选择一个账号' : loading ? '加载中...' : '暂无关键词，点击上方按钮添加'}
            />
          )}
        />
      </div>

      <Modal
        visible={isModalOpen}
        title={editingKeyword ? '编辑关键词' : '添加关键词'}
        onCancel={() => setIsModalOpen(false)}
        footer={null}
        unmountOnExit
        style={{ width: 720 }}
      >
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="input-label">所属账号</label>
            <Input
              value={selectedAccount}
              disabled
            />
          </div>
          <div>
            <label className="input-label">关键词</label>
            <Input
              value={keywordText}
              onChange={setKeywordText}
              placeholder="请输入关键词"
            />
          </div>
          <div>
            <label className="input-label">商品ID（可选）</label>
            <ArcoSelect
              value={itemIdText}
              onChange={(value) => setItemIdText(value || '')}
              placeholder="通用关键词（所有商品）"
              allowClear
              options={[
                { value: '', label: '通用关键词（所有商品）' },
                ...items.map((item) => ({
                  value: item.item_id,
                  label: `${item.item_id} - ${item.title || item.item_title || '未命名商品'}`,
                })),
              ]}
            />
            <p className="text-xs text-slate-500 dark:text-slate-400 mt-1">
              绑定商品ID后，此关键词仅在该商品对话中生效
            </p>
          </div>
          <div>
            <label className="input-label">回复内容</label>
            <Input.TextArea
              value={replyText}
              onChange={setReplyText}
              placeholder="请输入自动回复内容，留空表示不回复"
              autoSize={{ minRows: 5, maxRows: 8 }}
            />
            <p className="text-xs text-slate-500 dark:text-slate-400 mt-1">
              回复内容留空时，匹配到关键词但不会自动回复，可用于屏蔽特定消息
            </p>
          </div>
          <div className="flex justify-end gap-3 pt-2">
            <Button onClick={() => setIsModalOpen(false)} disabled={saving}>
              取消
            </Button>
            <Button htmlType="submit" type="primary" disabled={saving}>
              {saving ? '保存中...' : '保存'}
            </Button>
          </div>
        </form>
      </Modal>

      {/* 图片关键词弹窗 */}
      <Modal
        visible={isImageModalOpen}
        title={(
          <span className="flex items-center gap-2">
            <Image className="w-5 h-5 text-blue-500" />
            添加图片关键词
          </span>
        )}
        onCancel={() => setIsImageModalOpen(false)}
        footer={null}
        unmountOnExit
        style={{ width: 640 }}
      >
        <form onSubmit={handleImageSubmit} className="space-y-4">
          <div>
            <label className="input-label">关键词 <span className="text-red-500">*</span></label>
            <Input
              value={imageKeyword}
              onChange={setImageKeyword}
              placeholder="例如：图片、照片"
            />
            <p className="text-xs text-slate-500 dark:text-slate-400 mt-1">用户发送此关键词时将回复上传的图片</p>
          </div>
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
          <div>
            <label className="input-label">关联商品（可选）</label>
            <ArcoSelect
              value={imageItemId}
              onChange={(value) => setImageItemId(value || '')}
              placeholder="通用关键词（所有商品）"
              allowClear
              options={[
                { value: '', label: '通用关键词（所有商品）' },
                ...items.map((item) => ({
                  value: item.item_id,
                  label: `${item.item_id} - ${item.title || item.item_title || '未命名商品'}`,
                })),
              ]}
            />
            <p className="text-xs text-slate-500 dark:text-slate-400 mt-1">填写商品ID后，此关键词仅在该商品对话中生效</p>
          </div>
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
          <div className="flex justify-end gap-3 pt-2">
            <Button onClick={() => setIsImageModalOpen(false)} disabled={savingImage}>
              取消
            </Button>
            <Button htmlType="submit" type="primary" disabled={savingImage}>
              {savingImage ? '添加中...' : '添加图片关键词'}
            </Button>
          </div>
        </form>
      </Modal>

      {/* 图片预览弹窗 */}
      <Modal
        visible={isImagePreviewOpen}
        title="图片预览"
        onCancel={() => setIsImagePreviewOpen(false)}
        footer={null}
        unmountOnExit
        style={{ width: 960 }}
      >
        <div className="flex justify-center">
          <img
            src={previewImageUrl}
            alt="关键词图片"
            className="max-w-full max-h-[70vh] object-contain rounded-lg"
          />
        </div>
      </Modal>
    </div >
  )
}
