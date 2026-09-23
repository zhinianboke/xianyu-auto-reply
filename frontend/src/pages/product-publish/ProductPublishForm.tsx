/**
 * 单品发布左侧信息表单。
 * 将截图中的基础信息、规格、价格、发货和所在地交互集中管理。
 */
import { useState } from 'react'
import { ChevronRight, Loader2, MapPin, Trash2 } from 'lucide-react'
import type { PublishAccountCapability } from '@/api/productPublish'
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
  /**
   * 修改标题/描述时是否自动解锁类目并重新推荐。
   * 平台商品编辑（鱼小铺）必须传 false：解锁会触发推荐接口回写类目并清空
   * platform_attributes/brand/condition，导致只改标题也会覆盖平台已保存的成色、品牌等属性。
   */
  unlockCategoryOnTextChange?: boolean
  accountCapability?: PublishAccountCapability | null
  capabilityLoading?: boolean
}

export function ProductPublishForm({ form, setForm, accounts, onUploadSpecImage, showAccount = true, categoryLocked = false, onCategoryEdit, unlockCategoryOnTextChange = true, accountCapability = null, capabilityLoading = false }: ProductPublishFormProps) {
  const [showAddressPicker, setShowAddressPicker] = useState(false)
  // 未传账号能力时保持公共表单原有功能；只有明确检测为普通卖家才收起鱼小铺字段。
  const isFishShop = accountCapability?.is_fish_shop !== false
  const shippingOptions = isFishShop
    ? SHIPPING_OPTIONS
    : SHIPPING_OPTIONS.filter((option) => option.value !== 'template')
  const hasUnsupportedPersonalSpecifications = !isFishShop
    && (form.specifications.length > 0 || form.sku_rows.length > 0)

  const update = (patch: Partial<PublishForm>) => {
    if (unlockCategoryOnTextChange && (patch.title !== undefined || patch.description !== undefined) && onCategoryEdit) onCategoryEdit()
    setForm((current) => ({ ...current, ...patch }))
  }
  const updateSpecs = (specifications: ProductSpecification[], skuRows: SkuRow[]) => update({ specifications, sku_rows: skuRows, price: skuRows[0]?.price || form.price })

  const setShippingMethod = (shipping_method: ShippingMethod) => {
    update({ shipping_method, delivery_method: shipping_method === 'none' ? 'pickup' : 'express' })
  }

  return (
    <>
      <div className="vben-card relative">
        <div className="vben-card-header"><h2 className="vben-card-title">商品信息</h2></div>
        <div className="vben-card-body space-y-5">
          {showAccount && <div className="input-group">
            <label className="input-label">发布账号 <span className="text-red-500">*</span></label>
            <select className="input-ios" value={form.account_id} onChange={(event) => update({ account_id: event.target.value })}>
              <option value="">-- 请选择账号 --</option>
              {accounts.map((account: any) => (
                <option key={account.id} value={account.id}>
                  {`${account.note ? `${account.note} (${account.id})` : account.id}${account.enabled === false ? '（未启动）' : ''}`}
                </option>
              ))}
            </select>
            {accountCapability && <div className="mt-2 flex items-center gap-2 text-xs text-slate-500 dark:text-slate-400"><span className={`h-2 w-2 rounded-full ${accountCapability.is_fish_shop ? 'bg-emerald-500' : 'bg-slate-400'}`} /><span>{accountCapability.is_fish_shop ? '鱼小铺账号' : '普通卖家账号'}</span></div>}
          </div>}

          {hasUnsupportedPersonalSpecifications && (
            <div className="flex flex-col gap-3 rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-800 dark:border-amber-700 dark:bg-amber-900/20 dark:text-amber-300 sm:flex-row sm:items-center sm:justify-between">
              <span>当前表单仍包含鱼小铺规格数据，普通卖家发布前需要清除。</span>
              <button type="button" className="btn-ios-secondary flex-shrink-0 px-3 py-1.5 text-xs" onClick={() => updateSpecs([], [])}>
                <Trash2 className="h-3.5 w-3.5" />清除规格数据
              </button>
            </div>
          )}

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

          {isFishShop && <section className="space-y-3">
            <div className="flex items-center justify-between"><h3 className="text-base font-semibold text-slate-800 dark:text-slate-100">商品规格</h3><span className="text-xs text-slate-400">最多添加2个规格类型</span></div>
            <ProductSpecificationsEditor specifications={form.specifications} skuRows={form.sku_rows} onChange={updateSpecs} onUploadImage={onUploadSpecImage} />
          </section>}

          {(!isFishShop || form.specifications.length === 0) && (
            <section className="space-y-3">
              <h3 className="text-base font-semibold text-slate-800 dark:text-slate-100">价格</h3>
              <div className={`grid grid-cols-1 gap-3 ${isFishShop ? 'md:grid-cols-3' : 'md:grid-cols-2'}`}>
                <div className="input-group"><label className="input-label">价格 <span className="text-red-500">*</span></label><div className="relative"><span className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400">¥</span><input type="number" className="input-ios pl-8" min="0" step="0.01" placeholder="0.00" value={form.price} onChange={(event) => update({ price: event.target.value })} /></div></div>
                <div className="input-group"><label className="input-label">原价</label><div className="relative"><span className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400">¥</span><input type="number" className="input-ios pl-8" min="0" step="0.01" placeholder="0.00" value={form.original_price} onChange={(event) => update({ original_price: event.target.value })} /></div></div>
                {isFishShop && <div className="input-group"><label className="input-label">库存</label><input type="number" className="input-ios" min="1" step="1" value={form.quantity} onChange={(event) => update({ quantity: Math.max(1, Number(event.target.value) || 1) })} /></div>}
              </div>
              {isFishShop
                ? <p className="text-xs text-slate-400">鱼小铺软件服务费按成交额（含运费）的1.6%计收</p>
                : <p className="text-xs text-slate-400">基础软件服务费 = 成交额（含运费）*{accountCapability?.commission_config.percent ? `${Number(accountCapability.commission_config.percent) * 100}%` : '0.6%'}</p>}
            </section>
          )}

          <section className="space-y-3">
            <h3 className="text-base font-semibold text-slate-800 dark:text-slate-100">发货设置</h3>
            <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
              {shippingOptions.map((option) => (
                <label key={option.value} className="inline-flex items-center gap-1.5 text-sm text-slate-600 dark:text-slate-300 cursor-pointer">
                  <input type="radio" name="shipping_method" checked={form.shipping_method === option.value} onChange={() => setShippingMethod(option.value)} />{option.label}
                </label>
              ))}
              <label className="inline-flex items-center gap-2 text-sm text-slate-600 dark:text-slate-300 cursor-pointer"><span>支持自提</span><input type="checkbox" checked={form.support_pickup} onChange={(event) => update({ support_pickup: event.target.checked })} /></label>
            </div>
            {!isFishShop && form.shipping_method === 'template' && <p className="text-xs text-amber-600 dark:text-amber-400">普通卖家不支持运费模板，请重新选择发货方式</p>}
            {form.shipping_method !== 'free' && form.shipping_method !== 'none' && <div className="grid grid-cols-1 md:grid-cols-2 gap-3"><div className="input-group"><label className="input-label">运费（元）</label><input type="number" className="input-ios" min="0" step="0.01" placeholder="0.00" value={form.postage} onChange={(event) => update({ postage: event.target.value })} /></div></div>}
            <div className="input-group"><label className="input-label">宝贝所在地</label><button type="button" className="input-ios text-left flex items-center gap-2" onClick={() => setShowAddressPicker(true)}><MapPin className="w-4 h-4 text-slate-500" /><span className="truncate flex-1">{form.address || '请选择宝贝所在地'}</span><ChevronRight className="w-4 h-4 text-slate-400" /></button></div>
          </section>
        </div>
        {capabilityLoading && <div className="absolute inset-0 z-20 flex items-center justify-center rounded-lg bg-white/75 backdrop-blur-sm dark:bg-slate-800/75"><div className="flex items-center gap-2 text-sm font-medium text-slate-600 dark:text-slate-300"><Loader2 className="h-5 w-5 animate-spin text-blue-500" />正在检测账号发布能力...</div></div>}
      </div>
      <AddressPickerModal open={showAddressPicker} currentValue={form.address} onClose={() => setShowAddressPicker(false)} onSelect={(address, expectedText) => { update({ address, address_expected_text: expectedText }); setShowAddressPicker(false) }} />
    </>
  )
}

export default ProductPublishForm
