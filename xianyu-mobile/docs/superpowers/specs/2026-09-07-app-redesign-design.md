# App 蓝白重设计 Spec

> 日期：2026-09-07
> 决策：对齐 web 蓝白冷色系（主色 Blue-500 #3b82f6 + slate 灰阶中性色），保留 lucide 图标，自定义组件+StyleSheet 架构（与 web 的自研 .btn-ios/.vben-card 类同构，最忠实复刻），安卓能正常运行。后端/功能不动，只调 UI。

## 设计令牌（lib/theme.ts）

### 配色
亮色：primary `#3b82f6` / hover `#2563eb` / light `#dbeafe`；background `#f8fafc`(slate-50)；surface `#ffffff`；surfaceAlt `#f1f5f9`(slate-100，表头/三级底)；text `#1e293b`(slate-800)；textSecondary `#64748b`(slate-500)；textMuted `#94a3b8`(slate-400)；border `#e2e8f0`(slate-200)；borderLight `#f1f5f9`；success `#22c55e`；warning `#f59e0b`；error `#ef4444`；info `#0ea5e9`。
暗色：primary `#60a5fa`(blue-400)；background `#0f172a`(slate-900，弃纯黑)；surface `#1e293b`(slate-800)；surfaceAlt `#334155`(slate-700)；text `#f1f5f9`；textSecondary `#94a3b8`；textMuted `#64748b`；border `#334155`；borderLight `#1e293b`。

### 字体/圆角/阴影
- typography：largeTitle 24/700、title 20/700、heading 17/600、body 16/400、caption 14/400、small 12/400、micro 10/600。
- radius：sm 6、md 6、lg 8、xl 16、full 9999。（整体收紧对齐 web 6/8/16）
- shadow：card 极轻(opacity 0.03)、floating(opacity 0.08)。

## 组件库刷新（components/ui/）
- Button：rounded-md，4 变体(primary 蓝/secondary 白边/ghost/danger)，px16 py8，pressed 0.7，150ms。
- Card：rounded-lg，padding lg16，border borderLight，shadow.card 极轻。
- Badge(新增)：rounded sm，px8 py0.5，text-xs 500，变体 success/warning/danger/info/gray（100底/800字）。
- Input：rounded-md，px12 py8，focus border blue + ring。
- Switch：blue 选中态。
- Modal：overlay black/50，content rounded-lg，header/body/footer 结构。

## 页面（核心4先行，其余令牌自动传导）
消息/订单/商品/我的：清理残留死区，统计卡用 Badge，列表卡片化。其余 ~30 页靠 theme 令牌+组件自动升级。

## 不变
后端 API、功能逻辑、expo-router 路由结构、lucide 图标、zustand 状态。
