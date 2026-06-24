/**
 * 商品监控 - 采集账号（按分类的兜底采集账号配置）页面
 *
 * 功能：
 * 1. 按分类配置兜底采集账号（每个分类一条、无分类一条，账号可多选/全选）
 * 2. 当监控任务自身的采集账号不可用时，采集/卖家补全任务按 5 层链回退：
 *    任务账号 → 本用户·本分类 → 本用户·无分类 → 管理员·本分类 → 管理员·无分类
 */
import {
  getCollectFallbackAccounts,
  saveCollectFallbackAccounts,
  deleteCollectFallbackAccounts,
} from '@/api/collectFallbackAccount'
import { FallbackAccountManager } from './FallbackAccountManager'

export function CollectFallbackAccount() {
  return (
    <FallbackAccountManager
      title="采集账号"
      description="按分类配置兜底采集账号。当监控任务自身的采集账号不可用（未配置/失效）时，采集与卖家补全任务按「本分类→无分类→管理员」顺序回退使用兜底账号采集。"
      accountKind="采集"
      list={getCollectFallbackAccounts}
      save={saveCollectFallbackAccounts}
      remove={deleteCollectFallbackAccounts}
    />
  )
}

export default CollectFallbackAccount
