import { useState } from 'react'
import { motion } from 'framer-motion'
import { Search, ShoppingBag, ExternalLink, MapPin, Heart } from 'lucide-react'
import { searchItems, SearchResultItem } from '@/api/search'
import { useUIStore } from '@/store/uiStore'
import { ButtonLoading } from '@/components/common/Loading'

export function ItemSearch() {
  const { addToast } = useUIStore()
  const [loading, setLoading] = useState(false)
  const [keyword, setKeyword] = useState('')
  const [results, setResults] = useState<SearchResultItem[]>([])
  const [total, setTotal] = useState(0)

  const handleSearch = async (e?: React.FormEvent) => {
    e?.preventDefault()
    if (!keyword.trim()) {
      addToast({ type: 'warning', message: '请输入搜索关键词' })
      return
    }

    addToast({ type: 'info', message: '正在搜索中，请稍候...' })
    
    try {
      setLoading(true)
      setResults([])
      const result = await searchItems(keyword.trim())
      
      if (result.success) {
        setResults(result.data || [])
        setTotal(result.total || result.data.length)
        
        if ((result.data || []).length === 0) {
          addToast({ type: 'info', message: '未找到相关商品' })
        } else {
          addToast({ type: 'success', message: `搜索完成，找到 ${result.data.length} 件商品` })
        }
        
        if (result.error) {
          addToast({ type: 'warning', message: result.error })
        }
      }
    } catch {
      addToast({ type: 'error', message: '搜索失败，请稍后重试' })
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="page-title">商品搜索</h1>
          <p className="page-description">在闲鱼平台搜索商品</p>
        </div>
        {total > 0 && (
          <span className="badge-primary">共 {total} 件商品</span>
        )}
      </div>

      {/* Search Bar */}
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        className="vben-card"
      >
        <div className="vben-card-body">
          <form onSubmit={handleSearch} className="flex flex-col md:flex-row gap-4">
            <div className="flex-1 relative">
              <Search className="absolute left-4 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400 dark:text-slate-500 z-10" />
              <input
                type="text"
                value={keyword}
                onChange={(e) => setKeyword(e.target.value)}
                placeholder="输入关键词搜索商品..."
                className="input-ios pl-12"
              />
            </div>
            <button
              type="submit"
              disabled={loading}
              className="btn-ios-primary w-full md:w-32 flex items-center justify-center"
            >
              {loading ? <ButtonLoading /> : '搜索'}
            </button>
          </form>
        </div>
      </motion.div>

      {/* Results */}
      {results.length > 0 && (
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.1 }}
          className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4"
        >
          {results.map((item, index) => (
            <motion.a
              key={item.item_id || index}
              href={item.item_url || `https://www.goofish.com/item?id=${item.item_id}`}
              target="_blank"
              rel="noopener noreferrer"
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: index * 0.03 }}
              className="vben-card group hover:shadow-lg transition-all duration-300 overflow-hidden"
            >
              {/* 商品图片 */}
              <div className="aspect-square bg-slate-100 dark:bg-slate-800 relative overflow-hidden">
                {item.main_image ? (
                  <img 
                    src={item.main_image} 
                    alt={item.title}
                    className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-300"
                    onError={(e) => {
                      (e.target as HTMLImageElement).style.display = 'none'
                    }}
                  />
                ) : (
                  <div className="absolute inset-0 flex items-center justify-center text-slate-300 dark:text-slate-600">
                    <ShoppingBag className="w-12 h-12" />
                  </div>
                )}
                {/* 外链图标 */}
                <div className="absolute top-2 right-2 opacity-0 group-hover:opacity-100 transition-opacity">
                  <div className="bg-black/50 rounded-full p-1.5">
                    <ExternalLink className="w-3.5 h-3.5 text-white" />
                  </div>
                </div>
              </div>
              
              {/* 商品信息 */}
              <div className="p-3">
                <h3 className="font-medium text-slate-900 dark:text-slate-100 line-clamp-2 text-sm mb-2 min-h-[2.5rem]">
                  {item.title}
                </h3>
                <div className="flex items-center justify-between mb-2">
                  <span className="text-lg font-bold text-red-500">{item.price}</span>
                  {item.want_count && item.want_count > 0 && (
                    <span className="text-xs text-slate-500 dark:text-slate-400 flex items-center gap-1">
                      <Heart className="w-3 h-3" />
                      {item.want_count}人想要
                    </span>
                  )}
                </div>
                <div className="flex items-center justify-between text-xs text-slate-500 dark:text-slate-400">
                  <span className="truncate max-w-[60%]">{item.seller_name || '-'}</span>
                  {item.area && (
                    <span className="flex items-center gap-0.5">
                      <MapPin className="w-3 h-3" />
                      {item.area}
                    </span>
                  )}
                </div>
                {/* 标签 */}
                {item.tags && item.tags.length > 0 && (
                  <div className="flex flex-wrap gap-1 mt-2">
                    {item.tags.slice(0, 3).map((tag, i) => (
                      <span key={i} className="text-xs px-1.5 py-0.5 bg-slate-100 dark:bg-slate-700 rounded text-slate-600 dark:text-slate-300">
                        {tag}
                      </span>
                    ))}
                  </div>
                )}
              </div>
            </motion.a>
          ))}
        </motion.div>
      )}

      {/* Empty State */}
      {!loading && results.length === 0 && (
        <div className="text-center py-12 text-slate-500 dark:text-slate-400">
          <ShoppingBag className="w-16 h-16 text-slate-300 dark:text-slate-600 mx-auto mb-4" />
          <p>输入关键词开始搜索</p>
        </div>
      )}

      {/* Loading State */}
      {loading && (
        <div className="text-center py-12">
          <div className="inline-flex items-center gap-2 text-blue-500">
            <ButtonLoading />
            <span>正在搜索中...</span>
          </div>
        </div>
      )}
    </div>
  )
}
