/** 校验开发服务器请求，避免非法路径、目录读取和无效 HTML 代理触发页面错误广播。 */
import { stat } from 'node:fs/promises'
import type { IncomingMessage, ServerResponse } from 'node:http'
import { normalizePath } from 'vite'
import type { Plugin, ViteDevServer } from 'vite'

/** 返回中文请求错误；开发资源请求不使用后端业务接口的响应格式。 */
function rejectRequest(response: ServerResponse, message: string) {
  response.statusCode = 400
  response.setHeader('Content-Type', 'text/plain; charset=utf-8')
  response.end(message)
}

/** 按 Vite 转换中间件的规则移除基础路径、时间戳及 import 标记，并还原虚拟模块 ID。 */
function transformRequestUrl(url: string, server: ViteDevServer): string {
  const base = decodeURI(server.config.base)
  if (base && base !== '/' && url.startsWith(base)) url = `/${url.slice(base.length)}`
  url = url.replace(/\bt=\d{13}&?\b/, '').replace(/[?&]$/, '')
    .replace(/(\?|&)import=?(?:&|$)/, '$1').replace(/[?&]$/, '')
  return url.startsWith('/@id/') ? url.slice('/@id/'.length).replace('__x00__', '\0') : url
}

/** 仅校验 HTML 代理的真实缓存；缺失模块返回请求错误，其他插件异常仍按原流程报错。 */
async function invalidHtmlProxy(url: string, server: ViteDevServer): Promise<boolean> {
  const id = transformRequestUrl(url, server)
  if (!/\?html-proxy\b/.test(id)) return false
  const proxyContexts = Object.keys(server.config.server.proxy ?? {})
  if (proxyContexts.some(context => context.startsWith('^') ? new RegExp(context).test(id) : id.startsWith(context))) return false
  if (!/\?html-proxy=?(?:&inline-css)?(?:&style-attr)?&index=\d+\.(?:js|css)$/.test(id)) {
    // direct CSS 由 Vite 在 HTML 转换期间生成和处理，不使用内联脚本代理缓存。
    return !/\?html-proxy&direct&index=\d+\.css$/.test(id)
  }
  const resolved = await server.pluginContainer.resolveId(id)
  try {
    return (await server.pluginContainer.load(resolved?.id ?? id)) == null
  } catch (error) {
    if (error instanceof Error && error.message.startsWith('No matching HTML proxy module found from ')) return true
    throw error
  }
}

/** 统一记录拒绝原因、原始请求和来源，便于定位偶发请求。 */
function logRejectedRequest(server: ViteDevServer, req: IncomingMessage, reason: string, directory?: string) {
  server.config.logger.warn(`[开发请求校验] ${reason} ${JSON.stringify({
    method: req.method, url: req.url, ...(directory ? { directory } : {}),
    peer: `${req.socket.remoteAddress ?? ''}:${req.socket.remotePort ?? ''}`,
    referer: req.headers.referer ?? '',
  })}`)
}

/** 检查 Vite 文件系统及模块 ID 请求实际读取的文件路径，保留正常文件和虚拟模块。 */
async function requestedDirectory(url: string, server: ViteDevServer): Promise<string | null> {
  const pathname = url.replace(/[?#].*$/, '')
  let file: string
  if (pathname.startsWith('/@fs/')) {
    // 与 Vite 的 fsPathFromId 一致：Windows 盘符保留，其他路径补上根目录斜杠。
    file = normalizePath(pathname.slice('/@fs/'.length))
    if (!file.startsWith('/') && !/^[a-z]:/i.test(file)) file = `/${file}`
  } else if (pathname.startsWith('/@id/')) {
    const id = url.slice('/@id/'.length).replace(/__x00__/g, '\0')
    if (id.includes('\0')) return null
    const resolved = await server.pluginContainer.resolveId(id)
    file = (resolved?.id ?? id).replace(/[?#].*$/, '')
  } else {
    return null
  }
  if (!file || file.includes('\0')) return null
  try {
    return (await stat(file)).isDirectory() ? file : null
  } catch (error) {
    const code = (error as NodeJS.ErrnoException).code
    // 不存在的文件交由 Vite 正常处理，权限、磁盘等真实错误继续向上抛出。
    if (code === 'ENOENT' || code === 'ENOTDIR') return null
    throw error
  }
}

/** 在 Vite 中间件前校验 URL；正常页面、有效 HTML 代理和后端代理请求继续处理。 */
export function rejectUnsafeDevServerPaths(): Plugin {
  const sensitiveRoots = new Set(['/etc', '/proc', '/sys', '/dev', '/var', '/root'])

  return {
    name: 'reject-unsafe-dev-server-paths',
    configureServer(server) {
      server.middlewares.use((req: IncomingMessage, res: ServerResponse, next) => {
        if (!req.url) return next()
        let decodedUrl: string
        try {
          decodedUrl = decodeURI(req.url)
          const pathname = new URL(decodedUrl, 'http://vite.local').pathname
          const decodedPathname = decodeURIComponent(pathname).replace(/[\\]+/g, '/')
          const segments = decodedPathname.split('/').filter(Boolean)
          const rootPath = segments.length > 0 ? `/${segments[0].toLowerCase()}` : ''
          const isWindowsAbsolutePath = /^\/[a-z]:\//i.test(decodedPathname)
          const isUncPath = decodedPathname.startsWith('//')
          const hasTraversal = segments.some(segment => segment === '..')
          if (sensitiveRoots.has(rootPath) || isWindowsAbsolutePath || isUncPath || hasTraversal) {
            rejectRequest(res, '请求路径不合法')
            return
          }
        } catch {
          rejectRequest(res, '请求地址编码不合法')
          return
        }

        void invalidHtmlProxy(decodedUrl, server).then(async invalid => {
          if (invalid) {
            logRejectedRequest(server, req, '拒绝无效 HTML 代理')
            rejectRequest(res, 'HTML 代理请求无效或模块不存在，请刷新对应页面后重试')
            return
          }
          const directory = await requestedDirectory(decodedUrl, server)
          if (!directory) return next()
          logRejectedRequest(server, req, '拒绝目录读取', directory)
          rejectRequest(res, '请求目标是目录，无法作为文件读取')
        }).catch(next)
      })
    },
  }
}
