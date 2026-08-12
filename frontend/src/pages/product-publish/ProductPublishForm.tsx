/**
 * 单品发布左侧信息表单。
 * 将截图中的基础信息、规格、价格、发货和所在地交互集中管理。
 */
import { useState } from 'react'
import { ChevronRight, MapPin } from 'lucide-react'
import ProductSpecificationsEditor from './ProductSpecificationsEditor'
import AddressPickerModal from './AddressPickerModal'
import PlatformCategoryRecommender from './PlatformCategoryRecommender'
import type { ProductSpecification, PublishForm, ShippingMethod, SkuRow } from './publishTypes'

const SHIPPING_OPTIONS: Array<{ value: ShippingMethod; label: string }> = [
  { value: 'free', label: '包邮' },
  { value: 'distance', label: '按距离计费' },
  { value: 'fixed', label: '一口价' },
  { value: 'template', label: '运费模板' },
  { value: 'none', label: '无需邮寄' },
]

interface ProductPublishFormProps {
  form: PublishForm
  setForm: React.Dispatch<React.SetStateAction<PublishForm>>
  accounts: any[]
  onUploadSpecImage: (file: File) => Promise<string | null>
  showAccount?: boolean
  categoryLocked?: boolean
  onCategoryEdit?: () => void
}

export function ProductPublishForm({ form, setForm, accounts, onUploadSpecImage, showAccount = true, categoryLocked = false, onCategoryEdit }: ProductPublishFormProps) {
  const [showAddressPicker, setShowAddressPicker] = useState(false)

  const update = (patch: Partial<PublishForm>) => {
    if ((patch.title !== undefined || patch.description !== undefined) && onCategoryEdit) onCategoryEdit()
    setForm((current) => ({ ...current, ...patch }))
  }
  const updateSpecs = (specifications: ProductSpecification[], skuRows: SkuRow[]) => update({ specifications, sku_rows: skuRows, price: skuRows[0]?.price || form.price })

  const setShippingMethod = (shipping_method: ShippingMethod) => {
    update({ shipping_method, delivery_method: shipping_method === 'none' ? 'pickup' : 'express' })
  }

  return (
    <>
      <div className="vben-card">
        <div className="vben-card-header"><h2 className="vben-card-title">商品信息</h2></div>
        <div className="vben-card-body space-y-5">
          {showAccount && <div className="input-group">
            <label className="input-label">发布账号 <span className="text-red-500">*</span></label>
            <select className="input-ios" value={form.account_id} onChange={(event) => update({ account_id: event.target.value })}>
              <option value="">-- 请选择账号 --</option>
              {accounts.map((account: any) => <option key={account.id} value={account.id}>{account.note ? `${account.note} (${account.id})` : account.id}</option>)}
            </select>
          </div>}

          <section className="space-y-3">
            <h3 className="text-base font-semibold text-slate-800 dark:text-slate-100">基础信息</h3>
            <div className="input-group">
              <label className="input-label">商品标题 <span className="text-red-500">*</span><span className="text-xs text-slate-400 ml-2 font-normal">{form.title.length}/30</span></label>
              <input className="input-ios" maxLength={30} placeholder="请输入商品标题（最多30字）" value={form.title} onChange={(event) => update({ title: event.target.value })} />
            </div>
            <div className="input-group">
              <label className="input-label">宝贝描述 <span className="text-red-500">*</span></label>
              <textarea className="input-ios min-h-32" rows={6} maxLength={1500} placeholder="描述一下宝贝的品牌型号、货品来源..." value={form.description} onChange={(event) => update({ description: event.target.value })} />
              <div className="flex justify-between text-xs text-slate-400 mt-1"><span>属性规格　上传主图/填写内容后将为你智能识别属性</span><span>{form.description.length}/1500</span></div>
            </div>
            <PlatformCategoryRecommender
              form={form}
              onChange={update}
              categoryLocked={categoryLocked}
              onReselectCategory={onCategoryEdit}
            />
          </section>

          <section className="space-y-3">
            <div className="flex items-center justify-between"><h3 className="text-base font-semibold text-slate-800 dark:text-slate-100">商品规格</h3><span className="text-xs text-slate-400">最多添加2个规格类型</span></div>
            <ProductSpecificationsEditor specifications={form.specifications} skuRows={form.sku_rows} onChange={updateSpecs} onUploadImage={onUploadSpecImage} />
          </section>

          {form.specifications.length === 0 && (
            <section className="space-y-3">
              <h3 className="text-base font-semibold text-slate-800 dark:text-slate-100">价格</h3>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                <div className="input-group"><label className="input-label">价格 <span className="text-red-500">*</span></label><div className="relative"><span className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400">¥</span><input type="number" className="input-ios pl-8" min="0" step="0.01" placeholder="0.00" value={form.price} onChange={(event) => update({ price: event.target.value })} /></div></div>
                <div className="input-group"><label className="input-label">原价</label><div className="relative"><span className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400">¥</span><input type="number" className="input-ios pl-8" min="0" step="0.01" placeholder="0.00" value={form.original_price} onChange={(event) => update({ original_price: event.target.value })} /></div></div>
                <div className="input-group"><label className="input-label">库存</label><input type="number" className="input-ios" min="1" step="1" value={form.quantity} onChange={(event) => update({ quantity: Math.max(1, Number(event.target.value) || 1) })} /></div>
              </div>
              <p className="text-xs text-slate-400">鱼小铺软件服务费按成交额（含运费）的1.6%计收</p>
            </section>
          )}

          <section className="space-y-3">
            <h3 className="text-base font-semibold text-slate-800 dark:text-slate-100">发货设置</h3>
            <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
              {SHIPPING_OPTIONS.map((option) => (
                <label key={option.value} className="inline-flex items-center gap-1.5 text-sm text-slate-600 dark:text-slate-300 cursor-pointer">
                  <input type="radio" name="shipping_method" checked={form.shipping_method === option.value} onChange={() => setShippingMethod(option.value)} />{option.label}
                </label>
              ))}
              <label className="inline-flex items-center gap-2 text-sm text-slate-600 dark:text-slate-300 cursor-pointer"><span>支持自提</span><input type="checkbox" checked={form.support_pickup} onChange={(event) => update({ support_pickup: event.target.checked })} /></label>
            </div>
            {form.shipping_method !== 'free' && form.shipping_method !== 'none' && <div className="grid grid-cols-1 md:grid-cols-2 gap-3"><div className="input-group"><label className="input-label">运费（元）</label><input type="number" className="input-ios" min="0" step="0.01" placeholder="0.00" value={form.postage} onChange={(event) => update({ postage: event.target.value })} /></div></div>}
            <div className="input-group"><label className="input-label">宝贝所在地</label><button type="button" className="input-ios text-left flex items-center gap-2" onClick={() => setShowAddressPicker(true)}><MapPin className="w-4 h-4 text-slate-500" /><span className="truncate flex-1">{form.address || '请选择宝贝所在地'}</span><ChevronRight className="w-4 h-4 text-slate-400" /></button></div>
          </section>
        </div>
      </div>
      <AddressPickerModal open={showAddressPicker} currentValue={form.address} onClose={() => setShowAddressPicker(false)} onSelect={(address, expectedText) => { update({ address, address_expected_text: expectedText }); setShowAddressPicker(false) }} />
    </>
  )
}

export default ProductPublishForm
