/** 前端独立存活检查和公开状态代理，统一传递真实客户端 IP。 */
import type { Plugin, ProxyOptions } from 'vite'
import type { IncomingMessage, ServerResponse } from 'http'

export const frontendHealthBody = JSON.stringify({
  success: true, code: 200, message: '前端服务已启动', data: { status: 'running' },
})

/** 直接响应前端存活检查，其他请求交给 Vite。 */
function frontendHealth(req: IncomingMessage, res: ServerResponse, next: () => void) {
  const separator = req.url?.indexOf('?') ?? -1
  const pathname = separator < 0 ? req.url : req.url?.slice(0, separator)
  if (pathname?.includes('%')) {
    try {
      const decoded = decodeURIComponent(pathname)
      if (decoded === '/api/v1/public/status' || decoded === '/api/v1/public/status/') {
        // 先规范化公开接口路径，确保编码路径也进入覆盖真实 IP 的专用代理。
        req.url = decoded + (separator < 0 ? '' : req.url!.slice(separator))
      }
    } catch {
      return next()
    }
  }
  if (pathname !== '/frontend-health') return next()
  res.statusCode = 200
  res.setHeader('Content-Type', 'application/json; charset=utf-8')
  res.setHeader('Cache-Control', 'no-store')
  res.end(frontendHealthBody)
}

/** 为开发及预览环境挂载独立前端存活检查和公开接口路径规范化。 */
export function frontendHealthPlugin(): Plugin {
  return {
    name: 'frontend-health',
    configureServer(server) { server.middlewares.use(frontendHealth) },
    configurePreviewServer(server) { server.middlewares.use(frontendHealth) },
  }
}

/** 在尚未发送响应时返回统一的代理故障，避免重复写入响应。 */
function sendStatusUnavailable(response: ServerResponse) {
  if (response.headersSent || response.writableEnded || response.destroyed) return
  response.statusCode = 200
  response.setHeader('Content-Type', 'application/json; charset=utf-8')
  response.setHeader('Cache-Control', 'no-store')
  response.end(JSON.stringify({
    success: false, code: 50303, message: '状态查询服务暂不可用，请稍后重试', data: null,
  }))
}

/** 公开状态使用前端反向代理，覆盖用户传入的转发 IP，并返回中文业务错误。 */
export function publicStatusProxy(target: string): ProxyOptions {
  return {
    target, changeOrigin: true, proxyTimeout: 15000, timeout: 15000,
    selfHandleResponse: true,
    configure(proxy) {
      proxy.on('proxyReq', (proxyReq, req) => {
        const clientIp = req.socket.remoteAddress || ''
        proxyReq.setHeader('X-Forwarded-For', clientIp)
        proxyReq.setHeader('X-Real-IP', clientIp)
      })
      proxy.on('error', (_error, _req, response) => {
        if (response && 'setHeader' in response) sendStatusUnavailable(response)
      })
      proxy.on('proxyRes', (upstream, _req, response) => {
        const chunks: Buffer[] = []
        const fail = () => {
          sendStatusUnavailable(response)
          upstream.destroy()
        }
        upstream.on('error', fail)
        upstream.on('aborted', fail)
        upstream.setTimeout(15000, fail)
        upstream.on('data', (chunk: Buffer) => chunks.push(chunk))
        upstream.on('end', () => {
          if (response.headersSent || response.writableEnded || response.destroyed) return
          if (!upstream.complete || (upstream.statusCode || 502) >= 500) {
            sendStatusUnavailable(response)
            return
          }
          // 完整读取后再发送，避免中途断开时返回半截 JSON 或重复响应。
          const body = Buffer.concat(chunks)
          response.statusCode = upstream.statusCode || 200
          const excluded = new Set(['connection', 'transfer-encoding', 'keep-alive', 'trailer', 'upgrade'])
          for (const [header, value] of Object.entries(upstream.headers)) {
            if (value !== undefined && !excluded.has(header)) response.setHeader(header, value)
          }
          response.setHeader('Content-Length', body.length)
          response.end(body)
        })
      })
    },
  }
}
