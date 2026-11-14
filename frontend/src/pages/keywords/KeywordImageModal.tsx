/** 图片关键词新增和预览弹窗，保留原有上传与商品选择行为。 */
import { Image, Search, Info } from 'lucide-react'
import type { useKeywordPage } from './useKeywordPage'

export function KeywordImageModal({ model }: { model: ReturnType<typeof useKeywordPage> }) {
  const { items, isImagePreviewOpen, setIsImagePreviewOpen, previewImageUrl, isImageModalOpen, setIsImageModalOpen, imageKeyword, setImageKeyword, imageSelectedItemIds, setImageSelectedItemIds, imageItemSearchText, setImageItemSearchText, imageFile, imagePreview, savingImage, imageInputRef, handleImageFileChange, handleImageSubmit } = model
  return <>
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
                        <li>同一范围内优先级：图片 &gt; 站外联系方式 &gt; 文本；商品级关键词整体优先于通用关键词</li>
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

  </>
}
