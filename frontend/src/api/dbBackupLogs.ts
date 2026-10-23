/**
 * 数据库备份日志 API。
 *
 * 提供分页查询、文件下载、单条删除和批量删除能力。
 */
import request, { del, get, post } from '@/utils/request'

const API_PREFIX = '/api/v1'

export interface DbBackupLog {
  id: number
  status: string
  file_name: string | null
  file_path: string | null
  file_size: number | null
  table_count: number | null
  total_rows: number | null
  duration_ms: number | null
  error_message: string | null
  downloadable: boolean
  created_at: string
}

interface DbBackupLogListResponse {
  success: boolean
  code?: number
  message?: string
  data?: DbBackupLog[]
  total?: number
}

interface DeleteDbBackupLogResponse {
  success: boolean
  code?: number
  message?: string
  data?: { deleted: number } | null
}

/** 分页查询数据库备份日志。 */
export const getDbBackupLogs = async (params?: {
  page?: number
  pageSize?: number
  status?: string
  start_date?: string
  end_date?: string
}): Promise<DbBackupLogListResponse> => {
  const query = new URLSearchParams()
  const page = params?.page || 1
  const pageSize = params?.pageSize || 20
  query.set('limit', String(pageSize))
  query.set('offset', String((page - 1) * pageSize))
  if (params?.status) query.set('status', params.status)
  if (params?.start_date) query.set('start_date', params.start_date)
  if (params?.end_date) query.set('end_date', params.end_date)

  const result = await get<DbBackupLogListResponse>(
    `${API_PREFIX}/db-backup-logs?${query.toString()}`,
  )
  return {
    success: Boolean(result.success),
    code: result.code,
    data: result.data || [],
    total: result.total,
    message: result.message,
  }
}

/** 下载数据库备份文件，并解析后端返回的 JSON 业务错误。 */
export const downloadDbBackupFile = async (
  logId: number,
): Promise<{ success: boolean; blob?: Blob; filename?: string; message?: string }> => {
  const response = await request.get<Blob>(`${API_PREFIX}/db-backup-logs/${logId}/download`, {
    responseType: 'blob',
  })

  const contentType = String(response.headers['content-type'] || '')
  if (contentType.includes('application/json')) {
    const data = JSON.parse(await response.data.text()) as { message?: string }
    return { success: false, message: data.message || '下载失败' }
  }

  const disposition = String(response.headers['content-disposition'] || '')
  const match = disposition.match(/filename\*?=(?:UTF-8'')?["']?([^"';]+)["']?/i)
  const filename = match ? decodeURIComponent(match[1]) : `backup_${logId}.sql.gz`
  return { success: true, blob: response.data, filename }
}

/** 删除单条数据库备份日志及其关联文件。 */
export const deleteDbBackupLog = async (
  logId: number,
): Promise<DeleteDbBackupLogResponse> => {
  return del(`${API_PREFIX}/db-backup-logs/${logId}`)
}

/** 批量删除数据库备份日志及其关联文件。 */
export const batchDeleteDbBackupLogs = async (
  logIds: number[],
): Promise<DeleteDbBackupLogResponse> => {
  return post(`${API_PREFIX}/db-backup-logs/batch-delete`, { ids: logIds })
}
