import { defineConfig } from 'vite'
import type { Plugin } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

/**
 * 拦截非法 URI 编码的请求插件
 * 背景：当浏览器或外部探测请求发来包含非法百分号编码（如单独的 % 或不合法的 %xx）的 URL 时，
 *      Vite 内部中间件在调用 decodeURI(req.url) 时会抛出 "URI malformed"，
 *      并触发 HMR 错误遮罩导致开发页面报错崩溃。
 * 方案：在所有中间件最前面校验 req.url，对非法编码直接返回 400，避免错误向上冒泡。
 */
function rejectMalformedURI(): Plugin {
  return {
    name: 'reject-malformed-uri',
    configureServer(server) {
      server.middlewares.use((req, res, next) => {
        try {
          // 提前尝试解码，能解码说明 URL 合法
          if (req.url) {
            decodeURI(req.url)
          }
          next()
        } catch {
          // 非法 URI 编码，直接返回 400，不再继续后续中间件
          res.statusCode = 400
          res.end('Bad Request: malformed URI')
        }
      })
    },
  }
}

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [rejectMalformedURI(), react()],
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
    assetsDir: 'static',
  },
})
