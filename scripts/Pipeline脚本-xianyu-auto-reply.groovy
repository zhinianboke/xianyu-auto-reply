pipeline {
    agent any
    
    environment {
        // GitHub 私有仓库配置
        GITHUB_REPO = 'https://github.com/zhinianboke/xianyu-auto-reply.git'
        GITHUB_CREDENTIALS = 'github-token'  // 需要在 Jenkins 中配置
        
        // 阿里云镜像仓库配置
        ALIYUN_REGISTRY = 'registry.cn-shanghai.aliyuncs.com'
        ALIYUN_NAMESPACE = 'zhinian-software'
        ALIYUN_CREDENTIALS = 'aliyun-docker-credentials'  // 需要在 Jenkins 中配置
        
        // 镜像名称 - 4个服务
        FRONTEND_IMAGE_NAME = 'xianyu-frontend'
        WEBSOCKET_IMAGE_NAME = 'xianyu-websocket'
        BACKEND_WEB_IMAGE_NAME = 'xianyu-backend-web'
        SCHEDULER_IMAGE_NAME = 'xianyu-scheduler'
        
        // 支持的平台
        PLATFORMS = 'linux/amd64,linux/arm64'
    }
    
    stages {
        stage('拉取代码') {
            steps {
                echo '开始拉取代码...'
                
                // 配置 Git 使用 HTTP/1.1 避免 HTTP2 问题
                sh 'git config --global http.version HTTP/1.1'
                sh 'git config --global http.postBuffer 524288000'
                
                // 从私有仓库拉取代码（需要凭据）
                git branch: 'main',
                    credentialsId: "${GITHUB_CREDENTIALS}",
                    url: "${GITHUB_REPO}"
                
                echo "代码拉取完成"
            }
        }
        
        stage('验证 Buildx 环境') {
            steps {
                echo '检查 Docker Buildx 环境...'
                script {
                    sh '''
                        # 检查 buildx 是否可用
                        docker buildx version
                        
                        # 确保使用正确的 builder
                        docker buildx use multiarch-builder || \
                        (docker buildx create --name multiarch-builder --driver docker-container --use && \
                         docker buildx inspect --bootstrap)
                        
                        # 显示支持的平台
                        echo "支持的平台:"
                        docker buildx inspect --bootstrap | grep Platforms
                    '''
                }
                echo '✓ Buildx 环境验证通过！'
            }
        }
        
        stage('构建并推送前端镜像') {
            steps {
                echo "开始构建前端多架构镜像..."
                echo "目标平台: ${PLATFORMS}"
                retry(5) {
                    script {
                        withCredentials([usernamePassword(
                            credentialsId: "${ALIYUN_CREDENTIALS}",
                            usernameVariable: 'REGISTRY_USER',
                            passwordVariable: 'REGISTRY_PASS'
                        )]) {
                            sh """
                                # 登录阿里云镜像仓库
                                echo "\${REGISTRY_PASS}" | docker login ${ALIYUN_REGISTRY} -u "\${REGISTRY_USER}" --password-stdin
                                
                                # 构建并推送前端镜像（Dockerfile在docker/frontend/，构建上下文为项目根目录）
                                docker buildx build \\
                                    --platform ${PLATFORMS} \\
                                    -t ${ALIYUN_REGISTRY}/${ALIYUN_NAMESPACE}/${FRONTEND_IMAGE_NAME}:latest \\
                                    -t ${ALIYUN_REGISTRY}/${ALIYUN_NAMESPACE}/${FRONTEND_IMAGE_NAME}:build-${BUILD_NUMBER} \\
                                    -f docker/frontend/Dockerfile \\
                                    --push \\
                                    .
                                
                                # 登出
                                docker logout ${ALIYUN_REGISTRY}
                            """
                        }
                    }
                }
                echo '✓ 前端镜像推送完成！'
            }
        }
        
        stage('构建并推送WebSocket镜像') {
            steps {
                echo "开始构建 WebSocket 多架构镜像..."
                retry(5) {
                    script {
                        withCredentials([usernamePassword(
                            credentialsId: "${ALIYUN_CREDENTIALS}",
                            usernameVariable: 'REGISTRY_USER',
                            passwordVariable: 'REGISTRY_PASS'
                        )]) {
                            sh """
                                # 登录阿里云镜像仓库
                                echo "\${REGISTRY_PASS}" | docker login ${ALIYUN_REGISTRY} -u "\${REGISTRY_USER}" --password-stdin
                                
                                # 构建并推送WebSocket镜像（含Playwright）
                                docker buildx build \\
                                    --platform ${PLATFORMS} \\
                                    -t ${ALIYUN_REGISTRY}/${ALIYUN_NAMESPACE}/${WEBSOCKET_IMAGE_NAME}:latest \\
                                    -t ${ALIYUN_REGISTRY}/${ALIYUN_NAMESPACE}/${WEBSOCKET_IMAGE_NAME}:build-${BUILD_NUMBER} \\
                                    -f websocket/Dockerfile \\
                                    --push \\
                                    .
                                
                                # 登出
                                docker logout ${ALIYUN_REGISTRY}
                            """
                        }
                    }
                }
                echo '✓ WebSocket 镜像推送完成！'
            }
        }
        
        stage('构建并推送Backend-Web镜像') {
            steps {
                echo "开始构建 Backend-Web 多架构镜像..."
                retry(5) {
                    script {
                        withCredentials([usernamePassword(
                            credentialsId: "${ALIYUN_CREDENTIALS}",
                            usernameVariable: 'REGISTRY_USER',
                            passwordVariable: 'REGISTRY_PASS'
                        )]) {
                            sh """
                                # 登录阿里云镜像仓库
                                echo "\${REGISTRY_PASS}" | docker login ${ALIYUN_REGISTRY} -u "\${REGISTRY_USER}" --password-stdin
                                
                                # 构建并推送Backend-Web镜像
                                docker buildx build \\
                                    --platform ${PLATFORMS} \\
                                    -t ${ALIYUN_REGISTRY}/${ALIYUN_NAMESPACE}/${BACKEND_WEB_IMAGE_NAME}:latest \\
                                    -t ${ALIYUN_REGISTRY}/${ALIYUN_NAMESPACE}/${BACKEND_WEB_IMAGE_NAME}:build-${BUILD_NUMBER} \\
                                    -f backend-web/Dockerfile \\
                                    --push \\
                                    .
                                
                                # 登出
                                docker logout ${ALIYUN_REGISTRY}
                            """
                        }
                    }
                }
                echo '✓ Backend-Web 镜像推送完成！'
            }
        }
        
        stage('构建并推送Scheduler镜像') {
            steps {
                echo "开始构建 Scheduler 多架构镜像（含Playwright）..."
                retry(5) {
                    script {
                        withCredentials([usernamePassword(
                            credentialsId: "${ALIYUN_CREDENTIALS}",
                            usernameVariable: 'REGISTRY_USER',
                            passwordVariable: 'REGISTRY_PASS'
                        )]) {
                            sh """
                                # 登录阿里云镜像仓库
                                echo "\${REGISTRY_PASS}" | docker login ${ALIYUN_REGISTRY} -u "\${REGISTRY_USER}" --password-stdin
                                
                                # 构建并推送Scheduler镜像（含Playwright）
                                docker buildx build \\
                                    --platform ${PLATFORMS} \\
                                    -t ${ALIYUN_REGISTRY}/${ALIYUN_NAMESPACE}/${SCHEDULER_IMAGE_NAME}:latest \\
                                    -t ${ALIYUN_REGISTRY}/${ALIYUN_NAMESPACE}/${SCHEDULER_IMAGE_NAME}:build-${BUILD_NUMBER} \\
                                    -f scheduler/Dockerfile \\
                                    --push \\
                                    .
                                
                                # 登出
                                docker logout ${ALIYUN_REGISTRY}
                            """
                        }
                    }
                }
                echo '✓ Scheduler 镜像推送完成！'
            }
        }
        
        stage('生成部署文件') {
            steps {
                echo '生成生产环境部署文件...'
                script {
                    sh """
                        # 创建部署文件目录
                        mkdir -p deploy-artifacts
                        
                        # 生成分发版 docker-compose.yml（使用阿里云镜像地址）
                        cat > deploy-artifacts/docker-compose.yml << 'COMPOSE_EOF'
# Docker Compose配置 - 闲鱼自动回复系统
# 分发版 - 使用预构建的Docker镜像，开箱即用
# 包含MySQL和Redis容器

services:
  # ====== 基础设施 ======

  # MySQL数据库
  mysql:
    image: mysql:8.0
    container_name: xianyu-mysql
    restart: unless-stopped
    environment:
      - MYSQL_ROOT_PASSWORD=\${MYSQL_ROOT_PASSWORD:-xianyu@2026}
      - MYSQL_DATABASE=\${MYSQL_DATABASE:-xianyu_data}
      - MYSQL_USER=\${MYSQL_USER:-xianyu}
      - MYSQL_PASSWORD=\${MYSQL_PASSWORD:-xianyu@2026}
      - TZ=Asia/Shanghai
    command:
      - --character-set-server=utf8mb4
      - --collation-server=utf8mb4_unicode_ci
      - --max-connections=500
      - --default-time-zone=+08:00
    volumes:
      - mysql_data:/var/lib/mysql
    networks:
      - xianyu-network
    healthcheck:
      test: ["CMD", "mysqladmin", "ping", "-h", "localhost", "-u", "root", "-p\${MYSQL_ROOT_PASSWORD:-xianyu@2026}"]
      interval: 10s
      timeout: 5s
      retries: 10
      start_period: 30s

  # Redis缓存
  redis:
    image: redis:7-alpine
    container_name: xianyu-redis
    restart: unless-stopped
    command: >
      redis-server
      --requirepass \${REDIS_PASSWORD:-xianyu@2026}
      --maxmemory 256mb
      --maxmemory-policy allkeys-lru
      --appendonly yes
    environment:
      - TZ=Asia/Shanghai
    volumes:
      - redis_data:/data
    networks:
      - xianyu-network
    healthcheck:
      test: ["CMD", "redis-cli", "-a", "\${REDIS_PASSWORD:-xianyu@2026}", "ping"]
      interval: 10s
      timeout: 5s
      retries: 5
      start_period: 10s

  # ====== 应用服务 ======

  # 前端服务
  frontend:
    image: \${IMAGE_REGISTRY:-registry.cn-shanghai.aliyuncs.com/zhinian-software}/xianyu-frontend:\${IMAGE_TAG:-latest}
    container_name: xianyu-frontend
    restart: unless-stopped
    ports:
      - "\${FRONTEND_PORT:-9000}:80"
    networks:
      - xianyu-network
    depends_on:
      backend-web:
        condition: service_healthy
    environment:
      - TZ=Asia/Shanghai

  # WebSocket服务
  websocket:
    image: \${IMAGE_REGISTRY:-registry.cn-shanghai.aliyuncs.com/zhinian-software}/xianyu-websocket:\${IMAGE_TAG:-latest}
    container_name: xianyu-websocket
    restart: unless-stopped
    environment:
      - ENVIRONMENT=production
      - MYSQL_HOST=mysql
      - MYSQL_PORT=3306
      - MYSQL_USER=\${MYSQL_USER:-xianyu}
      - MYSQL_PASSWORD=\${MYSQL_PASSWORD:-xianyu@2026}
      - MYSQL_DATABASE=\${MYSQL_DATABASE:-xianyu_data}
      - REDIS_HOST=redis
      - REDIS_PORT=6379
      - REDIS_PASSWORD=\${REDIS_PASSWORD:-xianyu@2026}
      - REDIS_DB=\${REDIS_DB:-0}
      - WEBSOCKET_PORT=8090
      - MAX_CAPTCHA_CONCURRENT=\${MAX_CAPTCHA_CONCURRENT:-3}
      - BROWSER_HEADLESS=true
      - BACKEND_WEB_SERVICE_URL=http://backend-web:8089
      - STATIC_DIR=/app/static
      - LOG_LEVEL=\${LOG_LEVEL:-INFO}
      - TZ=Asia/Shanghai
    volumes:
      - websocket_logs:/app/websocket/logs
      - static-files:/app/static
    ports:
      - "\${WEBSOCKET_PORT:-8090}:8090"
    networks:
      - xianyu-network
    depends_on:
      mysql:
        condition: service_healthy
      redis:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8090/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 60s

  # Backend-Web服务
  backend-web:
    image: \${IMAGE_REGISTRY:-registry.cn-shanghai.aliyuncs.com/zhinian-software}/xianyu-backend-web:\${IMAGE_TAG:-latest}
    container_name: xianyu-backend-web
    restart: unless-stopped
    environment:
      - ENVIRONMENT=production
      - MYSQL_HOST=mysql
      - MYSQL_PORT=3306
      - MYSQL_USER=\${MYSQL_USER:-xianyu}
      - MYSQL_PASSWORD=\${MYSQL_PASSWORD:-xianyu@2026}
      - MYSQL_DATABASE=\${MYSQL_DATABASE:-xianyu_data}
      - REDIS_HOST=redis
      - REDIS_PORT=6379
      - REDIS_PASSWORD=\${REDIS_PASSWORD:-xianyu@2026}
      - REDIS_DB=\${REDIS_DB:-0}
      - BACKEND_WEB_PORT=8089
      - JWT_ALGORITHM=HS256
      - ACCESS_TOKEN_EXPIRE_MINUTES=\${ACCESS_TOKEN_EXPIRE_MINUTES:-1440}
      - REFRESH_TOKEN_EXPIRE_MINUTES=\${REFRESH_TOKEN_EXPIRE_MINUTES:-10080}
      - CORS_ORIGINS=*
      - WEBSOCKET_SERVICE_URL=http://websocket:8090
      - SCHEDULER_SERVICE_URL=http://scheduler:8091
      - STATIC_DIR=/app/static
      - BACKUP_DIR=/app/backups
      - BACKEND_WEB_PUBLIC_URL=\${BACKEND_WEB_PUBLIC_URL:-}
      - BROWSER_HEADLESS=true
      - LOG_LEVEL=\${LOG_LEVEL:-INFO}
      - TZ=Asia/Shanghai
    volumes:
      - backend_web_logs:/app/backend-web/logs
      - static-files:/app/static
      - backup-files:/app/backups
    ports:
      - "\${BACKEND_WEB_PORT:-8089}:8089"
    networks:
      - xianyu-network
    depends_on:
      mysql:
        condition: service_healthy
      redis:
        condition: service_healthy
      websocket:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8089/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 60s

  # Scheduler服务
  scheduler:
    image: \${IMAGE_REGISTRY:-registry.cn-shanghai.aliyuncs.com/zhinian-software}/xianyu-scheduler:\${IMAGE_TAG:-latest}
    container_name: xianyu-scheduler
    restart: unless-stopped
    environment:
      - ENVIRONMENT=production
      - MYSQL_HOST=mysql
      - MYSQL_PORT=3306
      - MYSQL_USER=\${MYSQL_USER:-xianyu}
      - MYSQL_PASSWORD=\${MYSQL_PASSWORD:-xianyu@2026}
      - MYSQL_DATABASE=\${MYSQL_DATABASE:-xianyu_data}
      - REDIS_HOST=redis
      - REDIS_PORT=6379
      - REDIS_PASSWORD=\${REDIS_PASSWORD:-xianyu@2026}
      - REDIS_DB=\${REDIS_DB:-0}
      - SCHEDULER_PORT=8091
      - REDELIVERY_INTERVAL=\${REDELIVERY_INTERVAL:-5}
      - RATE_INTERVAL=\${RATE_INTERVAL:-20}
      - WEBSOCKET_SERVICE_URL=http://websocket:8090
      - BACKEND_WEB_SERVICE_URL=http://backend-web:8089
      - STATIC_DIR=/app/static
      - BACKUP_DIR=/app/backups
      - LOG_LEVEL=\${LOG_LEVEL:-INFO}
      - TZ=Asia/Shanghai
    volumes:
      - scheduler_logs:/app/scheduler/logs
      - static-files:/app/static:ro
      - backup-files:/app/backups
    ports:
      - "\${SCHEDULER_PORT:-8091}:8091"
    networks:
      - xianyu-network
    depends_on:
      mysql:
        condition: service_healthy
      redis:
        condition: service_healthy
      websocket:
        condition: service_healthy
      backend-web:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8091/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 60s

networks:
  xianyu-network:
    driver: bridge

volumes:
  mysql_data:
    driver: local
  redis_data:
    driver: local
  websocket_logs:
    driver: local
  backend_web_logs:
    driver: local
  scheduler_logs:
    driver: local
  static-files:
    driver: local
  backup-files:
    driver: local
COMPOSE_EOF
                        
                        # 生成环境变量模板
                        cat > deploy-artifacts/.env.template << 'ENV_EOF'
# ==========================================
# 闲鱼自动回复系统 - 环境变量配置
# ==========================================

# MySQL数据库配置（Docker内置，自动创建）
MYSQL_ROOT_PASSWORD=xianyu@2026
MYSQL_DATABASE=xianyu_data
MYSQL_USER=xianyu
MYSQL_PASSWORD=xianyu@2026

# Redis缓存配置（Docker内置）
REDIS_PASSWORD=xianyu@2026
REDIS_DB=0

# 说明：JWT 密钥由数据库统一托管（首次启动自动生成并持久化），无需在此配置

# 端口配置
FRONTEND_PORT=9000
BACKEND_WEB_PORT=8089
WEBSOCKET_PORT=8090
SCHEDULER_PORT=8091

# 镜像配置
IMAGE_REGISTRY=registry.cn-shanghai.aliyuncs.com/zhinian-software
IMAGE_TAG=latest

# 日志级别
LOG_LEVEL=INFO

# Token过期时间（分钟）
ACCESS_TOKEN_EXPIRE_MINUTES=1440
REFRESH_TOKEN_EXPIRE_MINUTES=10080

# 定时任务间隔（分钟）
REDELIVERY_INTERVAL=5
RATE_INTERVAL=20

# 验证码并发数
MAX_CAPTCHA_CONCURRENT=3
ENV_EOF
                        
                        # 创建部署脚本
                        cat > deploy-artifacts/deploy.sh << 'DEPLOY_EOF'
#!/bin/bash
# 闲鱼自动回复系统 - 部署脚本
# 
# 使用方法:
# 1. 上传部署文件到服务器
# 2. 配置 .env 文件
# 3. 运行: bash deploy.sh

set -e

echo "=========================================="
echo "闲鱼自动回复系统 - 部署"
echo "=========================================="

# 检查环境变量文件
if [ ! -f ".env" ]; then
    if [ -f ".env.template" ]; then
        cp .env.template .env
        echo "[提示] 已从模板创建.env文件，请根据需要修改配置后重新运行"
        exit 1
    else
        echo "[错误] 未找到 .env 文件"
        exit 1
    fi
fi

# 检查 Docker 和 Docker Compose
if ! command -v docker &> /dev/null; then
    echo "[错误] 未安装 Docker"
    exit 1
fi

if docker compose version &> /dev/null; then
    DOCKER_COMPOSE="docker compose"
elif command -v docker-compose &> /dev/null; then
    DOCKER_COMPOSE="docker-compose"
else
    echo "[错误] 未安装 Docker Compose"
    exit 1
fi

# 拉取最新镜像
echo "[信息] 拉取最新镜像..."
\$DOCKER_COMPOSE pull

# 停止旧服务（如果存在）
echo "[信息] 停止旧服务..."
\$DOCKER_COMPOSE down 2>/dev/null || true

# 启动服务
echo "[信息] 启动服务..."
\$DOCKER_COMPOSE up -d

# 检查服务状态
echo "[信息] 等待服务启动..."
sleep 15
\$DOCKER_COMPOSE ps

echo ""
echo "=========================================="
echo "部署完成！"
echo "=========================================="
echo "前端访问地址: http://localhost:9000"
echo "MySQL/Redis: 仅内部网络，不暴露到公网"
echo ""
echo "查看日志: \$DOCKER_COMPOSE logs -f"
echo "停止服务: \$DOCKER_COMPOSE down"
echo "重启服务: \$DOCKER_COMPOSE restart"
echo "更新服务: bash update.sh"
echo "=========================================="
DEPLOY_EOF

                        # 创建更新脚本
                        cat > deploy-artifacts/update.sh << 'UPDATE_EOF'
#!/bin/bash
# 闲鱼自动回复系统 - 更新脚本

set -e

echo "=========================================="
echo "闲鱼自动回复系统 - 更新"
echo "=========================================="

if docker compose version &> /dev/null; then
    DOCKER_COMPOSE="docker compose"
else
    DOCKER_COMPOSE="docker-compose"
fi

# 拉取最新镜像
echo "[信息] 拉取最新镜像..."
\$DOCKER_COMPOSE pull

# 重启服务（MySQL/Redis数据不受影响）
echo "[信息] 重启服务..."
\$DOCKER_COMPOSE up -d

echo "[完成] 更新完成！"
UPDATE_EOF

                        # 设置脚本执行权限
                        chmod +x deploy-artifacts/*.sh
                        
                        echo "部署文件生成完成！"
                        ls -la deploy-artifacts/
                    """
                }
                
                // 归档部署文件
                archiveArtifacts artifacts: 'deploy-artifacts/**', 
                                 fingerprint: true,
                                 allowEmptyArchive: false
                
                echo '✓ 部署文件生成完成！'
            }
        }
        
        stage('清理 Builder 缓存') {
            steps {
                echo '清理 buildx 缓存...'
                sh """
                    # 清理构建缓存（保留10GB）
                    docker buildx prune -f --keep-storage 10GB || true
                """
                echo '✓ 清理完成！'
            }
        }
    }
    
    post {
        success {
            echo """
            ========================================
            闲鱼自动回复系统 构建成功！
            ========================================
            构建编号：${BUILD_NUMBER}
            支持平台：${PLATFORMS}
            
            镜像已推送到阿里云镜像仓库：
            ────────────────────────────────────────
            前端镜像:
              ${ALIYUN_REGISTRY}/${ALIYUN_NAMESPACE}/${FRONTEND_IMAGE_NAME}:latest
              ${ALIYUN_REGISTRY}/${ALIYUN_NAMESPACE}/${FRONTEND_IMAGE_NAME}:build-${BUILD_NUMBER}
              
            WebSocket镜像:
              ${ALIYUN_REGISTRY}/${ALIYUN_NAMESPACE}/${WEBSOCKET_IMAGE_NAME}:latest
              ${ALIYUN_REGISTRY}/${ALIYUN_NAMESPACE}/${WEBSOCKET_IMAGE_NAME}:build-${BUILD_NUMBER}
            
            Backend-Web镜像:
              ${ALIYUN_REGISTRY}/${ALIYUN_NAMESPACE}/${BACKEND_WEB_IMAGE_NAME}:latest
              ${ALIYUN_REGISTRY}/${ALIYUN_NAMESPACE}/${BACKEND_WEB_IMAGE_NAME}:build-${BUILD_NUMBER}
            
            Scheduler镜像:
              ${ALIYUN_REGISTRY}/${ALIYUN_NAMESPACE}/${SCHEDULER_IMAGE_NAME}:latest
              ${ALIYUN_REGISTRY}/${ALIYUN_NAMESPACE}/${SCHEDULER_IMAGE_NAME}:build-${BUILD_NUMBER}
            
            支持的架构：
              linux/amd64  (x86_64 - Intel/AMD 处理器)
              linux/arm64  (aarch64 - ARM 64位处理器)
            
            部署文件已生成：
            ────────────────────────────────────────
              docker-compose.yml (生产环境配置，含MySQL/Redis)
              .env.template (环境变量模板)
              deploy.sh (一键部署脚本)
              update.sh (一键更新脚本)
              
              下载方式：
              1. 打开此构建页面
              2. 点击左侧 "Build Artifacts"
              3. 下载 deploy-artifacts 文件夹
              
              或使用命令行：
              wget ${BUILD_URL}artifact/deploy-artifacts.zip
            
            ========================================
            部署方法：
            ========================================
            
            【快速部署】:
              1. 下载部署文件到服务器
              2. 配置 .env 文件
              3. 运行: bash deploy.sh
            
            【手动部署】:
              1. 拉取镜像:
                 docker pull ${ALIYUN_REGISTRY}/${ALIYUN_NAMESPACE}/${FRONTEND_IMAGE_NAME}:latest
                 docker pull ${ALIYUN_REGISTRY}/${ALIYUN_NAMESPACE}/${WEBSOCKET_IMAGE_NAME}:latest
                 docker pull ${ALIYUN_REGISTRY}/${ALIYUN_NAMESPACE}/${BACKEND_WEB_IMAGE_NAME}:latest
                 docker pull ${ALIYUN_REGISTRY}/${ALIYUN_NAMESPACE}/${SCHEDULER_IMAGE_NAME}:latest
              
              2. 启动服务:
                 docker-compose up -d
            
            适用设备：
              x86_64 服务器 (Intel/AMD)
              ARM64 服务器 (AWS Graviton, 华为鲲鹏等)
              树莓派 4/5 (64位系统)
              苹果 M1/M2/M3 Mac (通过 Docker Desktop)
            
            ========================================
            服务说明：
            ========================================
              前端: http://localhost:9000
              Backend-Web API: http://localhost:8089
              WebSocket: http://localhost:8090
              Scheduler: http://localhost:8091
              MySQL: 内置容器（仅内部网络）
              Redis: 内置容器（仅内部网络）
            
            源码部署：
              所有Python后端服务直接使用源码部署
            ========================================
            """
        }
        failure {
            echo """
            ========================================
            闲鱼自动回复系统 构建失败！
            ========================================
            可能的原因：
            1. GitHub 凭据配置错误
            2. 阿里云镜像仓库凭据配置错误
            3. buildx 未正确配置
            4. 目标平台不支持
            5. Dockerfile 不兼容多架构
            6. 前端或后端构建失败
            7. 网络连接问题
            
            解决方案：
            1. 检查 GitHub 凭据: Jenkins -> 凭据管理 -> github-token
            2. 检查阿里云凭据: Jenkins -> 凭据管理 -> aliyun-registry-credentials
            3. 检查 buildx 配置: docker buildx ls
            4. 查看详细日志定位具体失败的服务
            5. 验证 Dockerfile 是否支持多架构构建
            6. 检查 Dockerfile 构建配置
            ========================================
            """
        }
        always {
            echo '闲鱼自动回复系统 构建流程结束。'
        }
    }
}
