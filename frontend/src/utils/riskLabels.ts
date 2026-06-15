export const riskTypeLabels: Record<string, string> = {
  slider_captcha: '滑块验证',
  captcha: '验证码',
  login_required: '需要重新登录',
  cookie_expired: 'Cookie 失效',
  account_limited: '账号受限',
  reply_failed: '回复失败',
  system_error: '系统异常',
}

export const riskStatusLabels: Record<string, { label: string; color: string }> = {
  processing: { label: '处理中', color: 'orange' },
  success: { label: '成功', color: 'green' },
  failed: { label: '失败', color: 'red' },
  pending: { label: '待处理', color: 'orange' },
}

export const getRiskTypeLabel = (value?: string) => {
  if (!value) return '-'
  return riskTypeLabels[value] || value
}

export const getRiskStatus = (value?: string) => {
  if (!value) return { label: '-', color: 'gray' }
  return riskStatusLabels[value] || { label: value, color: 'gray' }
}
