/** 普通关键词列表、图片查看入口和分页，保留原有操作行为。 */
import { motion } from 'framer-motion'
import { MessageSquare, CheckSquare, Square, Edit2, Trash2, ChevronLeft, ChevronRight } from 'lucide-react'
import { parseKeywordLines } from './useKeywordPage'
import type { useKeywordPage } from './useKeywordPage'

export function KeywordList({ model }: { model: ReturnType<typeof useKeywordPage> }) {
  const { loading, keywords, selectedAccount, setIsImagePreviewOpen, setPreviewImageUrl, selectedKeywordIds, setDeleteConfirm, currentPage, pageSize, totalPages, paginatedKeywords, handlePageChange, handlePageSizeChange, openEditModal, getKeywordUniqueId, toggleKeywordSelect, toggleSelectAllKeywords } = model
  return <>
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
        <div className="table-scroll flex-1 min-h-0">
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
                      ) : keyword.type === 'external_contact' ? (
                        <span className="text-sm text-emerald-600 dark:text-emerald-400">站外联系方式</span>
                      ) : (
                        <p className="truncate text-slate-600 dark:text-slate-300" title={keyword.reply}>
                          {keyword.reply || <span className="text-gray-400">不回复</span>}
                        </p>
                      )}
                    </td>
                    <td>
                      {keyword.type === 'image' ? (
                        <span className="badge-primary">图片</span>
                      ) : keyword.type === 'external_contact' ? (
                        <span className="badge-primary">站外联系方式</span>
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

  </>
}
