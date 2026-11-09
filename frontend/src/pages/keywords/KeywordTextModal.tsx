/** 文本与站外联系方式关键词的新增和编辑弹窗。 */
import { KeywordItemSelector } from './KeywordItemSelector'
import { Select } from '@/components/common/Select'
import LocationContactReplyFields from '@/pages/common/LocationContactReplyFields'
import type { useKeywordPage } from './useKeywordPage'

export function KeywordTextModal({ model }: { model: ReturnType<typeof useKeywordPage> }) {
  const { accounts, items, selectedAccount, formAccountId, setFormAccountId, isModalOpen, setIsModalOpen, editingKeyword, keywordText, setKeywordText, replyText, setReplyText, replyType, setReplyType, location, setLocation, itemIdText, setItemIdText, selectedItemIds, setSelectedItemIds, itemSearchText, setItemSearchText, saving, handleSubmit } = model
  return <>
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
                <KeywordItemSelector items={items} multiple={!editingKeyword}
                  value={editingKeyword ? (itemIdText ? [itemIdText] : []) : selectedItemIds}
                  onChange={editingKeyword ? next => {
                    const current = itemIdText ? [itemIdText] : []
                    const itemIds = typeof next === 'function' ? next(current) : next
                    setItemIdText(itemIds[0] || '')
                  } : setSelectedItemIds}
                  search={itemSearchText} onSearchChange={setItemSearchText} disabled={saving} />
                <div>
                  <label className="input-label">回复类型</label>
                  <select
                    value={replyType}
                    onChange={(e) => setReplyType(e.target.value as 'text' | 'external_contact')}
                    className="input-ios"
                  >
                    <option value="text">文本回复</option>
                    <option value="external_contact">站外联系方式</option>
                  </select>
                </div>
                {replyType === 'external_contact' ? (
                  <LocationContactReplyFields value={location} onChange={setLocation} />
                ) : (
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
                )}

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

  </>
}
