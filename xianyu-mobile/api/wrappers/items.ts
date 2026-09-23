import { getApiClient } from './client';

// ---------------------------------------------------------------------------
// 闲鱼已发布商品列表（对齐 web src/api/items.ts 的 getItemsPaginated）
// 后端路由前缀: /api/v1/items
// ---------------------------------------------------------------------------

const PREFIX = '/api/v1/items';

/** 已发布商品（列表展示所需字段，原始响应字段更全，此处只取展示用） */
export interface XianyuItem {
  id: string | number;
  cookie_id: string;
  item_id: string;
  title: string;
  price: string;
  status: string; // item_status_desc，鱼小铺商品的状态文案（普通账号为空）
  quantity: string | number | null;
  /** 主图 URL：从 item_detail（平台商品 JSON）解析，缺失为 null */
  image: string | null;
  is_seller_item: boolean;
  created_at?: string;
}

export interface XianyuItemsPage {
  items: XianyuItem[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

/**
 * 从 item_detail（平台商品 JSON 字符串）解析主图 URL。
 * 平台 detail 的 imageInfoDOList 中 type=0 为图片，major="true" 为主图。
 */
function extractImage(itemDetail: unknown): string | null {
  if (typeof itemDetail !== 'string' || !itemDetail) return null;
  try {
    const parsed = JSON.parse(itemDetail) as { imageInfoDOList?: unknown };
    const list = parsed.imageInfoDOList;
    if (!Array.isArray(list)) return null;
    const entries = list as Array<Record<string, unknown>>;
    const major = entries.find(
      (e) => typeof e === 'object' && e && String(e.major).toLowerCase() === 'true' && e.url,
    );
    const anyImg = entries.find(
      (e) => typeof e === 'object' && e && e.url,
    );
    const entry = major || anyImg;
    return (entry?.url as string) ?? null;
  } catch {
    return null;
  }
}

function mapItem(raw: Record<string, unknown>): XianyuItem {
  return {
    id: raw.id as string | number,
    cookie_id: (raw.cookie_id as string) ?? '',
    item_id: (raw.item_id as string) ?? '',
    title: (raw.item_title as string) || (raw.title as string) || '',
    price: (raw.item_price as string) || (raw.price as string) || '',
    status: (raw.item_status_desc as string) ?? '',
    quantity: (raw.item_quantity ?? null) as string | number | null,
    image: extractImage(raw.item_detail),
    is_seller_item: Boolean(raw.is_seller_item),
    created_at: raw.created_at as string | undefined,
  };
}

/**
 * 获取闲鱼已发布商品列表（分页）。
 * 后端: GET /api/v1/items/paginated?page&page_size&cookie_id
 * 响应: { success, data: Item[], total, page, page_size, total_pages }
 * cookieId 为空时返回当前权限范围内所有账号的商品。
 */
export async function getXianyuItems(
  page: number = 1,
  pageSize: number = 20,
  cookieId?: string,
): Promise<XianyuItemsPage> {
  const client = await getApiClient();
  const query: Record<string, string | number> = { page, page_size: pageSize };
  if (cookieId) query.cookie_id = cookieId;

  const { data } = (await (client.GET as any)(`${PREFIX}/paginated`, {
    params: { query },
  })) as { data?: unknown; error?: unknown };

  const body = (data ?? {}) as Record<string, unknown>;
  // 后端响应为 { success, data: [...], total, ... }；兼容裸数组与 { items: [...] }
  const rawList = Array.isArray(body.data)
    ? (body.data as Record<string, unknown>[])
    : Array.isArray(body)
      ? (body as Record<string, unknown>[])
      : Array.isArray((body as Record<string, unknown>).items)
        ? ((body as Record<string, unknown>).items as Record<string, unknown>[])
        : [];

  const total = typeof body.total === 'number' ? body.total : rawList.length;
  return {
    items: rawList.map(mapItem),
    total,
    page: typeof body.page === 'number' ? body.page : page,
    page_size: typeof body.page_size === 'number' ? body.page_size : pageSize,
    total_pages:
      typeof body.total_pages === 'number'
        ? body.total_pages
        : total > 0 ? Math.ceil(total / pageSize) : 0,
  };
}
