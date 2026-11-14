import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'
import { rejectUnsafeDevServerPaths } from './config/dev_request_guard'
import { frontendHealthPlugin, publicStatusProxy } from './config/public_status'

// https://vitejs.dev/config/
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const backendTarget = env.VITE_BACKEND_SERVICE_URL || env.BACKEND_WEB_SERVICE_URL || 'http://127.0.0.1:8089'
  return {
    plugins: [rejectUnsafeDevServerPaths(), frontendHealthPlugin(), react()],
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
        '/api/v1/public/': publicStatusProxy(backendTarget),
        // 所有 API 请求统一代理到后端（含WebSocket升级）
        '/api': {
          target: backendTarget,
          changeOrigin: true,
          ws: true,
        },
        // 静态文件代理到后端（包含上传的图片）
        '/static': {
          target: backendTarget,
          changeOrigin: true,
        },
      },
    },
    preview: {
      port: 9000,
      proxy: { '/api/v1/public/': publicStatusProxy(backendTarget) },
    },
    build: {
      outDir: 'dist',
      assetsDir: 'assets',
    },
  }
})
