import { getApiClient, extractError } from './client';

// ---------------------------------------------------------------------------
// AI 回复设置（每个闲鱼账号独立配置）
// 后端路由前缀: /api/v1/ai-reply-settings、测试连接: /api/v1/ai-reply-test
// 字段对齐后端 AIReplySettings / AIReplySettingsUpdate 模型
// ---------------------------------------------------------------------------

export type AIProviderType =
  | 'openai_compatible'
  | 'anthropic'
  | 'gemini'
  | 'dashscope_app';

/** 各服务商默认 API 地址，切换服务商且地址为空/仍为旧默认值时联动填充 */
export const AI_PROVIDER_DEFAULT_BASE_URLS: Record<AIProviderType, string> = {
  openai_compatible: 'https://dashscope.aliyuncs.com/compatible-mode/v1',
  anthropic: 'https://api.anthropic.com',
  gemini: 'https://generativelanguage.googleapis.com',
  dashscope_app: 'https://dashscope.aliyuncs.com/api/v1/apps/{app_id}/completion',
};

export const AI_PROVIDER_OPTIONS: { value: AIProviderType; label: string }[] = [
  { value: 'openai_compatible', label: 'OpenAI兼容' },
  { value: 'anthropic', label: 'Anthropic' },
  { value: 'gemini', label: 'Gemini' },
  { value: 'dashscope_app', label: 'DashScope' },
];

export interface AIReplySettings {
  ai_enabled: boolean;
  provider_type?: AIProviderType;
  model_name?: string;
  api_key?: string;
  base_url?: string;
  max_bargain_rounds?: number;
  custom_prompts?: string;
  ai_time_range_start?: string;
  ai_time_range_end?: string;
  // 兼容旧字段
  enabled?: boolean;
}

/** 统一解包 { success, data } 包裹格式；未包裹则原样返回 */
function unwrap<T>(data: unknown): T | null {
  if (data && typeof data === 'object') {
    const obj = data as Record<string, unknown>;
    if ('data' in obj && obj.data != null) return obj.data as T;
  }
  return (data as T) ?? null;
}

/** 获取账号的 AI 回复设置 */
export async function getAccountAiSettings(
  accountId: string,
): Promise<AIReplySettings> {
  const client = await getApiClient();
  const { data, error } = (await (client.GET as any)(
    `/api/v1/ai-reply-settings/${encodeURIComponent(accountId)}`,
  )) as { data?: unknown; error?: unknown };
  if (error) throw await extractError(error);
  return unwrap<AIReplySettings>(data) ?? { ai_enabled: false };
}

/** 更新账号的 AI 回复设置 */
export async function updateAccountAiSettings(
  accountId: string,
  settings: Partial<AIReplySettings>,
): Promise<{ success: boolean; message?: string }> {
  const client = await getApiClient();
  const { data, error } = (await (client.PUT as any)(
    `/api/v1/ai-reply-settings/${encodeURIComponent(accountId)}`,
    { body: settings },
  )) as { data?: { success?: boolean; message?: string }; error?: unknown };
  if (error) throw await extractError(error);
  return { success: data?.success ?? true, message: data?.message };
}

/** 测试 AI 连接（后端用已保存的配置发起一次请求） */
export async function testAccountAiConnection(
  accountId: string,
): Promise<{ success: boolean; message?: string }> {
  const client = await getApiClient();
  const { data, error } = (await (client.POST as any)(
    `/api/v1/ai-reply-test/${encodeURIComponent(accountId)}`,
  )) as { data?: { success?: boolean; message?: string }; error?: unknown };
  if (error) throw await extractError(error);
  return { success: data?.success ?? true, message: data?.message };
}
