/** 自动回复页面入口，普通关键词和API关键词分别保存。 */
import { motion } from 'framer-motion'
import { useState } from 'react'
import { Plus, MapPin, Image, Download, Upload, RefreshCw, Trash2 } from 'lucide-react'
import { Select } from '@/components/common/Select'
import { ConfirmModal } from '@/components/common/ConfirmModal'
import { PageLoading } from '@/components/common/Loading'
import { useKeywordPage } from './useKeywordPage'
import { KeywordList } from './KeywordList'
import { KeywordTextModal } from './KeywordTextModal'
import { KeywordImageModal } from './KeywordImageModal'
import { ApiKeywordFormModal } from './ApiKeywordFormModal'
import { ApiKeywordList } from './ApiKeywordList'
import { useUIStore } from '@/store/uiStore'

export function Keywords() {
  const model = useKeywordPage()
  const { addToast } = useUIStore()
  const [tab, setTab] = useState<'normal' | 'api'>('normal')
  const [apiAccountId, setApiAccountId] = useState<string | null>(null)
  const [apiRevision, setApiRevision] = useState(0)
  const { loading, accounts, selectedAccount, setSelectedAccount, selectedKeywordIds, deleteConfirm, setDeleteConfirm, batchDeleteConfirm, setBatchDeleteConfirm, deleting, loadKeywords, openAddModal, openExternalContactModal, handleDelete, handleBatchDelete, openImageModal, importing, exporting, importInputRef, handleExport, handleImportButtonClick, handleImportFileChange } = model

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
          {tab === 'normal' && selectedKeywordIds.size > 0 && (
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
            onClick={() => { setTab('normal'); openAddModal() }}
            className="btn-ios-primary"
          >
            <Plus className="w-4 h-4" />
            添加文本关键词
          </button>
          <button
            type="button"
            onClick={() => { setTab('normal'); openExternalContactModal() }}
            className="btn-ios-primary"
          >
            <MapPin className="w-4 h-4" />
            添加站外联系方式关键词
          </button>
          <button
            type="button"
            onClick={() => { setTab('normal'); openImageModal() }}
            className="btn-ios-primary"
          >
            <Image className="w-4 h-4" />
            添加图片关键词
          </button>
          <button type="button" className="btn-ios-primary" onClick={() => {
            if (!model.selectedAccount) {
              addToast({ type: 'warning', message: '请先选择具体账号才能新增API关键词' })
              return
            }
            setApiAccountId(model.selectedAccount)
          }}><Plus className="w-4 h-4" />新增 API关键词</button>
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
          <button type="button" onClick={() => {
            if (tab === 'api') setApiRevision(value => value + 1)
            else void loadKeywords()
          }} className="btn-ios-secondary ">
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

      <div className="flex gap-2" role="tablist" aria-label="关键词类型">
        <button type="button" role="tab" aria-selected={tab === 'normal'} className={tab === 'normal' ? 'btn-ios-primary' : 'btn-ios-secondary'}
          onClick={() => setTab('normal')}>普通关键词</button>
        <button type="button" role="tab" aria-selected={tab === 'api'} className={tab === 'api' ? 'btn-ios-primary' : 'btn-ios-secondary'}
          onClick={() => setTab('api')}>API关键词</button>
      </div>
      {tab === 'normal' ? <KeywordList model={model} /> : <ApiKeywordList key={selectedAccount} accountId={selectedAccount} revision={apiRevision} />}

      {apiAccountId && <ApiKeywordFormModal accountId={apiAccountId} onClose={() => setApiAccountId(null)} onSaved={() => {
        setApiAccountId(null)
        setApiRevision(value => value + 1)
        setTab('api')
      }} />}

      <KeywordTextModal model={model} />

      <KeywordImageModal model={model} />

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
