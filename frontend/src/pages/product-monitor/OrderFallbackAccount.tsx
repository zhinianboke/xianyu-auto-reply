/**
 * 商品监控 - 下单账号（按分类的兜底下单账号配置）页面
 *
 * 功能：
 * 1. 按分类配置兜底下单账号（每个分类一条、无分类一条，账号可多选/全选）
 * 2. 当监控任务自身的下单账号不可用时，定时下单/私信任务按 5 层链回退：
 *    任务账号 → 本用户·本分类 → 本用户·无分类 → 管理员·本分类 → 管理员·无分类
 */
import {
  getOrderFallbackAccounts,
  saveOrderFallbackAccounts,
  deleteOrderFallbackAccounts,
} from '@/api/orderFallbackAccount'
import { FallbackAccountManager } from './FallbackAccountManager'

export function OrderFallbackAccount() {
  return (
    <FallbackAccountManager
      title="下单账号"
      description="按分类配置兜底下单账号。当监控任务自身的下单账号不可用（删除/禁用/未配置/失效）时，定时下单任务按「本分类→无分类→管理员」顺序回退使用兜底账号下单。"
      accountKind="下单"
      list={getOrderFallbackAccounts}
      save={saveOrderFallbackAccounts}
      remove={deleteOrderFallbackAccounts}
    />
  )
}

export default OrderFallbackAccount
