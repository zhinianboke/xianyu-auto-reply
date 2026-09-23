// ============ 订单状态展示映射（移植自前端 orderStatus.ts，适配 RN） ============
// 由 components/OrdersPanel.tsx 与 app/(tabs)/orders/index.tsx 的重复实现合并而来。

export type Tone = 'warning' | 'info' | 'success' | 'muted';

export type StatusMeta = { label: string; tone: Tone };

export const ORDER_STATUS_META: Record<string, StatusMeta> = {
  pending_payment: { label: '待付款', tone: 'warning' },
  pending_ship: { label: '待发货', tone: 'info' },
  pending: { label: '待发货', tone: 'info' },
  paid: { label: '待发货', tone: 'info' },
  shipped: { label: '已发货', tone: 'success' },
  completed: { label: '交易成功', tone: 'success' },
  cancelled: { label: '交易关闭', tone: 'muted' },
  closed: { label: '交易关闭', tone: 'muted' },
  refunding: { label: '退款中', tone: 'warning' },
  refunded: { label: '已退款', tone: 'muted' },
};

export function getStatusMeta(status: string): StatusMeta {
  return ORDER_STATUS_META[status] || { label: status || '未知状态', tone: 'muted' };
}

/** 状态标签配色：浅色/深色分别给出背景与文字色 */
export function toneColors(tone: Tone, dark: boolean): { bg: string; fg: string } {
  switch (tone) {
    case 'warning':
      return dark
        ? { bg: '#3A2A00', fg: '#FF9F0A' }
        : { bg: '#FFF6E5', fg: '#C77700' };
    case 'info':
      return dark
        ? { bg: '#0C2A3A', fg: '#7DD3FC' }
        : { bg: '#E0F2FE', fg: '#0379C4' };
    case 'success':
      return dark
        ? { bg: '#0B3A1E', fg: '#30D158' }
        : { bg: '#E6F7EC', fg: '#1A7F45' };
    case 'muted':
    default:
      return dark
        ? { bg: '#2A2A2D', fg: '#AEAEB2' }
        : { bg: '#EFEFF0', fg: '#8A8A8E' };
  }
}

export function formatDateTime(iso: string): string {
  if (!iso) return '';
  const d = new Date(iso);
  if (isNaN(d.getTime())) return iso;
  const pad = (n: number) => n.toString().padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(
    d.getHours(),
  )}:${pad(d.getMinutes())}`;
}
