// ============================================================
// 闲鱼自动回复系统 - Jenkins Pipeline（仅构建 linux/amd64）
// ------------------------------------------------------------
// 说明：本脚本只构建 amd64(x86_64) 单架构镜像，不使用 docker buildx，
//       直接使用 docker build + docker push，构建机需为 amd64 架构。
// ============================================================
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

        // 仅构建 amd64 单架构
        PLATFORM = 'linux/amd64'

        // ===== 构建资源限制（防止内存/CPU 打满导致卡死）=====
        // 关键：必须关闭 BuildKit（=0）走 legacy builder，--memory/--cpu-quota 才会生效；
        //       BuildKit 模式下这些资源参数会被忽略。
        DOCKER_BUILDKIT = '0'
        // 内存上限（建议预留 ~0.5G 给系统/守护进程；按服务器实际内存调整）
        BUILD_MEMORY = '1536m'
        // 内存+交换总上限（设为与 BUILD_MEMORY 接近可抑制 swap 抖动卡死）
        BUILD_MEMORY_SWAP = '1536m'
        // CPU 配额：周期 100000us(=100ms)，quota/period 即可用核数
        // 150000 = 1.5 核（2核机器建议；想再保守可设 100000 = 1 核）
        BUILD_CPU_PERIOD = '100000'
        BUILD_CPU_QUOTA = '150000'
        // 串行构建已天然降低峰值；如需进一步限制 RUN 内并发可在 Dockerfile 控制
    }

    stages {
        stage('拉取代码') {
            steps {
                echo '开始拉取代码...'

                // 多 GitHub 加速镜像优先 + 直连兜底
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

                    # 先清理工作区旧内容（含上次遗留的只读 .git pack 文件），避免 cp 覆盖失败
                    find . -mindepth 1 -maxdepth 1 ! -name src_checkout -exec rm -rf {} +
                    # 将检出的代码（含隐藏文件）平铺到工作区根目录
                    cp -a src_checkout/. .
                    rm -rf src_checkout
                '''

                echo "代码拉取完成"
            }
        }

        stage('验证 Docker 环境') {
            steps {
                echo '检查 Docker 环境...'
                sh '''
                    # 检查 docker 是否可用
                    docker version

                    # 显示构建机架构（应为 amd64/x86_64）
                    echo "构建机架构:"
                    docker info --format '{{.Architecture}}' || uname -m

                    echo "目标平台: ${PLATFORM}"
                '''
                echo '✓ Docker 环境验证通过！'
            }
        }

        stage('预拉取基础镜像') {
            steps {
                // 关键：legacy builder（DOCKER_BUILDKIT=0）在 docker build --platform 时会解析
                //       多平台 index，并尝试拉取官方镜像携带的 provenance/SBOM 证明清单
                //       （media type application/vnd.in-toto+json）。国内镜像加速源通常不提供
                //       这些证明 blob，导致 "could not fetch content descriptor ... not found" 报错。
                //       而普通 docker pull 只解析当前主机架构(amd64)清单，不会拉取证明清单，因此不受影响。
                //       这里先把所有基础镜像 pull 到本地并打成官方 tag，后续 FROM 直接命中本地缓存，
                //       绕开会触发证明清单解析的 index 路径。
                echo '预拉取基础镜像（绕开 legacy builder 证明清单拉取 bug）...'
                sh '''
                    set -e

                    # 镜像加速源前缀（官方镜像位于 library/ 命名空间），最后空字符串为 docker.io 直连兜底
                    MIRRORS="docker.1ms.run/library/ docker.xuanyuan.me/library/ dockerpull.com/library/ "

                    pull_base() {
                        IMG="$1"   # 形如 node:18-alpine
                        for M in ${MIRRORS}; do
                            SRC="${M}${IMG}"
                            echo "尝试拉取基础镜像: ${SRC}"
                            if docker pull "${SRC}"; then
                                # 若走加速源拉取成功，重命名为官方名，确保 Dockerfile 中 FROM 能命中本地缓存
                                if [ "${SRC}" != "${IMG}" ]; then
                                    docker tag "${SRC}" "${IMG}"
                                fi
                                echo "✓ 基础镜像就绪: ${IMG}"
                                return 0
                            fi
                            echo "✗ 拉取失败，切换下一个加速源..."
                        done
                        echo "✗ 基础镜像拉取失败: ${IMG}"
                        return 1
                    }

                    # 本项目所有 Dockerfile 用到的基础镜像
                    pull_base "node:18-alpine"
                    pull_base "nginx:alpine"
                    pull_base "python:3.11-slim"
                '''
                echo '✓ 基础镜像预拉取完成！'
            }
        }

        stage('构建并推送前端镜像') {
            steps {
                echo "开始构建前端镜像（${PLATFORM}）..."
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

                                # 构建前端镜像（Dockerfile在docker/frontend/，构建上下文为项目根目录）
                                docker build \\
                                    --platform ${PLATFORM} \\
                                    --memory ${BUILD_MEMORY} \\
                                    --memory-swap ${BUILD_MEMORY_SWAP} \\
                                    --cpu-period ${BUILD_CPU_PERIOD} \\
                                    --cpu-quota ${BUILD_CPU_QUOTA} \\
                                    -t ${ALIYUN_REGISTRY}/${ALIYUN_NAMESPACE}/${FRONTEND_IMAGE_NAME}:latest \\
                                    -f docker/frontend/Dockerfile \\
                                    .

                                # 推送镜像
                                docker push ${ALIYUN_REGISTRY}/${ALIYUN_NAMESPACE}/${FRONTEND_IMAGE_NAME}:latest

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
                echo "开始构建 WebSocket 镜像（${PLATFORM}）..."
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

                                # 构建WebSocket镜像（含Playwright）
                                docker build \\
                                    --platform ${PLATFORM} \\
                                    --memory ${BUILD_MEMORY} \\
                                    --memory-swap ${BUILD_MEMORY_SWAP} \\
                                    --cpu-period ${BUILD_CPU_PERIOD} \\
                                    --cpu-quota ${BUILD_CPU_QUOTA} \\
                                    -t ${ALIYUN_REGISTRY}/${ALIYUN_NAMESPACE}/${WEBSOCKET_IMAGE_NAME}:latest \\
                                    -f websocket/Dockerfile \\
                                    .

                                # 推送镜像
                                docker push ${ALIYUN_REGISTRY}/${ALIYUN_NAMESPACE}/${WEBSOCKET_IMAGE_NAME}:latest

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
                echo "开始构建 Backend-Web 镜像（${PLATFORM}）..."
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

                                # 构建Backend-Web镜像
                                docker build \\
                                    --platform ${PLATFORM} \\
                                    --memory ${BUILD_MEMORY} \\
                                    --memory-swap ${BUILD_MEMORY_SWAP} \\
                                    --cpu-period ${BUILD_CPU_PERIOD} \\
                                    --cpu-quota ${BUILD_CPU_QUOTA} \\
                                    -t ${ALIYUN_REGISTRY}/${ALIYUN_NAMESPACE}/${BACKEND_WEB_IMAGE_NAME}:latest \\
                                    -f backend-web/Dockerfile \\
                                    .

                                # 推送镜像
                                docker push ${ALIYUN_REGISTRY}/${ALIYUN_NAMESPACE}/${BACKEND_WEB_IMAGE_NAME}:latest

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
                echo "开始构建 Scheduler 镜像（含Playwright，${PLATFORM}）..."
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

                                # 构建Scheduler镜像（含Playwright）
                                docker build \\
                                    --platform ${PLATFORM} \\
                                    --memory ${BUILD_MEMORY} \\
                                    --memory-swap ${BUILD_MEMORY_SWAP} \\
                                    --cpu-period ${BUILD_CPU_PERIOD} \\
                                    --cpu-quota ${BUILD_CPU_QUOTA} \\
                                    -t ${ALIYUN_REGISTRY}/${ALIYUN_NAMESPACE}/${SCHEDULER_IMAGE_NAME}:latest \\
                                    -f scheduler/Dockerfile \\
                                    .

                                # 推送镜像
                                docker push ${ALIYUN_REGISTRY}/${ALIYUN_NAMESPACE}/${SCHEDULER_IMAGE_NAME}:latest

                                # 登出
                                docker logout ${ALIYUN_REGISTRY}
                            """
                        }
                    }
                }
                echo '✓ Scheduler 镜像推送完成！'
            }
        }

        stage('清理本地镜像缓存') {
            steps {
                echo '清理悬空镜像缓存...'
                sh """
                    # 清理悬空镜像，释放磁盘空间
                    docker image prune -f || true
                """
                echo '✓ 清理完成！'
            }
        }
    }

    post {
        success {
            echo """
            ========================================
            闲鱼自动回复系统 构建成功！（仅 amd64）
            ========================================
            构建编号：${BUILD_NUMBER}
            构建平台：${PLATFORM}

            镜像已推送到阿里云镜像仓库：
            ────────────────────────────────────────
            前端镜像:
              ${ALIYUN_REGISTRY}/${ALIYUN_NAMESPACE}/${FRONTEND_IMAGE_NAME}:latest

            WebSocket镜像:
              ${ALIYUN_REGISTRY}/${ALIYUN_NAMESPACE}/${WEBSOCKET_IMAGE_NAME}:latest

            Backend-Web镜像:
              ${ALIYUN_REGISTRY}/${ALIYUN_NAMESPACE}/${BACKEND_WEB_IMAGE_NAME}:latest

            Scheduler镜像:
              ${ALIYUN_REGISTRY}/${ALIYUN_NAMESPACE}/${SCHEDULER_IMAGE_NAME}:latest

            支持的架构：
              linux/amd64  (x86_64 - Intel/AMD 处理器)

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

            ========================================
            服务说明：
            ========================================
              前端: http://localhost:9000
              Backend-Web API: http://localhost:8089
              WebSocket: http://localhost:8090
              Scheduler: http://localhost:8091
              MySQL: 内置容器（仅内部网络）
              Redis: 内置容器（仅内部网络）
            ========================================
            """
        }
        failure {
            echo """
            ========================================
            闲鱼自动回复系统 构建失败！
            ========================================
            可能的原因：
            1. GitHub 网络/加速镜像不可用
            2. 阿里云镜像仓库凭据配置错误
            3. Docker 守护进程不可用
            4. Dockerfile 构建失败
            5. 网络连接问题

            解决方案：
            1. 检查 GitHub 加速镜像可用性
            2. 检查阿里云凭据: Jenkins -> 凭据管理 -> aliyun-docker-credentials
            3. 检查 docker 环境: docker version / docker info
            4. 查看详细日志定位具体失败的服务
            ========================================
            """
        }
        always {
            echo '闲鱼自动回复系统 构建流程结束。'
        }
    }
}
