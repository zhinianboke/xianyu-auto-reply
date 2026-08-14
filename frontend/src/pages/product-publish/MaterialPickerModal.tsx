/**
 * 单品发布素材选择弹窗。
 * 使用后端分页展示素材，并提供只读详情与导入操作。
 */
import { useEffect, useState } from 'react'
import { ChevronLeft, ChevronRight, Eye, Image, Loader2, Upload, X } from 'lucide-react'
import { getMaterial, getMaterials, type ProductMaterial } from '@/api/productPublish'
import { useUIStore } from '@/store/uiStore'

interface MaterialPickerModalProps {
  onSelect: (material: ProductMaterial) => void
  onClose: () => void
}

function textValue(value?: string | null): string {
  return value?.trim() || '-'
}

function shippingMethodText(material: ProductMaterial): string {
  const labels: Record<ProductMaterial['shipping_method'], string> = {
    free: '包邮',
    distance: '按距离计费',
    fixed: '一口价',
    template: '运费模板',
    none: '无需邮寄',
  }
  return labels[material.shipping_method] || '-'
}

function MaterialDetailModal({ material, onClose }: { material: ProductMaterial; onClose: () => void }) {
  const categoryPath = material.platform_category_path?.map((item) => item.name).filter(Boolean).join(' / ')
  const specificationNames = material.specifications?.map((specification) => specification.name) || []

  return (
    <div className="modal-overlay z-[60]">
      <div className="modal-content max-w-5xl max-h-[92vh] flex flex-col">
        <div className="modal-header flex-shrink-0">
          <div className="min-w-0">
            <h2 className="modal-title">素材详情</h2>
            <p className="mt-1 truncate text-xs text-slate-400">{material.title}</p>
          </div>
          <button type="button" className="modal-close" title="关闭" onClick={onClose}><X className="h-5 w-5" /></button>
        </div>

        <div className="modal-body overflow-y-auto space-y-6">
          <section className="space-y-3">
            <h3 className="text-sm font-semibold text-slate-800 dark:text-slate-100">图片与视频</h3>
            <div className="flex flex-wrap gap-2">
              {(material.images || []).map((url, index) => (
                <div key={`${url}-${index}`} className="relative h-24 w-24 overflow-hidden rounded-lg border border-slate-200 dark:border-slate-700">
                  <img src={url} alt={`${material.title} 图片 ${index + 1}`} className="h-full w-full object-cover" />
                  {index === 0 && <span className="absolute inset-x-0 bottom-0 bg-black/60 py-0.5 text-center text-[10px] text-white">首图</span>}
                </div>
              ))}
              {(material.images || []).length === 0 && <span className="text-sm text-slate-400">暂无图片</span>}
            </div>
            {(material.videos || []).map((video, index) => (
              <video key={`${video.url}-${index}`} className="w-full max-w-xl rounded-lg bg-black" controls preload="metadata" src={video.url}>
                当前浏览器不支持视频播放
              </video>
            ))}
          </section>

          <section className="space-y-3 border-t border-slate-200 pt-5 dark:border-slate-700">
            <h3 className="text-sm font-semibold text-slate-800 dark:text-slate-100">基础信息</h3>
            <dl className="grid grid-cols-1 gap-x-6 gap-y-3 text-sm sm:grid-cols-2 lg:grid-cols-3">
              <div><dt className="text-slate-400">商品标题</dt><dd className="mt-1 text-slate-700 dark:text-slate-200">{material.title}</dd></div>
              <div><dt className="text-slate-400">售价</dt><dd className="mt-1 font-medium text-amber-600">¥{material.price}</dd></div>
              <div><dt className="text-slate-400">原价</dt><dd className="mt-1 text-slate-700 dark:text-slate-200">{material.original_price ? `¥${material.original_price}` : '-'}</dd></div>
              <div><dt className="text-slate-400">成色</dt><dd className="mt-1 text-slate-700 dark:text-slate-200">{textValue(material.condition)}</dd></div>
              <div><dt className="text-slate-400">库存</dt><dd className="mt-1 text-slate-700 dark:text-slate-200">{material.quantity}</dd></div>
              <div><dt className="text-slate-400">本地分类</dt><dd className="mt-1 text-slate-700 dark:text-slate-200">{textValue(material.category)}</dd></div>
              <div><dt className="text-slate-400">宝贝所在地</dt><dd className="mt-1 text-slate-700 dark:text-slate-200">{textValue(material.address)}</dd></div>
              <div><dt className="text-slate-400">发货方式</dt><dd className="mt-1 text-slate-700 dark:text-slate-200">{material.delivery_method === 'pickup' ? '自提' : '快递'}</dd></div>
              <div><dt className="text-slate-400">运费方式</dt><dd className="mt-1 text-slate-700 dark:text-slate-200">{shippingMethodText(material)}</dd></div>
              <div><dt className="text-slate-400">运费</dt><dd className="mt-1 text-slate-700 dark:text-slate-200">{material.postage > 0 ? `¥${material.postage}` : '0 元'}</dd></div>
              <div><dt className="text-slate-400">支持自提</dt><dd className="mt-1 text-slate-700 dark:text-slate-200">{material.support_pickup ? '是' : '否'}</dd></div>
              <div><dt className="text-slate-400">更新时间</dt><dd className="mt-1 text-slate-700 dark:text-slate-200">{material.updated_at || '-'}</dd></div>
              <div className="sm:col-span-2 lg:col-span-3"><dt className="text-slate-400">商品描述</dt><dd className="mt-1 whitespace-pre-wrap break-words text-slate-700 dark:text-slate-200">{textValue(material.description)}</dd></div>
              <div className="sm:col-span-2 lg:col-span-3"><dt className="text-slate-400">内部备注</dt><dd className="mt-1 whitespace-pre-wrap break-words text-slate-700 dark:text-slate-200">{textValue(material.remark)}</dd></div>
            </dl>
          </section>

          <section className="space-y-3 border-t border-slate-200 pt-5 dark:border-slate-700">
            <h3 className="text-sm font-semibold text-slate-800 dark:text-slate-100">平台分类</h3>
            <dl className="grid grid-cols-1 gap-x-6 gap-y-3 text-sm sm:grid-cols-2 lg:grid-cols-3">
              <div className="sm:col-span-2 lg:col-span-3"><dt className="text-slate-400">分类路径</dt><dd className="mt-1 text-slate-700 dark:text-slate-200">{categoryPath || '-'}</dd></div>
              <div><dt className="text-slate-400">分类</dt><dd className="mt-1 text-slate-700 dark:text-slate-200">{textValue(material.platform_category_name)}</dd></div>
              <div><dt className="text-slate-400">分类 ID</dt><dd className="mt-1 break-all text-slate-700 dark:text-slate-200">{textValue(material.platform_category_id)}</dd></div>
              <div><dt className="text-slate-400">频道分类</dt><dd className="mt-1 text-slate-700 dark:text-slate-200">{textValue(material.platform_channel_category_name)}</dd></div>
              <div><dt className="text-slate-400">频道分类 ID</dt><dd className="mt-1 break-all text-slate-700 dark:text-slate-200">{textValue(material.platform_channel_category_id)}</dd></div>
              <div><dt className="text-slate-400">叶子分类 ID</dt><dd className="mt-1 break-all text-slate-700 dark:text-slate-200">{textValue(material.platform_leaf_id)}</dd></div>
              <div><dt className="text-slate-400">淘宝分类 ID</dt><dd className="mt-1 break-all text-slate-700 dark:text-slate-200">{textValue(material.platform_tb_category_id)}</dd></div>
            </dl>
            {(material.platform_attributes || []).length > 0 && (
              <div className="flex flex-wrap gap-2">
                {material.platform_attributes.map((attribute, index) => (
                  <span key={`${attribute.property_id}-${attribute.value_id}-${index}`} className="badge-info">
                    {attribute.property_name || '属性'}：{attribute.value_name || attribute.text || '-'}
                  </span>
                ))}
              </div>
            )}
          </section>

          {(material.specifications || []).length > 0 && (
            <section className="space-y-3 border-t border-slate-200 pt-5 dark:border-slate-700">
              <h3 className="text-sm font-semibold text-slate-800 dark:text-slate-100">商品规格</h3>
              <div className="space-y-3">
                {material.specifications.map((specification) => (
                  <div key={specification.name}>
                    <p className="mb-2 text-xs text-slate-400">{specification.name}</p>
                    <div className="flex flex-wrap gap-2">
                      {specification.values.map((value) => (
                        <span key={value.name} className="inline-flex items-center gap-2 rounded-md border border-slate-200 px-2 py-1 text-sm text-slate-700 dark:border-slate-700 dark:text-slate-200">
                          {value.image && <img src={value.image} alt="" className="h-7 w-7 rounded object-cover" />}
                          {value.name}
                        </span>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
              <div className="table-scroll max-h-64 rounded-lg border border-slate-200 dark:border-slate-700">
                <table className="table-ios min-w-[560px]">
                  <thead><tr>{specificationNames.map((name) => <th key={name}>{name}</th>)}<th>价格</th><th>库存</th></tr></thead>
                  <tbody>
                    {(material.sku_rows || []).map((row, index) => (
                      <tr key={`${Object.values(row.specs).join('-')}-${index}`}>
                        {specificationNames.map((name) => <td key={name}>{row.specs[name] || '-'}</td>)}
                        <td>¥{row.price}</td><td>{row.stock}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          )}
        </div>

        <div className="modal-footer flex-shrink-0">
          <button type="button" className="btn-ios-secondary" onClick={onClose}>关闭</button>
        </div>
      </div>
    </div>
  )
}

export function MaterialPickerModal({ onSelect, onClose }: MaterialPickerModalProps) {
  const { addToast } = useUIStore()
  const [materials, setMaterials] = useState<ProductMaterial[]>([])
  const [loading, setLoading] = useState(true)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)
  const [total, setTotal] = useState(0)
  const [totalPages, setTotalPages] = useState(0)
  const [detail, setDetail] = useState<ProductMaterial | null>(null)
  const [detailLoadingId, setDetailLoadingId] = useState<number | null>(null)

  useEffect(() => {
    let active = true
    setLoading(true)
    getMaterials(page, pageSize).then((result) => {
      if (!active) return
      if (!result.success || !result.data) {
        addToast({ type: 'error', message: result.message || '加载素材失败' })
        setMaterials([])
        return
      }
      setMaterials(result.data.list)
      setTotal(result.data.total)
      setTotalPages(result.data.total_pages)
    }).catch(() => {
      if (active) addToast({ type: 'error', message: '加载素材失败，请重试' })
    }).finally(() => {
      if (active) setLoading(false)
    })
    return () => { active = false }
  }, [addToast, page, pageSize])

  const showDetail = async (material: ProductMaterial) => {
    setDetailLoadingId(material.id)
    try {
      const response = await getMaterial(material.id)
      if (!response.success || !response.data) {
        addToast({ type: 'error', message: response.message || '加载素材详情失败' })
        return
      }
      setDetail(response.data)
    } catch {
      addToast({ type: 'error', message: '加载素材详情失败，请重试' })
    } finally {
      setDetailLoadingId(null)
    }
  }

  return (
    <div className="modal-overlay z-50">
      <div className="modal-content max-w-5xl h-[min(78vh,720px)] flex flex-col">
        <div className="modal-header flex-shrink-0">
          <div><h2 className="modal-title">从素材库选择</h2><p className="mt-1 text-xs text-slate-400">共 {total} 条素材</p></div>
          <button type="button" className="modal-close" title="关闭" onClick={onClose}><X className="h-5 w-5" /></button>
        </div>
        <div className="modal-body min-h-0 flex-1 p-0">
          <div className="table-scroll h-full">
            <table className="table-ios min-w-[760px]">
              <thead><tr><th>素材</th><th>价格</th><th>分类</th><th>规格</th><th>媒体</th><th className="w-32">操作</th></tr></thead>
              <tbody>
                {loading ? (
                  <tr><td colSpan={6} className="py-16 text-center"><Loader2 className="mx-auto h-7 w-7 animate-spin text-blue-500" /></td></tr>
                ) : materials.length === 0 ? (
                  <tr><td colSpan={6} className="py-16 text-center text-slate-400"><Image className="mx-auto mb-2 h-10 w-10 text-slate-300" />素材库为空，请先添加素材</td></tr>
                ) : materials.map((material) => (
                  <tr key={material.id}>
                    <td><div className="flex min-w-56 items-center gap-3">{material.images?.[0] ? <img src={material.images[0]} alt="" className="h-12 w-12 flex-shrink-0 rounded-lg object-cover" /> : <div className="flex h-12 w-12 flex-shrink-0 items-center justify-center rounded-lg bg-slate-100 text-xs text-slate-400 dark:bg-slate-700">无图</div>}<div className="min-w-0"><p className="truncate font-medium text-slate-800 dark:text-slate-100" title={material.title}>{material.title}</p><p className="mt-1 truncate text-xs text-slate-400" title={material.description}>{material.description}</p></div></div></td>
                    <td className="whitespace-nowrap font-medium text-amber-600">¥{material.price}</td>
                    <td className="max-w-40"><span className="block truncate" title={material.platform_category_name || material.category || ''}>{material.platform_category_name || material.category || '-'}</span></td>
                    <td>{(material.specifications || []).length ? `${material.specifications.length} 类 / ${(material.sku_rows || []).length} 组合` : '单规格'}</td>
                    <td className="whitespace-nowrap">{(material.images || []).length} 图 / {(material.videos || []).length} 视频</td>
                    <td><div className="table-actions">
                      <button type="button" className="table-action-btn" title="查看素材详情" disabled={detailLoadingId === material.id} onClick={() => void showDetail(material)}>{detailLoadingId === material.id ? <Loader2 className="h-4 w-4 animate-spin" /> : <Eye className="h-4 w-4 text-blue-500" />}</button>
                      <button type="button" className="btn-ios-primary btn-sm whitespace-nowrap" onClick={() => onSelect(material)}><Upload className="h-3.5 w-3.5" />导入</button>
                    </div></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
        <div className="flex flex-shrink-0 flex-col items-center justify-between gap-3 border-t border-slate-200 px-4 py-3 dark:border-slate-700 sm:flex-row">
          <div className="flex items-center gap-2 text-sm text-slate-500"><span>每页</span><select className="input-ios h-8 w-20 py-1" value={pageSize} onChange={(event) => { setPageSize(Number(event.target.value)); setPage(1) }}><option value={10}>10 条</option><option value={20}>20 条</option><option value={50}>50 条</option><option value={100}>100 条</option></select><span>共 {total} 条</span></div>
          <div className="flex items-center gap-2"><span className="text-sm text-slate-500">第 {page} / {Math.max(totalPages, 1)} 页</span><button type="button" className="table-action-btn" title="上一页" disabled={page <= 1 || loading} onClick={() => setPage((current) => current - 1)}><ChevronLeft className="h-4 w-4" /></button><button type="button" className="table-action-btn" title="下一页" disabled={page >= totalPages || loading} onClick={() => setPage((current) => current + 1)}><ChevronRight className="h-4 w-4" /></button></div>
        </div>
      </div>
      {detail && <MaterialDetailModal material={detail} onClose={() => setDetail(null)} />}
    </div>
  )
}

export default MaterialPickerModal
