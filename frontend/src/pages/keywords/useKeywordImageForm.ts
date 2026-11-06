/** 图片关键词表单状态与上传保存，沿用原有处理流程。 */
import { useState, useRef } from 'react'
import type { FormEvent, ChangeEvent } from 'react'
import { addImageKeyword } from '@/api/keywords'
import { useUIStore } from '@/store/uiStore'
export function useKeywordImageForm(selectedAccount: string, loadKeywords: () => Promise<void>) {
  const { addToast } = useUIStore()
  // 图片关键词相关状态
  const [isImageModalOpen, setIsImageModalOpen] = useState(false)
  const [imageKeyword, setImageKeyword] = useState('')
  const [imageSelectedItemIds, setImageSelectedItemIds] = useState<string[]>([])  // 多选商品ID
  const [imageItemSearchText, setImageItemSearchText] = useState('')  // 商品搜索
  const [imageFile, setImageFile] = useState<File | null>(null)
  const [imagePreview, setImagePreview] = useState<string>('')
  const [savingImage, setSavingImage] = useState(false)
  const imageInputRef = useRef<HTMLInputElement | null>(null)
  
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


  return { isImageModalOpen, setIsImageModalOpen, imageKeyword, setImageKeyword, imageSelectedItemIds, setImageSelectedItemIds, imageItemSearchText, setImageItemSearchText, imageFile, setImageFile, imagePreview, setImagePreview, savingImage, setSavingImage, imageInputRef, openImageModal, handleImageFileChange, handleImageSubmit }
}
