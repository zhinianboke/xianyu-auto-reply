/** 结算弹窗状态：分页读取、错误反馈及单条保存，屏蔽过期请求并防止重复提交。 */
import { useCallback, useEffect, useRef, useState } from 'react'
import { getUserSettlements, updateUserSettlement, type AdminSettlementList, type SettlementUpdate } from '@/api/adminSettlements'
import { useUIStore } from '@/store/uiStore'
import { getApiErrorMessage } from '@/utils/apiError'

/** 绑定目标用户；返回真实分页数据、加载状态、错误、刷新和保存操作。 */
export function useAdminSettlements(userId: number) {
  const addToast = useUIStore(state => state.addToast)
  const [data, setData] = useState<AdminSettlementList | null>(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const mounted = useRef(false)
  const generation = useRef(0)
  const updating = useRef(false)
  const reading = useRef(false)

  const reportError = useCallback((message: string) => {
    setError(message)
    addToast({ type: 'error', message })
  }, [addToast])

  /** 保留后端分页口径；关闭或切换用户后旧请求不得更新界面。 */
  const load = useCallback((page = 1, pageSize = 20) => {
    if (updating.current) return
    const requestGeneration = ++generation.current
    reading.current = true
    setLoading(true)
    setError('')
    void getUserSettlements(userId, page, pageSize).then(response => {
      if (!mounted.current || requestGeneration !== generation.current) return
      if (!response.success || !response.data) {
        setData(null)
        reportError(response.message)
        return
      }
      setData(response.data)
    }).catch(reason => {
      if (!mounted.current || requestGeneration !== generation.current) return
      setData(null)
      reportError(getApiErrorMessage(reason, '无法读取结算记录，请检查网络后重试'))
    }).finally(() => {
      if (mounted.current && requestGeneration === generation.current) {
        reading.current = false
        setLoading(false)
      }
    })
  }, [userId, reportError])

  useEffect(() => {
    mounted.current = true
    setData(null)
    load()
    return () => { mounted.current = false; generation.current += 1 }
  }, [load])

  /** 保存成功只替换对应记录；业务失败保留编辑内容，异步错误明确提示。 */
  const save = (recordId: number, payload: SettlementUpdate): Promise<boolean> => {
    if (updating.current || reading.current || loading || !mounted.current) return Promise.resolve(false)
    updating.current = true
    setSaving(true)
    setError('')
    const requestGeneration = generation.current
    return updateUserSettlement(userId, recordId, payload).then(response => {
      if (!mounted.current || requestGeneration !== generation.current) return false
      if (!response.success || !response.data) { reportError(response.message); return false }
      const updated = response.data
      setData(current => current ? { ...current, list: current.list.map(record => record.id === updated.id ? updated : record) } : current)
      addToast({ type: 'success', message: response.message })
      return true
    }).catch(reason => {
      if (mounted.current && requestGeneration === generation.current) {
        reportError(getApiErrorMessage(reason, '结算结果保存失败，请检查网络后重试'))
      }
      return false
    }).finally(() => {
      updating.current = false
      if (mounted.current && requestGeneration === generation.current) setSaving(false)
    })
  }

  return { data, loading, saving, error, load, save }
}
