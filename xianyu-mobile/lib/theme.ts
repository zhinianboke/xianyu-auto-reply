// 设计令牌：对齐 web 蓝白冷色系（主色 Blue-500 + slate 灰阶中性色）。
// 改这一个文件，c.primary/c.background/... 会自动传导到全 app 所有页面。

export const colors = {
  light: {
    // 品牌主色 — 蓝（对齐 web ocean 预设）
    primary: '#3B82F6',
    primaryHover: '#2563EB',
    primaryLight: '#DBEAFE',
    // 背景
    background: '#F8FAFC', // slate-50
    surface: '#FFFFFF',
    surfaceAlt: '#F1F5F9', // slate-100，表头/统计块/三级底
    // 文字（slate 灰阶：800 主 / 500 次 / 400 弱）
    text: '#1E293B',
    textSecondary: '#64748B',
    textMuted: '#94A3B8',
    // 边框
    border: '#E2E8F0', // slate-200
    borderLight: '#F1F5F9', // slate-100
    // 状态色（对齐 web）
    error: '#EF4444',
    success: '#22C55E',
    warning: '#F59E0B',
    info: '#0EA5E9',
    // 特殊
    overlay: 'rgba(15,23,42,0.5)',
  },
  dark: {
    primary: '#60A5FA', // blue-400
    primaryHover: '#3B82F6',
    primaryLight: '#1E3A8F', // blue-900
    background: '#0F172A', // slate-900（弃纯黑，对齐 web）
    surface: '#1E293B', // slate-800
    surfaceAlt: '#334155', // slate-700
    text: '#F1F5F9', // slate-100
    textSecondary: '#94A3B8', // slate-400
    textMuted: '#64748B', // slate-500
    border: '#334155', // slate-700
    borderLight: '#1E293B', // slate-800
    error: '#F87171',
    success: '#4ADE80',
    warning: '#FBBF24',
    info: '#38BDF8',
    overlay: 'rgba(0,0,0,0.6)',
  },
};

export type ThemeColors = typeof colors.light;

// 紧凑布局：压大间距（xl/xxl/xxxl），保留 xs/sm（≥8px 触摸间距、≥16px 正文不变）
export const spacing = {
  xs: 4,
  sm: 8,
  md: 10,
  lg: 14,
  xl: 18,
  xxl: 24,
  xxxl: 32,
} as const;

export const typography = {
  largeTitle: { fontSize: 24, fontWeight: '700' as const, letterSpacing: -0.5 },
  title: { fontSize: 20, fontWeight: '700' as const, letterSpacing: -0.3 },
  heading: { fontSize: 17, fontWeight: '600' as const },
  body: { fontSize: 16, fontWeight: '400' as const, lineHeight: 24 },
  caption: { fontSize: 14, fontWeight: '400' as const, lineHeight: 20 },
  small: { fontSize: 12, fontWeight: '400' as const },
  micro: { fontSize: 10, fontWeight: '600' as const },
} as const;

export const radius = {
  none: 0,
  sm: 6,
  md: 6,
  lg: 8,
  xl: 16,
  full: 9999,
} as const;

export const shadow = {
  none: {},
  card: {
    // 极轻阴影，对齐 web 的“几乎无阴影”扁平感
    shadowColor: '#0F172A',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.04,
    shadowRadius: 3,
    elevation: 1,
  },
  floating: {
    shadowColor: '#0F172A',
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.08,
    shadowRadius: 12,
    elevation: 3,
  },
} as const;
