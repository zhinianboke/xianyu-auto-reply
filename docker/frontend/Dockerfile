# 前端 Dockerfile
# 闲鱼自动回复系统 - Vue/React前端
# 前端编译后为混淆压缩的JS，天然不含可读源码

# ====== 第一阶段：构建 ======
# 基础镜像使用国内加速源（与 jenkins/优化Buildx网络.sh 一致）
FROM docker.1ms.run/library/node:18-alpine AS builder

# 配置国内镜像源
RUN npm config set registry https://registry.npmmirror.com

WORKDIR /app

# 复制依赖文件
COPY frontend/package.json frontend/package-lock.json ./

# 使用锁文件进行确定性安装
RUN npm ci --no-audit --no-fund

# 复制源代码
COPY frontend/ .

# 构建生产版本（前端API已使用相对路径/api/v1，通过nginx反向代理到后端）
RUN npm run build

# ====== 第二阶段：运行 ======
# 基础镜像使用国内加速源（与 jenkins/优化Buildx网络.sh 一致）
FROM docker.1ms.run/library/nginx:alpine

# 配置国内镜像源
RUN sed -i 's|dl-cdn.alpinelinux.org|mirrors.aliyun.com|g' /etc/apk/repositories

# 复制nginx配置
COPY docker/frontend/nginx.conf /etc/nginx/conf.d/default.conf

# 复制构建产物（已混淆压缩，不含源码）
COPY --from=builder /app/dist /usr/share/nginx/html

# 暴露端口
EXPOSE 80

# 设置时区
ENV TZ=Asia/Shanghai

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD wget --no-verbose --tries=1 --spider http://localhost:80/ || exit 1

CMD ["nginx", "-g", "daemon off;"]
