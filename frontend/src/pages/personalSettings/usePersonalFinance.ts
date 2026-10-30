/** 个人设置资金操作状态：收款码上传、提现及结算查询。 */
import { useState, useRef } from 'react'
import { uploadPaymentQrcode } from '@/api/settings'
import { createWithdraw, getSettlementRecords, type SettlementRecord } from '@/api/payment'
import { useUIStore } from '@/store/uiStore'
import type { usePersonalSettingsData } from './usePersonalSettingsData'

export function usePersonalFinance(settings: ReturnType<typeof usePersonalSettingsData>) {
  const { addToast } = useUIStore()
  const { balance, setBalance, paymentQrcode, paymentType, setPaymentQrcode, loadSettings } = settings
  const [showSettlementModal, setShowSettlementModal] = useState(false)
  const [settlementRecords, setSettlementRecords] = useState<SettlementRecord[]>([])
  const [settlementLoading, setSettlementLoading] = useState(false)
  const [settlementPage, setSettlementPage] = useState(1)
  const [settlementPageSize, setSettlementPageSize] = useState(20)
  const [settlementTotal, setSettlementTotal] = useState(0)
  const [settlementTotalPages, setSettlementTotalPages] = useState(0)
  const [withdrawing, setWithdrawing] = useState(false)
  const [showWithdrawModal, setShowWithdrawModal] = useState(false)
  const [withdrawAmount, setWithdrawAmount] = useState('')
  const [withdrawMinAmount, setWithdrawMinAmount] = useState('')  // 最低提现金额
  // 收款码状态
  const [showQrcodeModal, setShowQrcodeModal] = useState(false)
  const [uploadingQrcode, setUploadingQrcode] = useState(false)
  const qrcodeFileRef = useRef<HTMLInputElement>(null)

  const loadSettlementRecords = async (page: number = 1, pageSize: number = settlementPageSize) => {
    try {
      setSettlementLoading(true)
      const result = await getSettlementRecords(page, pageSize)
      if (result.success && result.data) {
        setSettlementRecords(result.data.list)
        setSettlementPage(result.data.page)
        setSettlementPageSize(result.data.page_size)
        setSettlementTotal(result.data.total)
        setSettlementTotalPages(result.data.total_pages)
      } else {
        setSettlementRecords([])
        addToast({ type: 'error', message: result.message || '加载结算记录失败' })
      }
    } catch (error: unknown) {
      const err = error as { response?: { data?: { detail?: string; message?: string } }; message?: string }
      const errorMsg = err?.response?.data?.detail || err?.response?.data?.message || err?.message || '加载结算记录失败'
      addToast({ type: 'error', message: errorMsg })
      setSettlementRecords([])
    } finally {
      setSettlementLoading(false)
    }
  }

  const handleUploadQrcode = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    try {
      setUploadingQrcode(true)
      const result = await uploadPaymentQrcode(file, paymentType)
      if (result.success && result.data?.image_url) {
        setPaymentQrcode(result.data.image_url)
        setShowQrcodeModal(false)
        addToast({ type: 'success', message: '收款码上传成功' })
      } else {
        addToast({ type: 'error', message: result.message || '上传失败' })
      }
    } catch {
      addToast({ type: 'error', message: '上传失败' })
    } finally {
      setUploadingQrcode(false)
      e.target.value = ''
    }
  }

  const handleWithdraw = async () => {
    if (!paymentQrcode) {
      addToast({ type: 'warning', message: '请先上传收款码' })
      return
    }

    if (!withdrawAmount.trim()) {
      addToast({ type: 'warning', message: '请输入提现金额' })
      return
    }

    const currentBalance = Number(balance || '0')
    const amountValue = Number(withdrawAmount.trim())

    // 校验最低提现金额
    if (withdrawMinAmount) {
      const minAmt = Number(withdrawMinAmount)
      if (minAmt > 0 && amountValue < minAmt) {
        addToast({ type: 'warning', message: `提现金额不能低于最低提现金额 ¥${minAmt}` })
        return
      }
    }

    if (!Number.isFinite(amountValue) || amountValue <= 0) {
      addToast({ type: 'warning', message: '提现金额必须大于0' })
      return
    }

    if (amountValue > currentBalance) {
      addToast({ type: 'warning', message: '提现金额不能大于当前余额' })
      return
    }

    try {
      setWithdrawing(true)
      const result = await createWithdraw(withdrawAmount.trim())
      if (result.success) {
        const nextBalance = result.data?.balance
        if (nextBalance !== undefined) {
          setBalance(nextBalance)
        } else {
          await loadSettings()
        }
        setWithdrawAmount('')
        setShowWithdrawModal(false)
        addToast({ type: 'success', message: result.message || '提现申请已提交，等待审核' })
        await loadSettlementRecords(1, settlementPageSize)
        setShowSettlementModal(true)
      } else {
        addToast({ type: 'error', message: result.message || '提现申请失败' })
      }
    } catch (error: unknown) {
      const err = error as { response?: { data?: { detail?: string; message?: string } }; message?: string }
      const errorMsg = err?.response?.data?.detail || err?.response?.data?.message || err?.message || '提现申请失败'
      addToast({ type: 'error', message: errorMsg })
    } finally {
      setWithdrawing(false)
    }
  }

  const openSettlementModal = async () => {
    setShowSettlementModal(true)
    await loadSettlementRecords(1, settlementPageSize)
  }

  return {
    showSettlementModal,
    setShowSettlementModal,
    settlementRecords,
    settlementLoading,
    settlementPage,
    settlementPageSize,
    setSettlementPageSize,
    settlementTotal,
    settlementTotalPages,
    withdrawing,
    showWithdrawModal,
    setShowWithdrawModal,
    withdrawAmount,
    setWithdrawAmount,
    withdrawMinAmount,
    setWithdrawMinAmount,
    showQrcodeModal,
    setShowQrcodeModal,
    uploadingQrcode,
    qrcodeFileRef,
    loadSettlementRecords,
    handleUploadQrcode,
    handleWithdraw,
    openSettlementModal
  }
}
