/** 关键词导入导出操作与加载状态。 */
import { useState, useRef } from 'react'
import type { ChangeEvent } from 'react'
import { exportKeywords, importKeywords as importKeywordsApi } from '@/api/keywords'
import { useUIStore } from '@/store/uiStore'
export function useKeywordTransfer(selectedAccount: string, loadKeywords: () => Promise<void>) {
  const { addToast } = useUIStore()
  const [importing, setImporting] = useState(false)
  const [exporting, setExporting] = useState(false)
  const importInputRef = useRef<HTMLInputElement | null>(null)
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


  return { importing, setImporting, exporting, setExporting, importInputRef, handleExport, handleImportButtonClick, handleImportFileChange }
}
