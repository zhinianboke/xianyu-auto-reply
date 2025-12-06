import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

// https://vitejs.dev/config/
export default defineConfig(({ command }) => ({
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    port: 3000,
    proxy: {
      '/api': {
        target: 'http://localhost:8080',
        changeOrigin: true,
      },
      '/login': {
        target: 'http://localhost:8080',
        changeOrigin: true,
        bypass: (req) => {
          if (req.method === 'GET') {
            return '/index.html'
          }
        },
      },
      '/verify': {
        target: 'http://localhost:8080',
        changeOrigin: true,
      },
      '/cookies': {
        target: 'http://localhost:8080',
        changeOrigin: true,
      },
      '/delivery-rules': {
        target: 'http://localhost:8080',
        changeOrigin: true,
      },
      '/system-settings': {
        target: 'http://localhost:8080',
        changeOrigin: true,
      },
      '/logs': {
        target: 'http://localhost:8080',
        changeOrigin: true,
      },
      '/users': {
        target: 'http://localhost:8080',
        changeOrigin: true,
      },
      // 管理员API - 前端有 /admin/* 路由，需要区分浏览器访问和 API 请求
      '/admin': {
        target: 'http://localhost:8080',
        changeOrigin: true,
        bypass: (req) => {
          // 浏览器直接访问（Accept 包含 text/html）时，让前端路由处理
          if (req.headers.accept?.includes('text/html')) {
            return '/index.html'
          }
        },
      },
      '/risk-control-logs': {
        target: 'http://localhost:8080',
        changeOrigin: true,
      },
      '/qrcode': {
        target: 'http://localhost:8080',
        changeOrigin: true,
      },
      '/generate-captcha': {
        target: 'http://localhost:8080',
        changeOrigin: true,
      },
      '/verify-captcha': {
        target: 'http://localhost:8080',
        changeOrigin: true,
      },
      '/send-verification-code': {
        target: 'http://localhost:8080',
        changeOrigin: true,
      },
      '/registration-status': {
        target: 'http://localhost:8080',
        changeOrigin: true,
      },
      '/login-info-status': {
        target: 'http://localhost:8080',
        changeOrigin: true,
      },
      '/register': {
        target: 'http://localhost:8080',
        changeOrigin: true,
        bypass: (req) => {
          // 浏览器直接访问时返回前端页面，只有 POST 请求才代理到后端
          if (req.method === 'GET' && req.headers.accept?.includes('text/html')) {
            return '/index.html'
          }
        },
      },
      '/itemReplays': {
        target: 'http://localhost:8080',
        changeOrigin: true,
      },
      '/item-reply': {
        target: 'http://localhost:8080',
        changeOrigin: true,
      },
      '/default-replies': {
        target: 'http://localhost:8080',
        changeOrigin: true,
      },
      '/ai-reply-settings': {
        target: 'http://localhost:8080',
        changeOrigin: true,
      },
      '/ai-reply-test': {
        target: 'http://localhost:8080',
        changeOrigin: true,
      },
      '/password-login': {
        target: 'http://localhost:8080',
        changeOrigin: true,
      },
      '/qr-login': {
        target: 'http://localhost:8080',
        changeOrigin: true,
      },
      '/keywords-export': {
        target: 'http://localhost:8080',
        changeOrigin: true,
      },
      '/keywords-import': {
        target: 'http://localhost:8080',
        changeOrigin: true,
      },
      '/default-reply': {
        target: 'http://localhost:8080',
        changeOrigin: true,
      },
      '/static': {
        target: 'http://localhost:8080',
        changeOrigin: true,
      },
      '/backup': {
        target: 'http://localhost:8080',
        changeOrigin: true,
      },
      '/project-stats': {
        target: 'http://localhost:8080',
        changeOrigin: true,
      },
      '/change-password': {
        target: 'http://localhost:8080',
        changeOrigin: true,
      },
      '/change-admin-password': {
        target: 'http://localhost:8080',
        changeOrigin: true,
      },
      '/logout': {
        target: 'http://localhost:8080',
        changeOrigin: true,
      },
      '/user-settings': {
        target: 'http://localhost:8080',
        changeOrigin: true,
      },
      '/search': {
        target: 'http://localhost:8080',
        changeOrigin: true,
      },
      // 商品管理 - 前端有 /items 路由，需要区分浏览器访问和 API 请求
      '/items': {
        target: 'http://localhost:8080',
        changeOrigin: true,
        bypass: (req) => {
          // 只有浏览器直接访问 /items 路径时才返回前端页面
          // API 请求通常是 /items/xxx 或带有 application/json
          const isApiRequest = req.url !== '/items' ||
            req.headers.accept?.includes('application/json') ||
            req.headers['content-type']?.includes('application/json')
          if (!isApiRequest && req.headers.accept?.includes('text/html')) {
            return '/index.html'
          }
        },
      },
      // 卡券管理 - 前端有 /cards 路由
      '/cards': {
        target: 'http://localhost:8080',
        changeOrigin: true,
        bypass: (req) => {
          if (req.headers.accept?.includes('text/html')) {
            return '/index.html'
          }
        },
      },
      // 通知渠道 - 前端有 /notification-channels 路由
      '/notification-channels': {
        target: 'http://localhost:8080',
        changeOrigin: true,
        bypass: (req) => {
          if (req.headers.accept?.includes('text/html')) {
            return '/index.html'
          }
        },
      },
      // 消息通知 - 前端有 /message-notifications 路由
      '/message-notifications': {
        target: 'http://localhost:8080',
        changeOrigin: true,
        bypass: (req) => {
          if (req.headers.accept?.includes('text/html')) {
            return '/index.html'
          }
        },
      },
      // 关键词 - 前端有 /keywords 路由
      '/keywords': {
        target: 'http://localhost:8080',
        changeOrigin: true,
        bypass: (req) => {
          if (req.headers.accept?.includes('text/html')) {
            return '/index.html'
          }
        },
      },
      // 订单 API - 后端路径是 /api/orders
      '/api/orders': {
        target: 'http://localhost:8080',
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: 'dist',
    // 资源放在 assets 目录，通过 base 配置让引用路径为 /static/assets/
    assetsDir: 'assets',
  },
  // 只在生产构建时使用 /static/ 作为 base，开发模式使用 /
  base: command === 'build' ? '/static/' : '/',
}))
