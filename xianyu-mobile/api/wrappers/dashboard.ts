import { getApiClient, extractError } from './client';

// ---------------------------------------------------------------------------
// 类型定义
// ---------------------------------------------------------------------------

export interface DashboardStats {
  total_accounts: number;
  active_accounts: number;
  today_replies: number;
  total_orders: number;
}

export interface Notification {
  id: number;
  type: string;
  title: string;
  content: string;
  read: boolean;
  created_at: string;
}

export interface Announcement {
  id: number;
  title: string;
  content: string;
  created_at: string;
}

// ---------------------------------------------------------------------------
// 内部工具：后端统一响应为 { success, message, data }
// ---------------------------------------------------------------------------

/** 后端统一响应为 { success, message, data }，抽出内部 data；未包裹则原样返回。
 *  数据分析接口存在双层包裹：外层 {success,message,data:{code,data:{真实统计}}}，
 *  故需反复解开 {success,data} 与 {code,data} 两种信封，最多 4 层防自引用死循环。 */
function unwrapData<T>(body: unknown): T {
  let cur: unknown = body;
  for (let i = 0; i < 4 && cur && typeof cur === 'object'; i++) {
    const obj = cur as Record<string, unknown>;
    const isEnvelope =
      ('success' in obj && 'data' in obj) || ('code' in obj && 'data' in obj);
    if (!isEnvelope) break;
    const inner = obj.data;
    if (inner == null) break;
    cur = inner;
  }
  return cur as T;
}

/** 从可能为数组、裸对象或分页包装的响应中提取数组 */
function unwrapArray<T>(data: unknown): T[] {
  const inner = unwrapData<unknown>(data);
  if (Array.isArray(inner)) return inner as T[];
  if (inner && typeof inner === 'object') {
    const obj = inner as Record<string, unknown>;
    // 兼容常见分页/列表包装
    for (const key of [
      'items',
      'list',
      'data',
      'notifications',
      'records',
      'results',
    ]) {
      if (Array.isArray(obj[key])) return obj[key] as T[];
    }
  }
  return [];
}

/** 宽松地将任意值转为 number，失败返回 0 */
function toNumber(value: unknown): number {
  if (typeof value === 'number') return Number.isFinite(value) ? value : 0;
  if (typeof value === 'string') {
    const n = Number(value);
    return Number.isFinite(n) ? n : 0;
  }
  if (typeof value === 'boolean') return value ? 1 : 0;
  return 0;
}

/** 宽松地将任意值转为 boolean（识别 read 状态的多种表达） */
function toBool(value: unknown): boolean {
  if (typeof value === 'boolean') return value;
  if (typeof value === 'number') return value !== 0;
  if (typeof value === 'string') {
    const v = value.toLowerCase();
    return v === 'true' || v === '1' || v === 'read' || v === 'yes';
  }
  // read_at / read_time 等时间字段非空即视为已读
  if (value != null && typeof value === 'object') return true;
  return false;
}

// ---------------------------------------------------------------------------
// 数据分析
// ---------------------------------------------------------------------------

/** 分布数据单项（活跃时段/地域/类目/流量来源等共用结构） */
export interface DistributionItem {
  profileCode: string;
  profileVal: string;
  usrRatio: number;
  usrRatioFormat: string;
}

/** 横幅指标项：name=指标字段名(对齐 web CORE_METRICS)，dataStr=展示值，ratio/ratioFormat=同比环比 */
export interface BannerDataItem {
  name: string;
  dataStr: string;
  ratio?: number;
  ratioFormat?: string;
  lastDataStr?: string;
  cycle?: string;
}

/** 数据分析概要：标量字段经索引签名保留，已知分布数组与横幅指标强类型化以便渲染 */
export interface AnalysisSummary {
  buyerActiveList?: DistributionItem[];
  buyerProvinceList?: DistributionItem[];
  itemCateList?: DistributionItem[];
  sceneSourceList?: DistributionItem[];
  /** 卖家数据罗盘横幅指标列表（由 graphBannerBenchData.bannerDataList 归一化上提） */
  bannerDataList?: BannerDataItem[];
  [key: string]: unknown;
}

/** 将原始分布数组归一化为 DistributionItem[]（缺 profileVal 的项丢弃） */
function normalizeDistribution(raw: unknown): DistributionItem[] {
  if (!Array.isArray(raw)) return [];
  const out: DistributionItem[] = [];
  for (const item of raw) {
    if (!item || typeof item !== 'object') continue;
    const o = item as Record<string, unknown>;
    const profileVal = o.profileVal != null ? String(o.profileVal) : '';
    if (!profileVal) continue;
    out.push({
      profileCode: o.profileCode != null ? String(o.profileCode) : '',
      profileVal,
      usrRatio: toNumber(o.usrRatio),
      usrRatioFormat: o.usrRatioFormat != null ? String(o.usrRatioFormat) : '',
    });
  }
  return out;
}

/** 将原始横幅指标项归一化为 BannerDataItem（缺 name 的项丢弃） */
function normalizeBannerItem(raw: unknown): BannerDataItem | null {
  if (!raw || typeof raw !== 'object') return null;
  const o = raw as Record<string, unknown>;
  const name = o.name != null ? String(o.name) : '';
  if (!name) return null;
  const item: BannerDataItem = {
    name,
    dataStr: o.dataStr != null ? String(o.dataStr) : '',
  };
  if (o.ratio != null) item.ratio = toNumber(o.ratio);
  if (o.ratioFormat != null) item.ratioFormat = String(o.ratioFormat);
  if (o.lastDataStr != null) item.lastDataStr = String(o.lastDataStr);
  if (o.cycle != null) item.cycle = String(o.cycle);
  return item;
}

/** 将原始横幅指标数组归一化（非数组或缺 name 的项过滤掉） */
function normalizeBannerList(raw: unknown): BannerDataItem[] {
  if (!Array.isArray(raw)) return [];
  const out: BannerDataItem[] = [];
  for (const item of raw) {
    const b = normalizeBannerItem(item);
    if (b) out.push(b);
  }
  return out;
}

/** 把原始概要对象的已知分布数组与横幅指标归一化后返回。
 *  卖家数据罗盘的横幅指标埋在 graphBannerBenchData.bannerDataList 下，
 *  此处上提到顶层 bannerDataList，便于上层直接消费。 */
function buildSummary(raw: unknown): AnalysisSummary {
  const obj: AnalysisSummary =
    raw && typeof raw === 'object' ? (raw as AnalysisSummary) : {};
  obj.buyerActiveList = normalizeDistribution(obj.buyerActiveList);
  obj.buyerProvinceList = normalizeDistribution(obj.buyerProvinceList);
  obj.itemCateList = normalizeDistribution(obj.itemCateList);
  obj.sceneSourceList = normalizeDistribution(obj.sceneSourceList);
  const benchRaw = obj.graphBannerBenchData;
  const bench =
    benchRaw && typeof benchRaw === 'object'
      ? (benchRaw as Record<string, unknown>)
      : null;
  const bannerSrc =
    bench && Array.isArray(bench.bannerDataList)
      ? bench.bannerDataList
      : obj.bannerDataList;
  obj.bannerDataList = normalizeBannerList(bannerSrc);
  return obj;
}

/**
 * 浏览概要（流量分布）
 *
 * 后端接口 schema（BrowseSummaryRequest）要求字段为
 * `{ account_id: number, date_type: string, date_range: string | null }`，
 * 其中 date_type 取 `recent1d/recent7d/recent30d/customDate`，
 * date_range 格式为 `yyyyMMdd|yyyyMMdd`。这里按真实 schema 适配，
 * 由 startDate/endDate 推导 date_type=customDate 与 date_range。
 */
export async function getBrowseSummary(
  accountId: string,
  startDate: string,
  endDate: string,
): Promise<AnalysisSummary> {
  const client = await getApiClient();
  const dateRange = `${startDate.replace(/-/g, '')}|${endDate.replace(/-/g, '')}`;
  const { data } = (await (client.POST as any)(
    '/api/v1/data-analysis/browse-summary',
    {
      body: {
        account_id: toNumber(accountId),
        date_type: 'customDate',
        date_range: dateRange,
      },
    },
  )) as { data?: unknown; error?: unknown };
  return buildSummary(unwrapData<unknown>(data));
}

/**
 * 卖家概要（卖家数据罗盘）
 *
 * 与 getBrowseSummary 同样的 schema（SellerSummaryRequest），适配方式一致。
 */
export async function getSellerSummary(
  accountId: string,
  startDate: string,
  endDate: string,
): Promise<AnalysisSummary> {
  const client = await getApiClient();
  const dateRange = `${startDate.replace(/-/g, '')}|${endDate.replace(/-/g, '')}`;
  const { data } = (await (client.POST as any)(
    '/api/v1/data-analysis/seller-summary',
    {
      body: {
        account_id: toNumber(accountId),
        date_type: 'customDate',
        date_range: dateRange,
      },
    },
  )) as { data?: unknown; error?: unknown };
  return buildSummary(unwrapData<unknown>(data));
}

// ---------------------------------------------------------------------------
// 通知（人脸验证通知：具备已读状态 + 标记已读接口）
// ---------------------------------------------------------------------------

/** 将后端返回的原始通知对象归一化为 Notification 结构（字段名宽松兼容） */
function normalizeNotification(raw: Record<string, unknown>): Notification {
  return {
    id: toNumber(raw.id ?? raw.notification_id ?? raw.pk),
    type: String(
      raw.type ?? raw.notification_type ?? raw.category ?? 'notification',
    ),
    title: String(raw.title ?? raw.subject ?? raw.message ?? '通知'),
    content: String(
      raw.content ?? raw.detail ?? raw.description ?? raw.message ?? '',
    ),
    read: toBool(
      raw.read ?? raw.is_read ?? raw.isRead ?? raw.read_at ?? raw.status === 'read',
    ),
    created_at: String(
      raw.created_at ??
        raw.created_time ??
        raw.create_time ??
        raw.time ??
        raw.timestamp ??
        '',
    ),
  };
}

/** 获取通知列表 */
export async function getNotifications(): Promise<Notification[]> {
  const client = await getApiClient();
  const { data } = (await (client.GET as any)(
    '/api/v1/face-verification/notifications',
  )) as { data?: unknown; error?: unknown };
  return unwrapArray<Record<string, unknown>>(data).map(normalizeNotification);
}

/** 标记通知为已读 */
export async function markNotificationRead(id: number): Promise<void> {
  const client = await getApiClient();
  await (client.POST as any)(
    `/api/v1/face-verification/notifications/${id}/read`,
  );
}

// ---------------------------------------------------------------------------
// 公告
// ---------------------------------------------------------------------------

/** 将后端返回的原始公告对象归一化为 Announcement 结构（字段名宽松兼容） */
function normalizeAnnouncement(raw: Record<string, unknown>): Announcement {
  return {
    id: toNumber(raw.id ?? raw.announcement_id ?? raw.pk),
    title: String(raw.title ?? ''),
    content: String(raw.content ?? ''),
    created_at: String(
      raw.created_at ?? raw.created_time ?? raw.create_time ?? '',
    ),
  };
}

/** 获取公告列表 */
export async function getAnnouncements(): Promise<Announcement[]> {
  const client = await getApiClient();
  const { data } = (await (client.GET as any)('/api/v1/announcements')) as {
    data?: unknown;
    error?: unknown;
  };
  return unwrapArray<Record<string, unknown>>(data).map(normalizeAnnouncement);
}

/** 创建公告 */
export async function createAnnouncement(
  title: string,
  content: string,
): Promise<void> {
  const client = await getApiClient();
  await (client.POST as any)('/api/v1/announcements', {
    body: { title, content },
  });
}

/** 更新公告 */
export async function updateAnnouncement(
  id: number,
  title: string,
  content: string,
): Promise<void> {
  const client = await getApiClient();
  await (client.PUT as any)(`/api/v1/announcements/${id}`, {
    body: { title, content },
  });
}

/** 删除公告 */
export async function deleteAnnouncement(id: number): Promise<void> {
  const client = await getApiClient();
  await (client.DELETE as any)(`/api/v1/announcements/${id}`);
}
