/** 用户管理中的结算记录：用户隔离分页、中文字典与逐条修改结果。 */
import { get, put } from '@/utils/request'
import type { SettlementRecord, SettlementRecordListData } from '@/api/payment'

export interface SettlementOption { value: string; label: string; enabled: boolean }
export interface AdminSettlementRecord extends SettlementRecord {
  revision: string
  status_label: string
  payment_type_label: string
}
export interface AdminSettlementList extends Omit<SettlementRecordListData, 'list'> {
  list: AdminSettlementRecord[]
  options: { statuses: SettlementOption[]; payment_types: SettlementOption[] }
}
interface SettlementResponse<T> { success: boolean; code: number; message: string; data: T | null }
export interface SettlementUpdate {
  status: string
  expected_revision: string
  reject_reason: string
  remark: string
}

/** 只查询选中用户的记录，分页和中文选项统一由后端提供。 */
export const getUserSettlements = (userId: number, page: number, pageSize: number) =>
  get<SettlementResponse<AdminSettlementList>>(`/api/v1/admin/users/${userId}/settlement-records`, { params: { page, page_size: pageSize } })

/** 提交原记录版本，防止两名管理员相互覆盖结果。 */
export const updateUserSettlement = (userId: number, recordId: number, payload: SettlementUpdate) =>
  put<SettlementResponse<AdminSettlementRecord>>(`/api/v1/admin/users/${userId}/settlement-records/${recordId}`, payload)
