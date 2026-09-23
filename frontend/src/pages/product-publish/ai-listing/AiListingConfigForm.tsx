/**
 * AI 铺货配置表单
 *
 * 功能：
 * 1. 新增/编辑一套 AI 铺货配置（文案接口必填，图片接口按开关显示）
 * 2. 密钥统一用公共 PasswordInput，编辑时留空表示不修改
 * 3. 支持从服务商拉取模型列表辅助填写模型名称
 */
import { useState } from 'react'
import { Loader2, RefreshCw, X } from 'lucide-react'
import {
  createAiListingConfig,
  getAiListingModels,
  updateAiListingConfig,
  type AiListingConfig,
  type AiListingConfigParams,
} from '@/api/aiListing'
import { PasswordInput } from '@/components/common/PasswordInput'
import { useUIStore } from '@/store/uiStore'
import { getApiErrorMessage } from '@/utils/apiError'
import { clampNumberInput } from '@/utils/number'

/** 新增时的表单默认值 */
const defaultForm: AiListingConfigParams = {
  name: '',
  provider_type: 'openai_compatible',
  text_base_url: '',
  text_api_key: '',
  text_model: '',
  text_temperature: 0.7,
  text_max_tokens: 2048,
  prompt_template: '',
  image_enabled: false,
  image_base_url: '',
  image_api_key: '',
  image_model: '',
  image_size: '1024x1024',
  image_count: 1,
}

/** 把已保存的配置转成表单值（密钥不回填，留空表示不修改） */
function configToForm(config: AiListingConfig): AiListingConfigParams {
  return {
    name: config.name,
    provider_type: config.provider_type,
    text_base_url: config.text_base_url,
    text_api_key: '',
    text_model: config.text_model,
    text_temperature: config.text_temperature,
    text_max_tokens: config.text_max_tokens,
    prompt_template: config.prompt_template,
    image_enabled: config.image_enabled,
    image_base_url: config.image_base_url,
    image_api_key: '',
    image_model: config.image_model,
    image_size: config.image_size,
    image_count: config.image_count,
  }
}

interface AiListingConfigFormProps {
  /** 编辑的配置；为 null 表示新增 */
  config: AiListingConfig | null
  /** 保存成功回调 */
  onSaved: () => void
  /** 返回列表回调 */
  onCancel: () => void
}

export function AiListingConfigForm({ config, onSaved, onCancel }: AiListingConfigFormProps) {
  const { addToast } = useUIStore()
  const isEdit = Boolean(config)

  const [form, setForm] = useState<AiListingConfigParams>(config ? configToForm(config) : defaultForm)
  const [saving, setSaving] = useState(false)
  const [models, setModels] = useState<Array<{ id: string; name: string }>>([])
  const [loadingModels, setLoadingModels] = useState(false)

  const handleLoadModels = async () => {
    if (!form.text_base_url.trim()) {
      addToast({ type: 'warning', message: '请先填写文案接口地址' })
      return
    }
    setLoadingModels(true)
    try {
      const res = await getAiListingModels({
        provider_type: form.provider_type,
        base_url: form.text_base_url.trim(),
        api_key: form.text_api_key.trim() || undefined,
        config_id: config?.id,
      })
      if (!res.success || !res.data) {
        addToast({ type: 'error', message: res.message || '拉取模型列表失败' })
        return
      }
      setModels(res.data.models)
      addToast({ type: 'success', message: `已获取 ${res.data.models.length} 个模型` })
    } catch (error) {
      addToast({ type: 'error', message: getApiErrorMessage(error, '拉取模型列表失败') })
    } finally {
      setLoadingModels(false)
    }
  }

  const handleSave = async () => {
    if (!form.name.trim()) {
      addToast({ type: 'warning', message: '请填写配置名称' })
      return
    }
    if (!form.text_base_url.trim() || !form.text_model.trim()) {
      addToast({ type: 'warning', message: '请填写文案接口地址与模型名称' })
      return
    }
    if (!isEdit && !form.text_api_key.trim()) {
      addToast({ type: 'warning', message: '请填写文案接口密钥' })
      return
    }
    if (form.image_enabled && (!form.image_base_url?.trim() || !form.image_model?.trim())) {
      addToast({ type: 'warning', message: '启用AI图片生成时请填写图片接口地址与模型' })
      return
    }

    setSaving(true)
    try {
      const res = config ? await updateAiListingConfig(config.id, form) : await createAiListingConfig(form)
      if (!res.success) {
        addToast({ type: 'error', message: res.message || '保存配置失败' })
        return
      }
      addToast({ type: 'success', message: res.message || '配置已保存' })
      onSaved()
    } catch (error) {
      addToast({ type: 'error', message: getApiErrorMessage(error, '保存配置失败') })
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-slate-900 dark:text-slate-100">
          {isEdit ? '编辑配置' : '新增配置'}
        </h3>
        <button className="btn-ios-secondary btn-sm" onClick={onCancel} disabled={saving}>
          <X className="w-3.5 h-3.5" />返回列表
        </button>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <div className="input-group">
          <label className="input-label">配置名称</label>
          <input
            className="input-ios"
            placeholder="如：数码配件文案"
            value={form.name}
            onChange={e => setForm({ ...form, name: e.target.value })}
          />
        </div>
        <div className="input-group">
          <label className="input-label">文案接口地址</label>
          <input
            className="input-ios"
            placeholder="https://dashscope.aliyuncs.com/compatible-mode/v1"
            value={form.text_base_url}
            onChange={e => setForm({ ...form, text_base_url: e.target.value })}
          />
        </div>
        <div className="input-group">
          <label className="input-label">
            文案接口密钥{isEdit && <span className="input-hint">（留空表示不修改）</span>}
          </label>
          <PasswordInput
            value={form.text_api_key}
            onChange={value => setForm({ ...form, text_api_key: value })}
            placeholder={isEdit ? '留空则沿用已保存的密钥' : '请输入密钥'}
          />
        </div>
        <div className="input-group">
          <label className="input-label">文案模型</label>
          <div className="flex gap-2">
            <input
              className="input-ios flex-1"
              placeholder="如：qwen-plus"
              value={form.text_model}
              onChange={e => setForm({ ...form, text_model: e.target.value })}
            />
            <button className="btn-ios-secondary btn-sm" onClick={handleLoadModels} disabled={loadingModels}>
              {loadingModels ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <RefreshCw className="w-3.5 h-3.5" />}
              模型
            </button>
          </div>
          {models.length > 0 && (
            <select
              className="input-ios mt-2"
              value={form.text_model}
              onChange={e => setForm({ ...form, text_model: e.target.value })}
            >
              <option value="">请选择模型</option>
              {models.map(model => <option key={model.id} value={model.id}>{model.name}</option>)}
            </select>
          )}
        </div>
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <div className="input-group">
          <label className="input-label">温度</label>
          <input
            type="number" step="0.1" min="0" max="2" className="input-ios"
            value={form.text_temperature}
            onChange={e => setForm({ ...form, text_temperature: clampNumberInput(e.target.value, 0, 2, 0.7) })}
          />
        </div>
        <div className="input-group">
          <label className="input-label">最大 token</label>
          <input
            type="number" min="256" max="32768" className="input-ios"
            value={form.text_max_tokens}
            onChange={e => setForm({ ...form, text_max_tokens: clampNumberInput(e.target.value, 256, 32768, 2048) })}
          />
        </div>
      </div>

      <div className="input-group">
        <label className="input-label">
          提示词模板<span className="input-hint">（可空，支持 {'{count}'} {'{keyword}'} {'{hints}'} 占位符）</span>
        </label>
        <textarea
          className="input-ios min-h-[80px]"
          placeholder="留空则使用内置模板"
          value={form.prompt_template || ''}
          onChange={e => setForm({ ...form, prompt_template: e.target.value })}
        />
      </div>

      <div className="rounded-lg border border-slate-200 dark:border-slate-700 p-3 space-y-3">
        <label className="checkbox-label">
          <input
            type="checkbox" className="checkbox-ios"
            checked={form.image_enabled}
            onChange={e => setForm({ ...form, image_enabled: e.target.checked })}
          />
          <span>启用 AI 图片生成（关闭时使用启动任务时选择的兜底图片）</span>
        </label>

        {form.image_enabled && (
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div className="input-group">
              <label className="input-label">图片接口地址</label>
              <input
                className="input-ios" placeholder="https://api.example.com/v1"
                value={form.image_base_url || ''}
                onChange={e => setForm({ ...form, image_base_url: e.target.value })}
              />
            </div>
            <div className="input-group">
              <label className="input-label">
                图片接口密钥{isEdit && <span className="input-hint">（留空表示不修改）</span>}
              </label>
              <PasswordInput
                value={form.image_api_key}
                onChange={value => setForm({ ...form, image_api_key: value })}
                placeholder={isEdit ? '留空则沿用已保存的密钥' : '请输入密钥'}
              />
            </div>
            <div className="input-group">
              <label className="input-label">图片模型</label>
              <input
                className="input-ios" placeholder="如：wanx-v1"
                value={form.image_model || ''}
                onChange={e => setForm({ ...form, image_model: e.target.value })}
              />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="input-group">
                <label className="input-label">图片尺寸</label>
                <input
                  className="input-ios" placeholder="1024x1024"
                  value={form.image_size}
                  onChange={e => setForm({ ...form, image_size: e.target.value })}
                />
              </div>
              <div className="input-group">
                <label className="input-label">每条张数</label>
                <input
                  type="number" min="1" max="9" className="input-ios"
                  value={form.image_count}
                  onChange={e => setForm({ ...form, image_count: clampNumberInput(e.target.value, 1, 9, 1) })}
                />
              </div>
            </div>
          </div>
        )}
      </div>

      <div className="flex justify-end gap-2">
        <button className="btn-ios-secondary" onClick={onCancel} disabled={saving}>取消</button>
        <button className="btn-ios-primary" onClick={handleSave} disabled={saving}>
          {saving ? <><Loader2 className="w-4 h-4 animate-spin" />保存中...</> : '保存配置'}
        </button>
      </div>
    </div>
  )
}

export default AiListingConfigForm


