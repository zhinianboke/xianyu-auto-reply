/**
 * 意见反馈页面
 * 
 * 功能：
 * 1. 用户提交反馈（需求、BUG、其他）
 * 2. 查看自己的反馈列表
 * 3. 管理员可查看所有反馈并标记解决
 * 4. 支持对话形式多次回复
 */
import { useState, useEffect, useRef } from 'react'
import { motion } from 'framer-motion'
import {
  MessageSquarePlus,
  RefreshCw,
  Plus,
  Trash2,
  X,
  Loader2,
  CheckCircle,
  Clock,
  Bug,
  Lightbulb,
  HelpCircle,
  Image as ImageIcon,
  Upload,
  Send,
  MessageCircle,
} from 'lucide-react'
import { 
  getFeedbacks, 
  getFeedbackDetail,
  getFeedbackStats,
  createFeedback, 
  replyFeedback,
  resolveFeedback, 
  unresolveFeedback, 
  deleteFeedback 
} from '@/api/feedback'
import type { Feedback as FeedbackType, FeedbackDetail, FeedbackStats } from '@/api/feedback'
import { getAccountDetails } from '@/api/accounts'
import { useUIStore } from '@/store/uiStore'
import { useAuthStore } from '@/store/authStore'
import { PageLoading } from '@/components/common/Loading'
import { Select } from '@/components/common/Select'
import { ConfirmModal } from '@/components/common/ConfirmModal'
import type { Account } from '@/types'

const FEEDBACK_TYPE_OPTIONS = [
  { value: 'FEATURE', label: '需求', icon: Lightbulb, color: 'text-amber-500' },
  { value: 'BUG', label: 'BUG', icon: Bug, color: 'text-red-500' },
  { value: 'OTHER', label: '其他', icon: HelpCircle, color: 'text-blue-500' },
]

export default function Feedback() {
  const { addToast } = useUIStore()
  const { user, token, isAuthenticated, _hasHydrated } = useAuthStore()

  const [loading, setLoading] = useState(true)
  const [feedbacks, setFeedbacks] = useState<FeedbackType[]>([])
  const [accounts, setAccounts] = useState<Account[]>([])
  const [total, setTotal] = useState(0)
  const [stats, setStats] = useState<FeedbackStats>({ total: 0, resolved: 0, pending: 0 })
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)
  const [filterResolved, setFilterResolved] = useState<string>('')
  const [filterType, setFilterType] = useState<string>('')

  // 新建弹窗
  const [isModalOpen, setIsModalOpen] = useState(false)
  const [formTitle, setFormTitle] = useState('')
  const [formContent, setFormContent] = useState('')
  const [formType, setFormType] = useState('OTHER')
  const [formCookieId, setFormCookieId] = useState('')
  const [formImages, setFormImages] = useState<string[]>([])
  const [saving, setSaving] = useState(false)
  const [uploading, setUploading] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)

  // 详情弹窗（对话形式）
  const [detailOpen, setDetailOpen] = useState(false)
  const [detailLoading, setDetailLoading] = useState(false)
  const [detailData, setDetailData] = useState<FeedbackDetail | null>(null)
  const [replyContent, setReplyContent] = useState('')
  const [replying, setReplying] = useState(false)
  const messagesEndRef = useRef<HTMLDivElement>(null)

  // 删除确认弹窗
  const [deleteConfirm, setDeleteConfirm] = useState<{ open: boolean; feedback: FeedbackType | null }>({
    open: false,
    feedback: null,
  })
  const [deleting, setDeleting] = useState(false)

  const loadFeedbacks = async (opts?: { resolved?: string; type?: string; pageNum?: number }) => {
    if (!_hasHydrated || !isAuthenticated || !token) return
    // 允许查询/重置按钮传入即时值，避免 setState 异步导致的旧值查询
    const resolved = opts?.resolved ?? filterResolved
    const type = opts?.type ?? filterType
    const pageNum = opts?.pageNum ?? page
    try {
      setLoading(true)
      // 并行加载列表和统计数据
      const [listResult, statsResult] = await Promise.all([
        getFeedbacks({
          page: pageNum,
          page_size: pageSize,
          is_resolved: resolved === '' ? undefined : resolved === 'true',
          feedback_type: type || undefined,
        }),
        getFeedbackStats(),
      ])
      if (listResult.success && listResult.data) {
        setFeedbacks(listResult.data.items)
        setTotal(listResult.data.total)
      }
      if (statsResult.success && statsResult.data) {
        setStats(statsResult.data)
      }
    } catch {
      addToast({ type: 'error', message: '加载反馈列表失败' })
    } finally {
      setLoading(false)
    }
  }

  const loadAccounts = async () => {
    if (!_hasHydrated || !isAuthenticated || !token) return
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
    loadFeedbacks()
  }, [_hasHydrated, isAuthenticated, token, page, pageSize])

  // 滚动到消息底部
  useEffect(() => {
    if (detailData && messagesEndRef.current) {
      messagesEndRef.current.scrollIntoView({ behavior: 'smooth' })
    }
  }, [detailData?.messages])

  // 点击「查询」按钮：用当前筛选草稿值回到第 1 页查询
  const handleSearch = () => {
    setPage(1)
    loadFeedbacks({ pageNum: 1 })
  }

  // 点击「重置」按钮：清空筛选条件并回到第 1 页重新加载
  const handleReset = () => {
    setFilterResolved('')
    setFilterType('')
    setPage(1)
    loadFeedbacks({ resolved: '', type: '', pageNum: 1 })
  }

  const openAddModal = () => {
    setFormTitle('')
    setFormContent('')
    setFormType('OTHER')
    setFormCookieId('')
    setFormImages([])
    setIsModalOpen(true)
  }

  const handleSubmit = async () => {
    if (!formTitle.trim()) {
      addToast({ type: 'warning', message: '请输入标题' })
      return
    }
    if (!formContent.trim()) {
      addToast({ type: 'warning', message: '请输入内容' })
      return
    }
    setSaving(true)
    try {
      const result = await createFeedback({
        title: formTitle.trim(),
        content: formContent.trim(),
        feedback_type: formType,
        cookie_id: formCookieId || undefined,
        images: formImages.length > 0 ? formImages : undefined,
      })
      if (result.success) {
        addToast({ type: 'success', message: '反馈提交成功' })
        setIsModalOpen(false)
        loadFeedbacks()
      } else {
        addToast({ type: 'error', message: result.message || '提交失败' })
      }
    } catch {
      addToast({ type: 'error', message: '提交失败' })
    } finally {
      setSaving(false)
    }
  }

  const handleUploadImage = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    if (!file.type.startsWith('image/')) {
      addToast({ type: 'warning', message: '请选择图片文件' })
      return
    }
    if (formImages.length >= 3) {
      addToast({ type: 'warning', message: '最多上传3张图片' })
      return
    }
    setUploading(true)
    try {
      const formData = new FormData()
      formData.append('image', file)
      const response = await fetch('/api/v1/upload/upload-image', {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}` },
        body: formData,
      })
      const result = await response.json()
      if (result.success && result.data?.image_url) {
        setFormImages([...formImages, result.data.image_url])
      } else {
        addToast({ type: 'error', message: result.message || '上传失败' })
      }
    } catch {
      addToast({ type: 'error', message: '上传失败' })
    } finally {
      setUploading(false)
      e.target.value = ''
    }
  }

  // 打开详情弹窗
  const openDetail = async (fb: FeedbackType) => {
    setDetailOpen(true)
    setDetailLoading(true)
    setReplyContent('')
    try {
      const result = await getFeedbackDetail(fb.id)
      if (result.success && result.data) {
        setDetailData(result.data)
      } else {
        addToast({ type: 'error', message: result.message || '获取详情失败' })
        setDetailOpen(false)
      }
    } catch {
      addToast({ type: 'error', message: '获取详情失败' })
      setDetailOpen(false)
    } finally {
      setDetailLoading(false)
    }
  }

  // 发送回复
  const handleReply = async () => {
    if (!replyContent.trim() || !detailData) return
    setReplying(true)
    try {
      const result = await replyFeedback(detailData.id, replyContent.trim())
      if (result.success) {
        setReplyContent('')
        // 重新加载详情
        const detailResult = await getFeedbackDetail(detailData.id)
        if (detailResult.success && detailResult.data) {
          setDetailData(detailResult.data)
        }
      } else {
        addToast({ type: 'error', message: result.message || '回复失败' })
      }
    } catch {
      addToast({ type: 'error', message: '回复失败' })
    } finally {
      setReplying(false)
    }
  }

  const handleResolve = async () => {
    if (!detailData) return
    try {
      const result = await resolveFeedback(detailData.id)
      if (result.success) {
        addToast({ type: 'success', message: '已标记为解决' })
        setDetailOpen(false)
        loadFeedbacks()
      } else {
        addToast({ type: 'error', message: result.message || '操作失败' })
      }
    } catch {
      addToast({ type: 'error', message: '操作失败' })
    }
  }

  const handleUnresolve = async () => {
    if (!detailData) return
    try {
      const result = await unresolveFeedback(detailData.id)
      if (result.success) {
        addToast({ type: 'success', message: '已标记为未解决' })
        setDetailOpen(false)
        loadFeedbacks()
      } else {
        addToast({ type: 'error', message: result.message || '操作失败' })
      }
    } catch {
      addToast({ type: 'error', message: '操作失败' })
    }
  }

  const handleDelete = async (fb: FeedbackType) => {
    setDeleting(true)
    try {
      const result = await deleteFeedback(fb.id)
      if (result.success) {
        addToast({ type: 'success', message: '删除成功' })
        setDeleteConfirm({ open: false, feedback: null })
        loadFeedbacks()
      } else {
        addToast({ type: 'error', message: result.message || '删除失败' })
      }
    } catch {
      addToast({ type: 'error', message: '删除失败' })
    } finally {
      setDeleting(false)
    }
  }

  const getTypeInfo = (type: string) => {
    return FEEDBACK_TYPE_OPTIONS.find((t) => t.value === type) || FEEDBACK_TYPE_OPTIONS[2]
  }

  if (loading && feedbacks.length === 0) {
    return <PageLoading />
  }

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="page-title">意见反馈</h1>
          <p className="page-description">提交您的需求、BUG或建议</p>
        </div>
        <div className="flex gap-3">
          <button onClick={openAddModal} className="btn-ios-primary">
            <Plus className="w-4 h-4" />
            提交反馈
          </button>
          <button onClick={loadFeedbacks} className="btn-ios-secondary">
            <RefreshCw className="w-4 h-4" />
            刷新
          </button>
        </div>
      </div>

      {/* 统计卡片 */}
      <div className="grid grid-cols-3 gap-3 sm:gap-4">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0, duration: 0.3 }}
          className="stat-card"
        >
          <div className="stat-icon-primary">
            <MessageSquarePlus className="w-6 h-6" />
          </div>
          <div>
            <p className="stat-value">{stats.total}</p>
            <p className="stat-label">总反馈</p>
          </div>
        </motion.div>
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.1, duration: 0.3 }}
          className="stat-card"
        >
          <div className="stat-icon-success">
            <CheckCircle className="w-6 h-6" />
          </div>
          <div>
            <p className="stat-value">{stats.resolved}</p>
            <p className="stat-label">已解决</p>
          </div>
        </motion.div>
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.2, duration: 0.3 }}
          className="stat-card"
        >
          <div className="stat-icon-warning">
            <Clock className="w-6 h-6" />
          </div>
          <div>
            <p className="stat-value">{stats.pending}</p>
            <p className="stat-label">待解决</p>
          </div>
        </motion.div>
      </div>

      {/* 筛选 */}
      <div className="flex flex-wrap items-end gap-4">
        <div className="input-group">
          <label className="input-label">解决状态</label>
          <Select
            value={filterResolved}
            onChange={setFilterResolved}
            options={[
              { value: '', label: '全部状态' },
              { value: 'false', label: '未解决' },
              { value: 'true', label: '已解决' },
            ]}
            className="w-32"
          />
        </div>
        <div className="input-group">
          <label className="input-label">类型</label>
          <Select
            value={filterType}
            onChange={setFilterType}
            options={[
              { value: '', label: '全部类型' },
              { value: 'FEATURE', label: '需求' },
              { value: 'BUG', label: 'BUG' },
              { value: 'OTHER', label: '其他' },
            ]}
            className="w-32"
          />
        </div>
        <div className="flex items-end gap-2 ml-auto">
          <button onClick={handleSearch} className="btn-ios-primary">
            查询
          </button>
          {(filterResolved !== '' || filterType !== '') && (
            <button onClick={handleReset} className="btn-ios-secondary text-red-500">
              重置
            </button>
          )}
        </div>
      </div>

      {/* 列表 */}
      <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} className="vben-card">
        <div className="vben-card-header">
          <h2 className="vben-card-title">
            <MessageSquarePlus className="w-4 h-4" />
            反馈列表
          </h2>
          <span className="badge-primary">{total} 条</span>
        </div>
        <div className="divide-y divide-slate-100 dark:divide-slate-700 max-h-[500px] overflow-y-auto">
          {feedbacks.length === 0 ? (
            <div className="py-12 text-center text-slate-500">
              <MessageSquarePlus className="w-12 h-12 mx-auto mb-3 text-slate-300" />
              <p>暂无反馈</p>
            </div>
          ) : (
            feedbacks.map((fb) => {
              const typeInfo = getTypeInfo(fb.feedback_type)
              const TypeIcon = typeInfo.icon
              return (
                <div
                  key={fb.id}
                  className="p-4 hover:bg-slate-50 dark:hover:bg-slate-800/50 cursor-pointer transition-colors"
                  onClick={() => openDetail(fb)}
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 mb-1">
                        <TypeIcon className={`w-4 h-4 ${typeInfo.color}`} />
                        <span className="font-medium text-slate-900 dark:text-slate-100 truncate">
                          {fb.title}
                        </span>
                        {fb.is_resolved ? (
                          <span className="badge-success flex items-center gap-1">
                            <CheckCircle className="w-3 h-3" />
                            已解决
                          </span>
                        ) : (
                          <span className="badge-warning flex items-center gap-1">
                            <Clock className="w-3 h-3" />
                            待处理
                          </span>
                        )}
                        {fb.message_count && fb.message_count > 1 && (
                          <span className="badge-secondary flex items-center gap-1">
                            <MessageCircle className="w-3 h-3" />
                            {fb.message_count}
                          </span>
                        )}
                      </div>
                      <p className="text-sm text-slate-500 dark:text-slate-400 line-clamp-2">
                        {fb.content}
                      </p>
                      <div className="flex items-center gap-3 mt-2 text-xs text-slate-400">
                        <span>{new Date(fb.created_at).toLocaleString('zh-CN')}</span>
                        {fb.cookie_id && <span>账号: {fb.cookie_id}</span>}
                        {fb.images && fb.images.length > 0 && (
                          <span className="flex items-center gap-1">
                            <ImageIcon className="w-3 h-3" />
                            {fb.images.length}张图片
                          </span>
                        )}
                      </div>
                    </div>
                    {user?.is_admin && (
                      <button
                        onClick={(e) => {
                          e.stopPropagation()
                          setDeleteConfirm({ open: true, feedback: fb })
                        }}
                        className="p-2 text-slate-400 hover:text-red-500 hover:bg-red-50 dark:hover:bg-red-900/20 rounded-lg transition-colors"
                      >
                        <Trash2 className="w-4 h-4" />
                      </button>
                    )}
                  </div>
                </div>
              )
            })
          )}
        </div>
        {/* 分页 */}
        <div className="p-4 border-t border-slate-100 dark:border-slate-700 flex flex-col sm:flex-row items-center justify-between gap-3">
          <div className="flex items-center gap-2 text-sm text-slate-500">
            <span>共 {total} 条</span>
            <span>每页</span>
            <select
              value={pageSize}
              onChange={(e) => {
                setPageSize(Number(e.target.value))
                setPage(1)
              }}
              className="px-2 py-1 border border-slate-200 dark:border-slate-700 rounded-lg bg-white dark:bg-slate-800 text-sm"
            >
              <option value={10}>10</option>
              <option value={20}>20</option>
              <option value={50}>50</option>
              <option value={100}>100</option>
            </select>
            <span>条</span>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={() => setPage((p) => Math.max(1, p - 1))}
              disabled={page === 1}
              className="btn-ios-secondary btn-sm"
            >
              上一页
            </button>
            <span className="px-3 py-1.5 text-sm text-slate-500">
              {page} / {Math.max(1, Math.ceil(total / pageSize))}
            </span>
            <button
              onClick={() => setPage((p) => p + 1)}
              disabled={page >= Math.ceil(total / pageSize) || total === 0}
              className="btn-ios-secondary btn-sm"
            >
              下一页
            </button>
          </div>
        </div>
      </motion.div>

      {/* 新建弹窗 */}
      {isModalOpen && (
        <div className="modal-overlay">
          <div className="modal-content max-w-lg min-h-[480px]">
            <div className="modal-header">
              <h2 className="text-lg font-semibold">提交反馈</h2>
              <button onClick={() => setIsModalOpen(false)} className="p-1 hover:bg-gray-100 dark:hover:bg-slate-700 rounded-lg">
                <X className="w-4 h-4 text-gray-500" />
              </button>
            </div>
            <div className="modal-body space-y-4">
              <div className="input-group">
                <label className="input-label">反馈类型 *</label>
                <div className="flex gap-2">
                  {FEEDBACK_TYPE_OPTIONS.map((opt) => {
                    const Icon = opt.icon
                    return (
                      <button
                        key={opt.value}
                        type="button"
                        onClick={() => setFormType(opt.value)}
                        className={`flex-1 flex items-center justify-center gap-2 py-2 px-3 rounded-lg border transition-colors ${
                          formType === opt.value
                            ? 'border-blue-500 bg-blue-50 dark:bg-blue-900/20 text-blue-600'
                            : 'border-slate-200 dark:border-slate-700 hover:border-slate-300'
                        }`}
                      >
                        <Icon className={`w-4 h-4 ${opt.color}`} />
                        <span className="text-sm">{opt.label}</span>
                      </button>
                    )
                  })}
                </div>
              </div>
              <div className="input-group">
                <label className="input-label">标题 *</label>
                <input
                  type="text"
                  value={formTitle}
                  onChange={(e) => setFormTitle(e.target.value)}
                  placeholder="简要描述您的反馈"
                  className="input-ios"
                  maxLength={100}
                />
              </div>
              <div className="input-group">
                <label className="input-label">内容 *</label>
                <textarea
                  value={formContent}
                  onChange={(e) => setFormContent(e.target.value)}
                  placeholder="详细描述您的需求或问题"
                  className="input-ios min-h-[100px] resize-none"
                  maxLength={2000}
                />
              </div>
              <div className="input-group">
                <label className="input-label">关联账号（可选）</label>
                <Select
                  value={formCookieId}
                  onChange={setFormCookieId}
                  options={[
                    { value: '', label: '不关联账号', key: 'none' },
                    ...accounts.map((a) => ({ 
                      value: a.id, 
                      label: a.note ? `${a.id} (${a.note})` : a.id,
                      key: a.pk?.toString() || a.id,
                    })),
                  ]}
                />
              </div>
              <div className="input-group">
                <label className="input-label">图片（可选，最多3张）</label>
                <div className="flex flex-wrap gap-2">
                  {formImages.map((img, idx) => (
                    <div key={idx} className="relative w-16 h-16 rounded-lg overflow-hidden border border-slate-200 dark:border-slate-700">
                      <img src={img} alt="" className="w-full h-full object-cover" />
                      <button
                        type="button"
                        onClick={() => setFormImages(formImages.filter((_, i) => i !== idx))}
                        className="absolute top-0 right-0 p-0.5 bg-red-500 text-white rounded-bl-lg"
                      >
                        <X className="w-3 h-3" />
                      </button>
                    </div>
                  ))}
                  {formImages.length < 3 && (
                    <button
                      type="button"
                      onClick={() => fileInputRef.current?.click()}
                      disabled={uploading}
                      className="w-16 h-16 rounded-lg border-2 border-dashed border-slate-300 dark:border-slate-600 flex items-center justify-center text-slate-400 hover:border-blue-400 hover:text-blue-400 transition-colors"
                    >
                      {uploading ? <Loader2 className="w-5 h-5 animate-spin" /> : <Upload className="w-5 h-5" />}
                    </button>
                  )}
                </div>
                <input
                  ref={fileInputRef}
                  type="file"
                  accept="image/*"
                  onChange={handleUploadImage}
                  className="hidden"
                />
              </div>
            </div>
            <div className="modal-footer">
              <button onClick={() => setIsModalOpen(false)} className="btn-ios-secondary" disabled={saving}>
                取消
              </button>
              <button onClick={handleSubmit} className="btn-ios-primary" disabled={saving}>
                {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : null}
                提交
              </button>
            </div>
          </div>
        </div>
      )}

      {/* 详情弹窗（对话形式） */}
      {detailOpen && (
        <div className="modal-overlay">
          <div className="modal-content max-w-2xl h-[80vh] flex flex-col">
            {detailLoading ? (
              <div className="flex-1 flex items-center justify-center">
                <Loader2 className="w-8 h-8 animate-spin text-blue-500" />
              </div>
            ) : detailData ? (
              <>
                {/* 头部 */}
                <div className="modal-header border-b border-slate-100 dark:border-slate-700">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      {(() => {
                        const info = getTypeInfo(detailData.feedback_type)
                        const Icon = info.icon
                        return <Icon className={`w-5 h-5 ${info.color}`} />
                      })()}
                      <h2 className="text-lg font-semibold truncate">{detailData.title}</h2>
                      {detailData.is_resolved ? (
                        <span className="badge-success">已解决</span>
                      ) : (
                        <span className="badge-warning">待处理</span>
                      )}
                    </div>
                    <div className="flex items-center gap-3 mt-1 text-xs text-slate-400">
                      <span>{new Date(detailData.created_at).toLocaleString('zh-CN')}</span>
                      {detailData.cookie_id && <span>账号: {detailData.cookie_id}</span>}
                    </div>
                  </div>
                  <button onClick={() => setDetailOpen(false)} className="p-1 hover:bg-gray-100 dark:hover:bg-slate-700 rounded-lg">
                    <X className="w-4 h-4 text-gray-500" />
                  </button>
                </div>

                {/* 图片区域 */}
                {detailData.images && detailData.images.length > 0 && (
                  <div className="px-4 py-2 border-b border-slate-100 dark:border-slate-700">
                    <div className="flex flex-wrap gap-2">
                      {detailData.images.map((img, idx) => (
                        <a key={idx} href={img} target="_blank" rel="noopener noreferrer">
                          <img src={img} alt="" className="w-16 h-16 object-cover rounded-lg border border-slate-200 dark:border-slate-700" />
                        </a>
                      ))}
                    </div>
                  </div>
                )}

                {/* 对话区域 */}
                <div className="flex-1 overflow-y-auto p-4 space-y-3">
                  {detailData.messages.map((msg, idx) => (
                    <div
                      key={msg.id || idx}
                      className={`flex ${msg.is_admin ? 'justify-start' : 'justify-end'}`}
                    >
                      <div
                        className={`max-w-[80%] rounded-lg px-4 py-2 ${
                          msg.is_admin
                            ? 'bg-blue-50 dark:bg-blue-900/20 text-slate-700 dark:text-slate-300'
                            : 'bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300'
                        }`}
                      >
                        <div className="flex items-center gap-2 mb-1">
                          <span className={`text-xs font-medium ${msg.is_admin ? 'text-blue-600 dark:text-blue-400' : 'text-slate-500'}`}>
                            {msg.is_admin ? '管理员' : '我'}
                          </span>
                          {msg.created_at && (
                            <span className="text-xs text-slate-400">
                              {new Date(msg.created_at).toLocaleString('zh-CN')}
                            </span>
                          )}
                        </div>
                        <p className="text-sm whitespace-pre-wrap">{msg.content}</p>
                      </div>
                    </div>
                  ))}
                  <div ref={messagesEndRef} />
                </div>

                {/* 底部操作区 */}
                <div className="border-t border-slate-100 dark:border-slate-700 p-4">
                  {/* 回复输入框 */}
                  <div className="flex gap-2 mb-3">
                    <input
                      type="text"
                      value={replyContent}
                      onChange={(e) => setReplyContent(e.target.value)}
                      placeholder="输入回复内容..."
                      className="input-ios flex-1"
                      onKeyDown={(e) => {
                        if (e.key === 'Enter' && !e.shiftKey) {
                          e.preventDefault()
                          handleReply()
                        }
                      }}
                    />
                    <button
                      onClick={handleReply}
                      disabled={!replyContent.trim() || replying}
                      className="btn-ios-primary"
                    >
                      {replying ? <Loader2 className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
                    </button>
                  </div>
                  {/* 管理员操作按钮 */}
                  {user?.is_admin && (
                    <div className="flex justify-end gap-2">
                      {detailData.is_resolved ? (
                        <button onClick={handleUnresolve} className="btn-ios-warning btn-sm">
                          标记未解决
                        </button>
                      ) : (
                        <button onClick={handleResolve} className="btn-ios-success btn-sm">
                          标记已解决
                        </button>
                      )}
                    </div>
                  )}
                </div>
              </>
            ) : null}
          </div>
        </div>
      )}

      {/* 删除确认弹窗 */}
      <ConfirmModal
        isOpen={deleteConfirm.open}
        title="删除确认"
        message="确定要删除这条反馈吗？删除后无法恢复。"
        confirmText="删除"
        cancelText="取消"
        type="danger"
        loading={deleting}
        onConfirm={() => deleteConfirm.feedback && handleDelete(deleteConfirm.feedback)}
        onCancel={() => setDeleteConfirm({ open: false, feedback: null })}
      />
    </div>
  )
}
