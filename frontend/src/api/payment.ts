/**
 * 支付相关API
 * 
 * 功能：
 * 1. 查询支付渠道和子方式
 * 2. 创建充值订单并返回二维码或支付链接
 * 3. 查询充值订单状态
 */
import { post, get } from '@/utils/request'
import type { ApiResponse, PaymentChannel, ZzcodePayType } from '@/types'

const PAYMENT_PREFIX = '/api/v1/payment'

/** 充值订单响应数据 */
export interface RechargeData {
  order_id: number
  order_no: string
  amount: string
  status: 'pending' | 'paid' | 'expired' | 'failed'
  channel: PaymentChannel
  pay_type?: ZzcodePayType | null
  pay_target_kind?: 'qrcode' | 'payurl' | 'urlscheme' | null
  qr_code?: string | null
  pay_url?: string | null
}

export interface PaymentOption {
  value: ZzcodePayType
  label: string
}

export interface PaymentOptions {
  channel: PaymentChannel
  channel_label: string
  pay_types: PaymentOption[]
}

export interface PaymentConfigOptions {
  channels: Array<{ value: PaymentChannel; label: string }>
  pay_types: PaymentOption[]
}

/** 充值订单状态 */
export interface RechargeStatus {
  order_id: number
  order_no: string
  amount: string
  status: 'pending' | 'paid' | 'expired' | 'failed'
  trade_no?: string
  paid_at?: string
  created_at?: string
}

/** 创建充值订单 */
export const createRecharge = async (amount: string, payType?: ZzcodePayType): Promise<{
  success: boolean
  message?: string
  data?: RechargeData
}> => {
  return post(`${PAYMENT_PREFIX}/recharge`, { amount, pay_type: payType || null })
}

/** 查询当前用户可用的支付渠道和子方式。 */
export const getPaymentOptions = (): Promise<ApiResponse<PaymentOptions>> => get(`${PAYMENT_PREFIX}/options`)

/** 查询管理员支付配置页使用的数据字典选项。 */
export const getPaymentConfigOptions = (): Promise<ApiResponse<PaymentConfigOptions>> => get(`${PAYMENT_PREFIX}/config-options`)

/** 查询充值订单状态 */
export const getRechargeStatus = async (orderNo: string): Promise<{
  success: boolean
  message?: string
  data?: RechargeStatus
}> => {
  return get(`${PAYMENT_PREFIX}/recharge/${orderNo}`)
}

export interface SettlementRecord {
  id: number
  alipay_id?: string
  payment_type?: 'alipay' | 'wechat'
  payment_qrcode?: string
  amount: string
  status: 'pending_review' | 'approved' | 'rejected' | 'paid'
  remark?: string
  reject_reason?: string
  created_at?: string
  updated_at?: string
}

export interface SettlementRecordListData {
  list: SettlementRecord[]
  total: number
  page: number
  page_size: number
  total_pages: number
}

/** 创建提现申请 */
export const createWithdraw = async (amount: string): Promise<{
  success: boolean
  message?: string
  data?: {
    id: number
    amount: string
    status: string
    alipay_id: string
    balance: string
    created_at?: string
  }
}> => {
  return post(`${PAYMENT_PREFIX}/withdraw`, { amount })
}

/** 查询结算记录 */
export const getSettlementRecords = async (page: number = 1, pageSize: number = 20): Promise<{
  success: boolean
  message?: string
  data?: SettlementRecordListData
}> => {
  return get(`${PAYMENT_PREFIX}/settlement-records?page=${page}&page_size=${pageSize}`)
}
