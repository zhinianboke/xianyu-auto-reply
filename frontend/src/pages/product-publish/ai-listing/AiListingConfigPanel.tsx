/**
 * AI 铺货配置面板
 *
 * 功能：
 * 1. 配置列表（后端分页 + 名称查询，查询/重置按钮在筛选行最右）
 * 2. 新增/编辑切换到配置表单组件
 * 3. 连通性测试与删除（删除走公共确认弹窗，后端为软删除）
 */
import { useCallback, useEffect, useState } from 'react'
import { Loader2, Pencil, Plus, Search, Trash2, X, Zap } from 'lucide-react'
import {
  deleteAiListingConfig,
  getAiListingConfigs,
  testAiListingConfig,
  type AiListingConfig,
} from '@/api/aiListing'
import { ConfirmModal } from '@/components/common/ConfirmModal'
import { useUIStore } from '@/store/uiStore'
import { getApiErrorMessage } from '@/utils/apiError'
import { AiListingConfigForm } from './AiListingConfigForm'

interface AiListingConfigPanelProps {
  /** 配置发生变化时通知父组件刷新配置下拉 */
  onConfigsChanged?: () => void
}

export function AiListingConfigPanel({ onConfigsChanged }: AiListingConfigPanelProps) {
  const { addToast } = useUIStore()

  const [configs, setConfigs] = useState<AiListingConfig[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(10)
  const [totalPages, setTotalPages] = useState(0)
  const [loading, setLoading] = useState(false)

  // 筛选：输入内容与生效条件分开，只有点「查询」或回车才生效
  const [nameInput, setNameInput] = useState('')
  const [nameFilter, setNameFilter] = useState('')

  // 表单态：undefined=列表态，null=新增，对象=编辑
  const [formTarget, setFormTarget] = useState<AiListingConfig | null | undefined>(undefined)
  const [testingId, setTestingId] = useState<number | null>(null)
  const [deleteTarget, setDeleteTarget] = useState<AiListingConfig | null>(null)
  const [deleting, setDeleting] = useState(false)

  const load = useCallback(async (targetPage: number, size: number, name: string) => {
    setLoading(true)
    try {
      const res = await getAiListingConfigs(targetPage, size, name || undefined)
      if (!res.success) {
        addToast({ type: 'error', message: res.message || '加载配置失败' })
        return
      }
      setConfigs(res.data.list)
      setTotal(res.data.total)
      setTotalPages(res.data.total_pages)
    } catch (error) {
      addToast({ type: 'error', message: getApiErrorMessage(error, '加载配置失败') })
    } finally {
      setLoading(false)
    }
  }, [addToast])

  useEffect(() => {
    void load(page, pageSize, nameFilter)
  }, [load, page, pageSize, nameFilter])

  const handleSaved = async () => {
    setFormTarget(undefined)
    setPage(1)
    await load(1, pageSize, nameFilter)
    onConfigsChanged?.()
  }

  const handleTest = async (config: AiListingConfig) => {
    setTestingId(config.id)
    try {
      const res = await testAiListingConfig(config.id)
      addToast({
        type: res.success ? 'success' : 'error',
        message: res.message || (res.success ? '连接成功' : '连接失败'),
      })
    } catch (error) {
      addToast({ type: 'error', message: getApiErrorMessage(error, '连接测试失败') })
    } finally {
      setTestingId(null)
    }
  }

  const handleDelete = async () => {
    if (!deleteTarget) return
    setDeleting(true)
    try {
      const res = await deleteAiListingConfig(deleteTarget.id)
      if (!res.success) {
        addToast({ type: 'error', message: res.message || '删除失败' })
        return
      }
      addToast({ type: 'success', message: res.message || '配置已删除' })
      setDeleteTarget(null)
      setPage(1)
      await load(1, pageSize, nameFilter)
      onConfigsChanged?.()
    } catch (error) {
      addToast({ type: 'error', message: getApiErrorMessage(error, '删除失败') })
    } finally {
      setDeleting(false)
    }
  }

  if (formTarget !== undefined) {
    return (
      <AiListingConfigForm
        config={formTarget}
        onSaved={handleSaved}
        onCancel={() => setFormTarget(undefined)}
      />
    )
  }

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-end gap-4">
        <div className="input-group">
          <label className="input-label">配置名称</label>
          <input
            className="input-ios w-48"
            placeholder="搜索配置名称..."
            value={nameInput}
            onChange={e => setNameInput(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && (setPage(1), setNameFilter(nameInput.trim()))}
          />
        </div>
        <div className="flex items-center gap-2 ml-auto">
          <button
            className="btn-ios-primary btn-sm"
            onClick={() => { setPage(1); setNameFilter(nameInput.trim()) }}
            disabled={loading}
          >
            <Search className="w-3.5 h-3.5" />查询
          </button>
          {nameFilter && (
            <button
              className="btn-ios-secondary btn-sm"
              onClick={() => { setNameInput(''); setNameFilter(''); setPage(1) }}
              disabled={loading}
            >
              <X className="w-3.5 h-3.5" />重置
            </button>
          )}
          <button className="btn-ios-primary btn-sm" onClick={() => setFormTarget(null)}>
            <Plus className="w-3.5 h-3.5" />新增配置
          </button>
        </div>
      </div>

      <div className="table-scroll max-h-72 border border-slate-200 dark:border-slate-700 rounded-lg">
        <table className="table-ios">
          <thead>
            <tr>
              <th>配置名称</th>
              <th>文案模型</th>
              <th>图片生成</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr><td colSpan={4} className="text-center py-8 text-slate-400">
                <Loader2 className="w-4 h-4 animate-spin inline mr-2" />加载中...
              </td></tr>
            ) : configs.length === 0 ? (
              <tr><td colSpan={4} className="text-center py-8 text-slate-400">
                {nameFilter ? '没有符合条件的配置' : '暂无配置，请先新增一套 AI 配置'}
              </td></tr>
            ) : configs.map(config => (
              <tr key={config.id}>
                <td>
                  <div className="font-medium text-slate-900 dark:text-slate-100">{config.name}</div>
                  <div className="text-xs text-slate-400">{config.text_api_key_masked}</div>
                </td>
                <td className="text-slate-600 dark:text-slate-300">{config.text_model}</td>
                <td>
                  {config.image_enabled
                    ? <span className="badge-success">已启用</span>
                    : <span className="badge-gray">未启用</span>}
                </td>
                <td>
                  <div className="table-actions">
                    <button
                      className="table-action-btn" title="测试连接"
                      onClick={() => handleTest(config)} disabled={testingId === config.id}
                    >
                      {testingId === config.id
                        ? <Loader2 className="w-4 h-4 animate-spin text-blue-500" />
                        : <Zap className="w-4 h-4 text-blue-500" />}
                    </button>
                    <button className="table-action-btn" title="编辑" onClick={() => setFormTarget(config)}>
                      <Pencil className="w-4 h-4" />
                    </button>
                    <button className="table-action-btn" title="删除" onClick={() => setDeleteTarget(config)}>
                      <Trash2 className="w-4 h-4 text-red-500" />
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="flex items-center justify-between text-xs text-slate-500 dark:text-slate-400">
        <div className="flex items-center gap-2">
          <span>每页</span>
          <select
            className="input-ios py-1 w-20"
            value={pageSize}
            onChange={e => { setPageSize(Number(e.target.value)); setPage(1) }}
          >
            {[10, 20, 50, 100].map(size => <option key={size} value={size}>{size}</option>)}
          </select>
          <span>共 {total} 条</span>
        </div>
        <div className="flex items-center gap-2">
          <button
            className="btn-ios-secondary btn-sm"
            onClick={() => setPage(p => Math.max(1, p - 1))}
            disabled={page <= 1 || loading}
          >
            上一页
          </button>
          <span>第 {page} / {totalPages || 1} 页</span>
          <button
            className="btn-ios-secondary btn-sm"
            onClick={() => setPage(p => (totalPages ? Math.min(totalPages, p + 1) : p))}
            disabled={page >= totalPages || loading}
          >
            下一页
          </button>
        </div>
      </div>

      <ConfirmModal
        isOpen={Boolean(deleteTarget)}
        type="danger"
        title="删除配置"
        message={`确定删除配置「${deleteTarget?.name || ''}」吗？删除后历史任务仍可查看，但无法再用它启动新任务。`}
        confirmText="删除"
        loading={deleting}
        onConfirm={handleDelete}
        onCancel={() => setDeleteTarget(null)}
      />
    </div>
  )
}

export default AiListingConfigPanel



