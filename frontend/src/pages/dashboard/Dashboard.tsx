import { useEffect, useMemo, useState } from 'react'
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import {
  Calendar,
  ChevronDown,
  ChevronUp,
  ExternalLink,
  KeyRound,
  MessageSquare,
  PackageCheck,
  Shield,
  ShoppingCart,
  Users,
  type LucideIcon,
} from 'lucide-react'
import { getAccountStats } from '@/api/accounts'
import { type TodayStats, getTodayStats } from '@/api/admin'
import { type Advertisement, getPublicAds } from '@/api/advertisements'
import { getAllCards, type CardData } from '@/api/cards'
import { OrderAmountChart } from '@/components/common/OrderAmountChart'
import { PageLoading } from '@/components/common/Loading'
import { useAuthStore } from '@/store/authStore'
import { useUIStore } from '@/store/uiStore'

interface DashboardStats {
  totalAccounts: number
  totalKeywords: number
  activeAccounts: number
  totalOrders: number
  todayReplyCount: number
  yesterdayReplyCount: number
  usedAccountCount: number
  remainingAccountCount: number | null
  cardInventory: number
  enabledCardInventory: number
}

interface AdsData {
  carousel: Advertisement[]
  text: Advertisement[]
}

interface SummaryCard {
  label: string
  value: string | number
  subLabel: string
  percent?: string
  percentTone?: 'positive' | 'negative' | 'neutral'
  icon: LucideIcon
  tone: 'blue' | 'cyan' | 'green' | 'orange' | 'purple' | 'red'
}

interface TodayBarPoint {
  label: string
  value: number
  color: string
  isCurrency?: boolean
}

const emptyStats: DashboardStats = {
  totalAccounts: 0,
  totalKeywords: 0,
  activeAccounts: 0,
  totalOrders: 0,
  todayReplyCount: 0,
  yesterdayReplyCount: 0,
  usedAccountCount: 0,
  remainingAccountCount: null,
  cardInventory: 0,
  enabledCardInventory: 0,
}

const formatCount = (value: number | null | undefined) => {
  if (value === null || value === undefined) return '-'
  return value
}

const formatReplyPercent = (today: number, yesterday: number) => {
  if (!yesterday) {
    return {
      text: today > 0 ? '+100.0%' : '0.0%',
      tone: today > 0 ? 'positive' : 'neutral',
    } as const
  }

  const value = ((today - yesterday) / yesterday) * 100
  return {
    text: `${value > 0 ? '+' : ''}${value.toFixed(1)}%`,
    tone: value > 0 ? 'positive' : value < 0 ? 'negative' : 'neutral',
  } as const
}

const buildTodayBars = (stats: TodayStats): TodayBarPoint[] => [
  { label: '新增用户', value: stats.today_users, color: '#3b82f6' },
  { label: '新增账号', value: stats.today_accounts, color: '#22c55e' },
  { label: '今日订单', value: stats.today_orders, color: '#8b5cf6' },
  { label: '代销订单', value: stats.today_agent_orders ?? 0, color: '#06b6d4' },
  { label: '订单金额', value: Number(stats.today_amount || 0), color: '#f43f5e', isCurrency: true },
  { label: '已发货', value: stats.today_shipped, color: '#10b981' },
  { label: '待处理', value: stats.today_pending, color: '#f59e0b' },
]

function TodayStatsTooltip({
  active,
  payload,
}: {
  active?: boolean
  payload?: Array<{ value: number; payload: TodayBarPoint }>
}) {
  if (!active || !payload?.length) return null

  const item = payload[0].payload
  return (
    <div className="dashboard-chart-tooltip">
      <p>{item.label}</p>
      <strong>{item.isCurrency ? `¥${Number(item.value).toFixed(2)}` : item.value}</strong>
    </div>
  )
}

function SummaryMetricCard({ card }: { card: SummaryCard }) {
  const Icon = card.icon

  return (
    <div className="dashboard-metric-card">
      <div className="dashboard-metric-head">
        <div className={`dashboard-metric-icon tone-${card.tone}`}>
          <Icon className="w-4 h-4" />
        </div>
        <div className="dashboard-metric-title">{card.label}</div>
      </div>
      <div className="dashboard-metric-main">
        <strong>{card.value}</strong>
        {card.percent && (
          <span className={`dashboard-metric-percent tone-${card.percentTone || 'neutral'}`}>
            {card.percent}
          </span>
        )}
      </div>
      <div className="dashboard-metric-sub">{card.subLabel}</div>
    </div>
  )
}

function AdsPanel({
  adsData,
  adsLoading,
  carouselIndex,
  expandedTextAds,
  onCarouselChange,
  onTextAdToggle,
}: {
  adsData: AdsData
  adsLoading: boolean
  carouselIndex: number
  expandedTextAds: Set<number>
  onCarouselChange: (index: number) => void
  onTextAdToggle: (id: number) => void
}) {
  const currentCarouselAd = adsData.carousel[carouselIndex]

  return (
    <div className="dashboard-ads-grid">
      <section className="dashboard-ad-card">
        <div className="dashboard-ad-header">
          <h2>推荐广告</h2>
        </div>
        <div className="dashboard-carousel">
          {adsLoading ? (
            <div className="dashboard-ad-loading" />
          ) : currentCarouselAd ? (
            <a
              href={currentCarouselAd.link || '#'}
              target="_blank"
              rel="noopener noreferrer"
              className="dashboard-carousel-link"
            >
              {currentCarouselAd.image_url ? (
                <img src={currentCarouselAd.image_url} alt={currentCarouselAd.title} />
              ) : (
                <div className="dashboard-carousel-fallback">
                  <strong>{currentCarouselAd.title}</strong>
                </div>
              )}
              <div className="dashboard-carousel-caption">
                <strong>{currentCarouselAd.title}</strong>
                {currentCarouselAd.content && <p>{currentCarouselAd.content}</p>}
              </div>
            </a>
          ) : (
            <div className="dashboard-ad-placeholder">暂无推荐广告</div>
          )}

          {adsData.carousel.length > 1 && (
            <div className="dashboard-carousel-dots">
              {adsData.carousel.map((ad, index) => (
                <button
                  key={ad.id}
                  type="button"
                  className={index === carouselIndex ? 'is-active' : ''}
                  onClick={() => onCarouselChange(index)}
                  aria-label={`切换到广告 ${index + 1}`}
                />
              ))}
            </div>
          )}
        </div>
      </section>

      <section className="dashboard-ad-card">
        <div className="dashboard-ad-header">
          <h2>文字广告</h2>
        </div>
        <div className="dashboard-text-ads">
          {adsLoading ? (
            <div className="dashboard-ad-loading" />
          ) : adsData.text.length ? (
            adsData.text.map((ad) => {
              const expanded = expandedTextAds.has(ad.id)
              return (
                <article key={ad.id} className="dashboard-text-ad-item">
                  <div className="dashboard-text-ad-title">
                    <a href={ad.link || '#'} target="_blank" rel="noopener noreferrer">
                      <span>{ad.title}</span>
                      <ExternalLink className="w-3 h-3" />
                    </a>
                    <button
                      type="button"
                      onClick={() => onTextAdToggle(ad.id)}
                      aria-label={expanded ? '收起文字广告' : '展开文字广告'}
                    >
                      {expanded ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
                    </button>
                  </div>
                  {expanded && ad.content && (
                    <p className="dashboard-text-ad-content">{ad.content}</p>
                  )}
                </article>
              )
            })
          ) : (
            <div className="dashboard-ad-placeholder">广告位招租</div>
          )}
        </div>
      </section>
    </div>
  )
}

function TodayStatsChart({ stats }: { stats: TodayStats }) {
  const data = useMemo(() => buildTodayBars(stats), [stats])

  return (
    <section className="dashboard-today-card">
      <div className="dashboard-ad-header">
        <h2>
          <Calendar className="w-4 h-4" />
          今日统计（管理员）
        </h2>
      </div>
      <div className="dashboard-today-chart">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} margin={{ top: 10, right: 8, left: -8, bottom: 0 }}>
            <CartesianGrid
              strokeDasharray="3 3"
              stroke="currentColor"
              className="text-slate-200 dark:text-[#3a3a3c]"
              vertical={false}
            />
            <XAxis
              dataKey="label"
              tick={{ fontSize: 12 }}
              stroke="currentColor"
              className="text-slate-400 dark:text-slate-500"
              tickLine={false}
              axisLine={false}
            />
            <YAxis
              tick={{ fontSize: 12 }}
              stroke="currentColor"
              className="text-slate-400 dark:text-slate-500"
              tickLine={false}
              axisLine={false}
              tickFormatter={(value: number) => (value >= 1000 ? `${(value / 1000).toFixed(1)}k` : String(value))}
            />
            <Tooltip content={<TodayStatsTooltip />} cursor={{ fill: 'rgba(59, 130, 246, 0.08)' }} />
            <Bar dataKey="value" radius={[6, 6, 0, 0]} maxBarSize={46}>
              {data.map((item) => (
                <Cell key={item.label} fill={item.color} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
    </section>
  )
}

export function Dashboard() {
  const { addToast } = useUIStore()
  const { isAuthenticated, token, _hasHydrated, user } = useAuthStore()
  const [loading, setLoading] = useState(true)
  const [adsLoading, setAdsLoading] = useState(true)
  const [stats, setStats] = useState<DashboardStats>(emptyStats)
  const [todayStats, setTodayStats] = useState<TodayStats | null>(null)
  const [adsData, setAdsData] = useState<AdsData>({ carousel: [], text: [] })
  const [carouselIndex, setCarouselIndex] = useState(0)
  const [expandedTextAds, setExpandedTextAds] = useState<Set<number>>(new Set())

  const loadStats = async () => {
    const [accountStats, cards] = await Promise.all([
      getAccountStats(),
      getAllCards(),
    ])
    const cardRows: CardData[] = Array.isArray(cards) ? cards : []

    setStats({
      totalAccounts: accountStats.total_accounts,
      totalKeywords: accountStats.total_keywords,
      activeAccounts: accountStats.active_accounts,
      totalOrders: accountStats.total_orders,
      todayReplyCount: accountStats.today_reply_count,
      yesterdayReplyCount: accountStats.yesterday_reply_count,
      usedAccountCount: accountStats.used_account_count,
      remainingAccountCount: accountStats.remaining_account_count ?? null,
      cardInventory: cardRows.length,
      enabledCardInventory: cardRows.filter((card) => card.enabled !== false).length,
    })
  }

  const loadAds = async () => {
    try {
      setAdsLoading(true)
      const adsResult = await getPublicAds()
      if (adsResult.success && adsResult.data) {
        setAdsData(adsResult.data)
      }
    } finally {
      setAdsLoading(false)
    }
  }

  const loadTodayStats = async () => {
    if (!user?.is_admin) {
      setTodayStats(null)
      return
    }

    const result = await getTodayStats()
    if (result.success && result.data) {
      setTodayStats(result.data)
    }
  }

  const loadDashboard = async () => {
    if (!_hasHydrated || !isAuthenticated || !token) return

    try {
      setLoading(true)
      await Promise.all([
        loadStats(),
        loadAds(),
        loadTodayStats(),
      ])
    } catch {
      addToast({ type: 'error', message: '加载仪表盘数据失败' })
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    if (!_hasHydrated || !isAuthenticated || !token) return
    loadDashboard()
  }, [_hasHydrated, isAuthenticated, token, user?.is_admin])

  useEffect(() => {
    if (adsData.carousel.length <= 1) return

    const timer = window.setInterval(() => {
      setCarouselIndex((current) => (current + 1) % adsData.carousel.length)
    }, 4000)

    return () => window.clearInterval(timer)
  }, [adsData.carousel.length])

  useEffect(() => {
    if (carouselIndex >= adsData.carousel.length) {
      setCarouselIndex(0)
    }
  }, [adsData.carousel.length, carouselIndex])

  const replyPercent = formatReplyPercent(stats.todayReplyCount, stats.yesterdayReplyCount)
  const summaryCards: SummaryCard[] = [
    {
      label: '总账号数',
      value: stats.totalAccounts,
      subLabel: `启用账号数 ${stats.activeAccounts}`,
      icon: Users,
      tone: 'blue',
    },
    {
      label: '已用账号数',
      value: stats.usedAccountCount,
      subLabel: `可添加账号数 ${formatCount(stats.remainingAccountCount)}`,
      icon: Shield,
      tone: 'orange',
    },
    {
      label: '关键词',
      value: stats.totalKeywords,
      subLabel: '关键词规则总数',
      icon: KeyRound,
      tone: 'cyan',
    },
    {
      label: '今日回复',
      value: stats.todayReplyCount,
      subLabel: `昨日回复 ${stats.yesterdayReplyCount}`,
      percent: replyPercent.text,
      percentTone: replyPercent.tone,
      icon: MessageSquare,
      tone: 'purple',
    },
    {
      label: '订单数量',
      value: stats.totalOrders,
      subLabel: '总订单数',
      icon: ShoppingCart,
      tone: 'green',
    },
    {
      label: '卡券库存',
      value: stats.cardInventory,
      subLabel: `启用库存 ${stats.enabledCardInventory}`,
      icon: PackageCheck,
      tone: 'red',
    },
  ]

  const toggleTextAd = (id: number) => {
    setExpandedTextAds((current) => {
      const next = new Set(current)
      if (next.has(id)) {
        next.delete(id)
      } else {
        next.add(id)
      }
      return next
    })
  }

  if (loading) {
    return <PageLoading />
  }

  return (
    <div className="dashboard-wms-page">
      <div className="dashboard-stats-panel">
        {summaryCards.map((card) => (
          <SummaryMetricCard key={card.label} card={card} />
        ))}
      </div>

      <AdsPanel
        adsData={adsData}
        adsLoading={adsLoading}
        carouselIndex={carouselIndex}
        expandedTextAds={expandedTextAds}
        onCarouselChange={setCarouselIndex}
        onTextAdToggle={toggleTextAd}
      />

      <OrderAmountChart />

      {user?.is_admin && todayStats && <TodayStatsChart stats={todayStats} />}
    </div>
  )
}
