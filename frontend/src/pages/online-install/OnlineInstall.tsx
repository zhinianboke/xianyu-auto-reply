/** 公开导航下的在线安装页面：SSH 密码 / 私钥认证、固定脚本说明、实时日志和安装耗时。 */
import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { CheckCircle2, Clock, Loader2, Play, Server, Terminal, Wifi, XCircle } from 'lucide-react'
import { AuthNavbar, PublicPageFooter } from '@/components/common/AuthNavbar'
import { ConfirmModal } from '@/components/common/ConfirmModal'
import { PasswordInput } from '@/components/common/PasswordInput'
import type { InstallConnection } from '@/api/onlineInstall'
import { cn } from '@/utils/cn'
import { useOnlineInstall } from './useOnlineInstall'

const INSTALL_COMMAND = "curl -fsSL https://xy-update.zhinianboke.com/deploy.sh | sed 's/\\r$//' | bash"

type InstallForm = Omit<InstallConnection, 'auth_method'> & {
  auth_method: 'password' | 'private_key'
  password: string
  private_key: string
  private_key_passphrase: string
}

/** 无需登录展示 SSH 安装表单与当前浏览器会话的安装日志。 */
export function OnlineInstall() {
  const install = useOnlineInstall()
  const [form, setForm] = useState<InstallForm>({ host: '', port: 22, username: 'root', auth_method: 'password', password: '', private_key: '', private_key_passphrase: '' })
  const [confirming, setConfirming] = useState(false)
  const [autoScroll, setAutoScroll] = useState(true)
  const formRef = useRef<HTMLFormElement>(null)
  const logRef = useRef<HTMLPreElement>(null)
  const busy = install.restoring || install.testing || install.submitting || install.running || install.polling || (!!install.taskId && !install.canReset)
  const connectedForm: InstallConnection = {
    host: form.host.trim(), port: form.port, username: form.username.trim(),
    ...(form.auth_method === 'private_key'
      ? { auth_method: 'private_key' as const, private_key: form.private_key, private_key_passphrase: form.private_key_passphrase }
      : { auth_method: 'password' as const, password: form.password }),
  }
  const { clearConnectionTest } = install

  useEffect(() => { clearConnectionTest() }, [form, clearConnectionTest])

  useEffect(() => {
    if (autoScroll && logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight
  }, [install.logs, autoScroll])

  return (
    <div className="min-h-screen bg-slate-50 transition-colors duration-200 dark:bg-slate-900">
      <AuthNavbar />
      <main className="mx-auto max-w-6xl px-3 pb-8 pt-20 sm:px-6">
        <nav aria-label="面包屑" className="mb-4 flex items-center gap-2 text-sm text-slate-500 dark:text-slate-400">
          <Link to="/" className="hover:text-[rgb(var(--color-primary))]">首页</Link><span>/</span><span className="text-slate-800 dark:text-slate-100">在线安装</span>
        </nav>
        <h1 className="text-xl font-semibold text-slate-900 dark:text-white sm:text-2xl">在线安装</h1>
        <p className="mb-6 mt-2 text-sm text-slate-500 dark:text-slate-400">通过 SSH 连接服务器并执行安装脚本，实时查看安装输出和结果。</p>
        <div className="grid gap-5 lg:grid-cols-[minmax(0,2fr)_minmax(0,3fr)]">
          <section className="overflow-hidden rounded-lg border border-slate-200 bg-white shadow-sm dark:border-slate-700 dark:bg-slate-800">
            <h2 className="flex items-center gap-2 border-b border-slate-200 px-4 py-3 font-semibold text-slate-800 dark:border-slate-700 dark:text-slate-100"><Server className="h-4 w-4 text-[rgb(var(--color-primary))]" />SSH 连接配置</h2>
            <form ref={formRef} onSubmit={event => { event.preventDefault(); if (!busy) setConfirming(true) }} className="relative space-y-4 p-4 sm:p-5">
              <label className="block text-sm font-medium text-slate-700 dark:text-slate-200">服务器 IP / 域名
                <input required maxLength={253} disabled={busy} value={form.host} onChange={event => setForm(current => ({ ...current, host: event.target.value }))} placeholder="请输入服务器 IP 或域名" autoComplete="off" className="input-ios mt-1.5 w-full" />
              </label>
              <div className="grid grid-cols-2 gap-3">
                <label className="block text-sm font-medium text-slate-700 dark:text-slate-200">SSH 端口
                  <input required type="number" min={1} max={65535} disabled={busy} value={form.port || ''} onChange={event => setForm(current => ({ ...current, port: Number(event.target.value) }))} className="input-ios mt-1.5 w-full" />
                </label>
                <label className="block text-sm font-medium text-slate-700 dark:text-slate-200">SSH 用户名
                  <input required maxLength={128} disabled={busy} value={form.username} onChange={event => setForm(current => ({ ...current, username: event.target.value }))} autoComplete="off" className="input-ios mt-1.5 w-full" />
                </label>
              </div>
              <label className="block text-sm font-medium text-slate-700 dark:text-slate-200">认证方式
                <select disabled={busy} value={form.auth_method} onChange={event => setForm(current => ({ ...current, auth_method: event.target.value as InstallForm['auth_method'] }))} className="input-ios mt-1.5 w-full">
                  <option value="password">密码认证</option>
                  <option value="private_key">私钥认证</option>
                </select>
              </label>
              {form.auth_method === 'password' ? (
                <label className="block text-sm font-medium text-slate-700 dark:text-slate-200">SSH 密码
                  <PasswordInput required disabled={busy} value={form.password} onChange={password => setForm(current => ({ ...current, password }))} placeholder="请输入 SSH 密码" className="mt-1.5" inputClassName="w-full" />
                </label>
              ) : (
                <>
                  <label className="block text-sm font-medium text-slate-700 dark:text-slate-200">SSH 私钥
                    <textarea required maxLength={65536} rows={6} disabled={busy} value={form.private_key} onChange={event => setForm(current => ({ ...current, private_key: event.target.value }))} placeholder="请粘贴完整私钥，包含 BEGIN / END 行" autoComplete="off" autoCapitalize="off" spellCheck={false} className="input-ios mt-1.5 w-full resize-y text-xs leading-5" />
                    <span className="mt-1.5 block text-xs font-normal text-slate-500 dark:text-slate-400">支持 OpenSSH / PEM 格式的 RSA、Ed25519、ECDSA 私钥；请勿填写 .pub 公钥。</span>
                  </label>
                  <label className="block text-sm font-medium text-slate-700 dark:text-slate-200">私钥口令（选填）
                    <PasswordInput disabled={busy} value={form.private_key_passphrase} onChange={private_key_passphrase => setForm(current => ({ ...current, private_key_passphrase }))} placeholder="私钥已加密时填写，未加密请留空" showLabel="显示私钥口令" hideLabel="隐藏私钥口令" className="mt-1.5" inputClassName="w-full" />
                  </label>
                </>
              )}
              <div className="rounded-md bg-slate-50 p-3 text-xs text-slate-600 dark:bg-slate-900/50 dark:text-slate-300">
                <p className="mb-2 font-medium">将在 SSH 登录后的默认目录执行：</p>
                <code className="break-all leading-5">{INSTALL_COMMAND}</code>
              </div>
              {install.serverInfo && <p className="break-all text-sm text-emerald-600 dark:text-emerald-400">{install.serverInfo}</p>}
              <div className="flex flex-wrap gap-3">
                <button type="button" disabled={busy} onClick={() => { if (formRef.current?.reportValidity()) install.testConnection(connectedForm) }} className="btn-ios-secondary flex-1"><Wifi className="h-4 w-4" />测试连接</button>
                <button type="submit" disabled={busy} className="btn-ios-primary flex-1"><Play className="h-4 w-4" />{install.running ? '安装中…' : '开始安装'}</button>
              </div>
              {(install.restoring || install.testing || install.submitting) && <div role="status" className="absolute inset-0 flex flex-col items-center justify-center gap-2 rounded-lg bg-white/80 backdrop-blur-sm dark:bg-slate-800/85"><Loader2 className="h-7 w-7 animate-spin text-[rgb(var(--color-primary))]" /><p className="text-sm text-slate-700 dark:text-slate-200">{install.restoring ? '正在恢复安装记录…' : install.testing ? '正在测试 SSH 连接…' : '正在提交安装任务…'}</p></div>}
            </form>
          </section>
          <section className="min-w-0 overflow-hidden rounded-lg border border-slate-200 bg-white shadow-sm dark:border-slate-700 dark:bg-slate-800">
            <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-200 px-4 py-3 dark:border-slate-700">
              <h2 className="flex items-center gap-2 font-semibold text-slate-800 dark:text-slate-100"><Terminal className="h-4 w-4 text-[rgb(var(--color-primary))]" />安装日志</h2>
              {(install.running || install.polling) && <span role="status" className="flex items-center gap-1.5 text-xs text-[rgb(var(--color-primary))]"><Loader2 className="h-3.5 w-3.5 animate-spin" />{install.polling ? '正在安装' : '日志读取已暂停'}</span>}
            </div>
            <div className="space-y-3 p-4">
              <div className="flex items-center justify-between gap-2 text-xs text-slate-500 dark:text-slate-400">
                <span className="min-w-0">{install.result ? `开始时间：${install.result.created_at}（北京时间）` : '执行输出将在这里显示'}</span>
                <label className="flex shrink-0 items-center gap-1.5"><input type="checkbox" checked={autoScroll} onChange={event => setAutoScroll(event.target.checked)} className="accent-[rgb(var(--color-primary))]" />自动滚动</label>
              </div>
              {install.taskId && <p className="flex items-center gap-1.5 text-sm text-slate-700 dark:text-slate-200"><Clock className="h-4 w-4 shrink-0 text-[rgb(var(--color-primary))]" /><span>安装耗时：</span><span className="tabular-nums">{install.elapsedText ?? '正在获取…'}</span></p>}
              <pre ref={logRef} aria-label="安装实时日志" tabIndex={0} className="h-[360px] overflow-auto rounded-md border border-slate-200 bg-slate-50 p-3 text-xs leading-6 text-slate-800 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100 sm:h-[440px] whitespace-pre-wrap break-all">{install.logs || '暂无安装输出，请填写 SSH 配置后开始安装。'}</pre>
              {install.result?.finished && <p className={cn('flex items-start gap-2 rounded-md p-3 text-sm', install.result.success ? 'bg-emerald-50 text-emerald-700 dark:bg-emerald-900/20 dark:text-emerald-300' : 'bg-red-50 text-red-700 dark:bg-red-900/20 dark:text-red-300')}>{install.result.success ? <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0" /> : <XCircle className="mt-0.5 h-4 w-4 shrink-0" />}{install.result.message}</p>}
              {install.error && <p role="alert" className="break-words rounded-md bg-red-50 p-3 text-sm text-red-700 dark:bg-red-900/20 dark:text-red-300">{install.error}</p>}
              <div className="flex flex-wrap gap-2">
                {install.taskId && !install.polling && !install.result?.finished && <button type="button" disabled={install.submitting || install.testing} onClick={install.resumeLogs} className="btn-ios-secondary btn-sm">重新读取日志</button>}
                {install.taskId && !install.submitting && !install.testing && <button type="button" disabled={!install.canReset} onClick={install.resetTask} className="btn-ios-secondary btn-sm">开始新的安装</button>}
              </div>
              {install.taskId && <p className="text-xs text-slate-500 dark:text-slate-400">刷新页面可恢复当前安装日志和耗时。安装任务结束前不能重置或开始新的安装，离开页面不会中断服务器上的安装。</p>}
            </div>
          </section>
        </div>
        <PublicPageFooter />
      </main>
      <ConfirmModal isOpen={confirming} title="确认在线安装" message={<span>将在服务器 <strong className="break-all">{connectedForm.host}:{connectedForm.port}</strong> 的 SSH 登录默认目录执行部署脚本，并启动闲鱼自动回复服务。</span>} confirmText="确定安装" cancelText="关闭" onCancel={() => setConfirming(false)} onConfirm={() => { setConfirming(false); install.startInstall(connectedForm) }} />
    </div>
  )
}
