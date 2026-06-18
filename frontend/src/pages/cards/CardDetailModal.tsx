/**
 * 卡券详情弹窗组件
 * 
 * 功能：以只读方式展示卡券的详细信息
 */
import { X } from 'lucide-react'
import type { CardData } from '@/api/cards'

// 卡券类型标签
const cardTypeLabels: Record<string, string> = {
  api: 'API',
  text: '文本',
  data: '批量',
  image: '图片',
}

interface CardDetailModalProps {
  card: CardData
  onClose: () => void
  /** 弹窗层级，默认60 */
  zIndex?: number
}

/** 详情行组件 */
function DetailRow({ label, value, multiline }: { label: string; value: string; multiline?: boolean }) {
  return (
    <div className={multiline ? '' : 'flex items-start'}>
      <span className="text-gray-500 dark:text-gray-400 min-w-[100px] inline-block font-medium">{label}：</span>
      {multiline ? (
        <pre className="mt-1 p-3 rounded-lg bg-gray-50 dark:bg-gray-900 text-gray-700 dark:text-gray-300 text-xs whitespace-pre-wrap break-all max-h-40 overflow-y-auto border border-gray-200 dark:border-gray-700">
          {value}
        </pre>
      ) : (
        <span className="text-gray-900 dark:text-white">{value}</span>
      )}
    </div>
  )
}

export function CardDetailModal({ card, onClose, zIndex = 60 }: CardDetailModalProps) {
  return (
    <div className="modal-overlay" style={{ zIndex }}>
      <div className="modal-content max-w-2xl max-h-[90vh] overflow-y-auto">
        <div className="modal-header flex items-center justify-between">
          <h2 className="text-lg font-semibold">卡券详情</h2>
          <button onClick={onClose} className="p-1 hover:bg-gray-100 dark:hover:bg-gray-800 rounded-lg">
            <X className="w-4 h-4 text-gray-500" />
          </button>
        </div>
        <div className="modal-body space-y-3 text-sm">
          <DetailRow label="卡券名称" value={card.name} />
          <DetailRow label="卡券类型" value={cardTypeLabels[card.type] || card.type} />
          <DetailRow label="状态" value={card.enabled ? '启用' : '禁用'} />
          <DetailRow label="延迟发送" value={`${card.delay_seconds || 0} 秒`} />
          <DetailRow label="发货次数" value={String(card.delivery_count ?? 0)} />
          <DetailRow label="对接价格" value={card.price ? `¥${card.price}` : '-'} />
          <DetailRow label="是否可对接" value={card.is_dockable ? '可对接' : '不可对接'} />
          {card.is_dockable && (
            <DetailRow label="最低售价" value={card.min_price ? `¥${card.min_price}` : '未设置'} />
          )}
          {card.description && (
            <DetailRow label="备注" value={card.description} multiline />
          )}

          {/* 多规格信息 */}
          {card.is_multi_spec && (
            <div className="border border-gray-200 dark:border-gray-700 rounded-lg p-3">
              <h3 className="font-medium text-gray-900 dark:text-white mb-2">多规格信息</h3>
              <div className="grid grid-cols-2 gap-2 text-sm">
                <DetailRow label="规格名称" value={card.spec_name || '-'} />
                <DetailRow label="规格值" value={card.spec_value || '-'} />
              </div>
            </div>
          )}

          {/* 文本内容 */}
          {card.type === 'text' && (
            <DetailRow label="文本内容" value={card.text_content || '-'} multiline />
          )}

          {/* 批量数据 */}
          {card.type === 'data' && (
            <div>
              <DetailRow
                label="批量数据"
                value={card.data_content || '-'}
                multiline
              />
              {card.data_content && (
                <p className="text-xs text-gray-500 mt-1">
                  共 {card.data_content.split('\n').filter((line: string) => line.trim()).length} 条数据
                </p>
              )}
            </div>
          )}

          {/* API配置 */}
          {card.type === 'api' && card.api_config && (
            <div className="border border-gray-200 dark:border-gray-700 rounded-lg p-3 space-y-2">
              <h3 className="font-medium text-gray-900 dark:text-white">API配置</h3>
              <DetailRow label="API地址" value={card.api_config.url || '-'} />
              <DetailRow label="请求方法" value={card.api_config.method || 'GET'} />
              <DetailRow label="超时时间" value={`${card.api_config.timeout || 60} 秒`} />
              {card.api_config.headers && (
                <DetailRow label="请求头" value={card.api_config.headers} multiline />
              )}
              {card.api_config.params && (
                <DetailRow label="请求参数" value={card.api_config.params} multiline />
              )}
              {card.api_config.response_field && (
                <DetailRow label="响应取值字段" value={card.api_config.response_field} />
              )}
            </div>
          )}

          {/* 图片 */}
          {card.image_urls && card.image_urls.length > 0 && (
            <div>
              <span className="text-gray-500 dark:text-gray-400 font-medium">卡券图片：</span>
              <div className="flex gap-3 mt-2 flex-wrap">
                {card.image_urls.map((url, i) => (
                  <img
                    key={i}
                    src={url}
                    alt={`图片${i + 1}`}
                    className="w-24 h-24 object-cover rounded-lg border border-gray-200 dark:border-gray-700"
                  />
                ))}
              </div>
            </div>
          )}
          {!card.image_urls?.length && card.image_url && (
            <div>
              <span className="text-gray-500 dark:text-gray-400 font-medium">卡券图片：</span>
              <div className="mt-2">
                <img
                  src={card.image_url}
                  alt="卡券图片"
                  className="w-24 h-24 object-cover rounded-lg border border-gray-200 dark:border-gray-700"
                />
              </div>
            </div>
          )}

          {/* 时间信息 */}
          <div className="border-t border-gray-200 dark:border-gray-700 pt-3 space-y-2">
            <DetailRow label="创建时间" value={card.created_at ? new Date(card.created_at).toLocaleString('zh-CN') : '-'} />
            <DetailRow label="更新时间" value={card.updated_at ? new Date(card.updated_at).toLocaleString('zh-CN') : '-'} />
          </div>
        </div>
        <div className="modal-footer">
          <button onClick={onClose} className="btn-ios-secondary">
            关闭
          </button>
        </div>
      </div>
    </div>
  )
}
