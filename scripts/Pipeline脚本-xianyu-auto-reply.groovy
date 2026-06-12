pipeline {
    agent any
    
    environment {
        // GitHub 仓库配置（通过国内 GitHub 加速镜像拉取，公开仓库无需凭据）
        GITHUB_REPO = 'https://github.com/zhinianboke/xianyu-auto-reply.git'
        // 注：已改为多加速镜像拉取（ghfast.top 等），不再使用 github-token 凭据；
        //     若仓库为私有需走凭据，请改回 git 步骤并配置 GITHUB_CREDENTIALS
        GITHUB_CREDENTIALS = 'github-token'
        
        // 阿里云镜像仓库配置
        ALIYUN_REGISTRY = 'registry.cn-shanghai.aliyuncs.com'
        ALIYUN_NAMESPACE = 'zhinian-software'
        ALIYUN_CREDENTIALS = 'aliyun-docker-credentials'  // 需要在 Jenkins 中配置
        
        // 镜像名称 - 4个服务
        FRONTEND_IMAGE_NAME = 'xianyu-frontend'
        WEBSOCKET_IMAGE_NAME = 'xianyu-websocket'
        BACKEND_WEB_IMAGE_NAME = 'xianyu-backend-web'
        SCHEDULER_IMAGE_NAME = 'xianyu-scheduler'

        // 基础设施镜像 - 从国内加速源同步多架构镜像到阿里云（amd64 + arm64）
        // 镜像名与 docker-compose.yml 保持一致（xianyu- 前缀）
        MYSQL_SOURCE_IMAGE = 'docker.1ms.run/library/mysql:8.0'
        MYSQL_TARGET_TAG = 'xianyu-mysql:8.0'
        REDIS_SOURCE_IMAGE = 'docker.1ms.run/library/redis:7-alpine'
        REDIS_TARGET_TAG = 'xianyu-redis:7-alpine'

        // 支持的平台
        PLATFORMS = 'linux/amd64,linux/arm64'
    }
    
    stages {
        stage('拉取代码') {
            steps {
                echo '开始拉取代码...'

                // 多 GitHub 加速镜像优先 + 直连兜底（参照 jenkins/安装Buildx插件.sh、修复DockerCLI.sh）
                // 加速镜像优先级：ghfast.top → gh-proxy.com → ghproxy.net → mirror.ghproxy.com → github.com 直连
                sh '''
                    git config --global http.version HTTP/1.1
                    git config --global http.postBuffer 524288000

                    rm -rf src_checkout
                    CLONED=0
                    for PREFIX in \
                        "https://ghfast.top/" \
                        "https://gh-proxy.com/" \
                        "https://ghproxy.net/" \
                        "https://mirror.ghproxy.com/" \
                        ""; do
                        URL="${PREFIX}${GITHUB_REPO}"
                        echo "尝试拉取: ${URL}"
                        if git clone --branch main --depth 1 "${URL}" src_checkout; then
                            echo "✓ 拉取成功: ${URL}"
                            CLONED=1
                            break
                        fi
                        echo "✗ 拉取失败，切换下一个加速镜像..."
                        rm -rf src_checkout
                    done
                    [ "${CLONED}" = "1" ] || { echo "所有镜像均拉取失败"; exit 1; }

                    # 将检出的代码（含隐藏文件）平铺到工作区根目录
                    cp -a src_checkout/. .
                    rm -rf src_checkout
                '''

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

        stage('同步MySQL/Redis多架构镜像到阿里云') {
            steps {
                echo "开始同步基础设施镜像（MySQL/Redis）多架构镜像到阿里云..."
                echo "目标平台: ${PLATFORMS}"
                // 官方 mysql:8.0 / redis:7-alpine 本身即多架构镜像；
                // 使用 buildx imagetools create 直接复制整个 manifest list（含 amd64 + arm64），无需 pull/rebuild
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

                                # 复制 MySQL 多架构镜像（保留 amd64 + arm64）
                                docker buildx imagetools create \\
                                    -t ${ALIYUN_REGISTRY}/${ALIYUN_NAMESPACE}/${MYSQL_TARGET_TAG} \\
                                    ${MYSQL_SOURCE_IMAGE}

                                # 复制 Redis 多架构镜像（保留 amd64 + arm64）
                                docker buildx imagetools create \\
                                    -t ${ALIYUN_REGISTRY}/${ALIYUN_NAMESPACE}/${REDIS_TARGET_TAG} \\
                                    ${REDIS_SOURCE_IMAGE}

                                # 校验目标镜像架构
                                echo "MySQL 镜像架构:"
                                docker buildx imagetools inspect ${ALIYUN_REGISTRY}/${ALIYUN_NAMESPACE}/${MYSQL_TARGET_TAG} | grep -E 'Platform|MediaType' || true
                                echo "Redis 镜像架构:"
                                docker buildx imagetools inspect ${ALIYUN_REGISTRY}/${ALIYUN_NAMESPACE}/${REDIS_TARGET_TAG} | grep -E 'Platform|MediaType' || true

                                # 登出
                                docker logout ${ALIYUN_REGISTRY}
                            """
                        }
                    }
                }
                echo '✓ MySQL/Redis 多架构镜像同步完成！'
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

            基础设施镜像（多架构，已同步到阿里云）:
              ${ALIYUN_REGISTRY}/${ALIYUN_NAMESPACE}/${MYSQL_TARGET_TAG}
              ${ALIYUN_REGISTRY}/${ALIYUN_NAMESPACE}/${REDIS_TARGET_TAG}
            
            支持的架构：
              linux/amd64  (x86_64 - Intel/AMD 处理器)
              linux/arm64  (aarch64 - ARM 64位处理器)
            
            ========================================
            部署方法：
            ========================================
            
            使用仓库根目录的 docker-compose.yml 部署（已内置阿里云镜像地址）：
            
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
