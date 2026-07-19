import { defineConfig } from 'vite'
import type { Plugin } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

/**
 * 拦截非法 URI 编码和危险文件路径请求的插件
 * 背景：当浏览器或外部探测请求发来包含非法百分号编码（如单独的 % 或不合法的 %xx）的 URL 时，
 *      Vite 内部中间件在调用 decodeURI(req.url) 时会抛出 "URI malformed"，
 *      并触发 HMR 错误遮罩导致开发页面报错崩溃。
 *      某些 Linux 探测请求（如 /etc/passwd）在 Windows 下会被解析成 C:\\etc\\passwd，
 *      进入 Vite 文件加载器后触发 ENOENT 并显示错误遮罩。
 * 方案：在所有中间件最前面校验 req.url，对非法编码和文件系统探测路径直接返回 400。
 */
function rejectUnsafeDevServerPaths(): Plugin {
  const sensitiveRoots = new Set(['/etc', '/proc', '/sys', '/dev', '/var', '/root'])

  return {
    name: 'reject-unsafe-dev-server-paths',
    configureServer(server) {
      server.middlewares.use((req, res, next) => {
        try {
          if (!req.url) {
            next()
            return
          }

          // 提前尝试解码，能解码说明 URL 合法；再解码组件以识别编码后的路径分隔符。
          const decodedUrl = decodeURI(req.url)
          const pathname = new URL(decodedUrl, 'http://vite.local').pathname
          const decodedPathname = decodeURIComponent(pathname).replace(/[\\]+/g, '/')
          const segments = decodedPathname.split('/').filter(Boolean)
          const rootPath = segments.length > 0 ? `/${segments[0].toLowerCase()}` : ''
          const isWindowsAbsolutePath = /^\/[a-z]:\//i.test(decodedPathname)
          const isUncPath = decodedPathname.startsWith('//')
          const hasTraversal = segments.some((segment) => segment === '..')

          if (
            sensitiveRoots.has(rootPath) ||
            isWindowsAbsolutePath ||
            isUncPath ||
            hasTraversal
          ) {
            res.statusCode = 400
            res.end('Bad Request: unsafe file path')
            return
          }

          next()
        } catch {
          // 非法 URI 编码或 URL 格式错误，直接返回 400，不再继续后续中间件。
          res.statusCode = 400
          res.end('Bad Request: malformed URI')
        }
      })
    },
  }
}

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [rejectUnsafeDevServerPaths(), react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    port: 9000,
    host: '0.0.0.0', // 允许外部访问
    allowedHosts: [
      'localhost',
      '127.0.0.1',
      'xy.zhinianboke.com',
      'xy-back.zhinianboke.com'
    ],
    proxy: {
      // 所有 API 请求统一代理到后端（含WebSocket升级）
      '/api': {
        target: 'http://localhost:8089',
        changeOrigin: true,
        ws: true,
      },
      // 静态文件代理到后端（包含上传的图片）
      '/static': {
        target: 'http://localhost:8089',
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: 'dist',
    assetsDir: 'assets',
  },
})
