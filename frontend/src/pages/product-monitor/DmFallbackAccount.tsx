/**
 * 商品监控 - 私信账号（按分类的兜底私信账号配置）页面
 *
 * 功能：
 * 1. 按分类配置兜底私信账号（每个分类一条、无分类一条，账号可多选/全选）
 * 2. 当商品真实下单成功的账号发私信不可用时，私信任务按链回退：
 *    下单账号 → 本用户·本分类 → 本用户·无分类 → 管理员·本分类 → 管理员·无分类
 */
import {
  getDmFallbackAccounts,
  saveDmFallbackAccounts,
  deleteDmFallbackAccounts,
} from '@/api/dmFallbackAccount'
import { FallbackAccountManager } from './FallbackAccountManager'

export function DmFallbackAccount() {
  return (
    <FallbackAccountManager
      title="私信账号"
      description="按分类配置兜底私信账号。当商品真实下单成功的账号发私信不可用时，私信任务按「本分类→无分类→管理员」顺序回退使用兜底账号发私信。"
      accountKind="私信"
      list={getDmFallbackAccounts}
      save={saveDmFallbackAccounts}
      remove={deleteDmFallbackAccounts}
    />
  )
}

export default DmFallbackAccount
