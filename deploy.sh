#!/bin/bash
# ==========================================
# 闲鱼自动回复系统 - 一键部署脚本
# 自动检查并安装 Docker/Compose，生成配置并拉取远程镜像启动
# 用法: bash deploy.sh
# ==========================================

set -e

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

WORK_DIR="$(cd "$(dirname "$0")" && pwd)"
COMPOSE_FILE="$WORK_DIR/docker-compose.deploy.yml"
ENV_FILE="$WORK_DIR/.env"

echo "=========================================="
echo "  闲鱼自动回复系统 - 一键部署"
echo "=========================================="
echo ""

# ========== 检查环境 ==========
INSTALL_ROOT=()
DOCKER_PREFIX=()
INSTALL_APT_UPDATED=0

install_error() {
    printf '[错误] %s\n' "$*" >&2
    exit 1
}

# 安装和启动系统服务时使用 root 或免密 sudo，避免 SSH/管道执行等待密码。
require_install_root() {
    if [ "$EUID" -ne 0 ]; then
        command -v sudo >/dev/null 2>&1 && sudo -n true ||
            install_error '自动安装或启动 Docker 需要 root 或免密 sudo，请使用具备权限的账号'
        INSTALL_ROOT=(sudo -n)
    fi
}

install_as_root() {
    "${INSTALL_ROOT[@]}" "$@" </dev/null
}

# Debian/Ubuntu 安装软件前刷新索引；任一软件源更新失败立即停止，同次部署只刷新一次。
update_install_index() {
    if [ "$INSTALL_PM" != apt ] || [ "$INSTALL_APT_UPDATED" = 1 ]; then return; fi
    echo '[信息] 正在更新 APT 软件包索引…'
    install_as_root apt-get -o APT::Update::Error-Mode=any update ||
        install_error 'APT 软件包索引更新失败，请检查软件源和网络后重试'
    INSTALL_APT_UPDATED=1
}

# 以安装权限检查配置和符号链接，避免普通账号无读取权限时误判为不存在。
install_path_exists() {
    install_as_root test -e "$1" || install_as_root test -L "$1"
}

# 使用参考脚本的 wget 下载方式，失败时保留真实错误输出。
download_install_file() {
    if ! command -v wget >/dev/null 2>&1; then
        detect_install_os
        update_install_index
        install_as_root "$INSTALL_PM" install -y wget || install_error '安装 wget 下载工具失败'
    fi
    wget --tries=3 --timeout=30 -O "$2" "$1" </dev/null
}

# 仅缺少组件时识别发行版；已可用的 Docker/Compose 不重复安装。
detect_install_os() {
    local ID=''
    [ -r /etc/os-release ] || install_error '无法识别 Linux 发行版：缺少 /etc/os-release'
    . /etc/os-release
    case "$ID" in
        ubuntu|debian) INSTALL_PM=apt ;;
        centos) INSTALL_PM=yum ;;
        *) install_error "自动安装暂不支持 $ID，请手动安装 Docker 与 Compose 后重试" ;;
    esac
    command -v "$INSTALL_PM" >/dev/null 2>&1 || install_error "缺少包管理器 $INSTALL_PM"
}

# 直接采用 build-env1.sh 的 Docker 包、阿里云源和 daemon.json 下载地址。
install_docker() {
    require_install_root
    detect_install_os
    echo '[信息] Docker 未安装，开始自动安装…'
    if [ "$INSTALL_PM" = apt ]; then
        update_install_index
        install_as_root env DEBIAN_FRONTEND=noninteractive apt install -y docker.io || install_error 'Docker 安装失败'
    else
        install_as_root yum install -y yum-utils device-mapper-persistent-data lvm2 ||
            install_error '安装 Docker 软件源依赖失败'
        if install_path_exists /etc/yum.repos.d/docker-ce.repo; then
            install_as_root cp -a -- /etc/yum.repos.d/docker-ce.repo "/etc/yum.repos.d/docker-ce.repo.backup.$(date +%Y%m%d%H%M%S).$$" ||
                install_error '备份已有 Docker 软件源失败'
        fi
        install_as_root yum-config-manager --add-repo http://mirrors.aliyun.com/docker-ce/linux/centos/docker-ce.repo ||
            install_error '添加阿里云 Docker CE 软件源失败'
        install_as_root yum install -y docker-ce docker-ce-cli containerd.io || install_error 'Docker CE 安装失败'
        install_as_root systemctl enable docker || install_error '设置 Docker 开机启动失败'
        install_as_root systemctl start docker || install_error 'Docker 启动失败'
    fi
    type -P docker >/dev/null 2>&1 || install_error '安装完成后仍未找到 Docker 命令'
    # 下载参考脚本使用的配置；已有配置保留，避免覆盖服务器原有设置。
    if ! install_path_exists /etc/docker/daemon.json; then
        local config_file
        config_file=$(mktemp) || install_error '无法创建 Docker 配置临时文件'
        download_install_file 'https://selfdownload.zhinianboke.com/file/website/docker/daemon.json' "$config_file" ||
            { rm -f -- "$config_file"; install_error '下载 Docker 配置失败'; }
        install_as_root mkdir -p /etc/docker ||
            { rm -f -- "$config_file"; install_error '创建 Docker 配置目录失败'; }
        install_as_root install -m 0644 "$config_file" /etc/docker/daemon.json ||
            { rm -f -- "$config_file"; install_error '写入 Docker 配置失败'; }
        rm -f -- "$config_file"
        install_as_root systemctl restart docker.service || install_error '应用 Docker 配置并重启失败'
    fi
}

# 所有部署阶段的 Docker 调用使用同一权限；command 避免同名函数递归。
docker() {
    command "${DOCKER_PREFIX[@]}" docker "$@"
}

# 优先使用插件，也兼容已有可执行的 docker-compose 独立命令。
select_compose() {
    if docker compose version >/dev/null 2>&1; then
        DC="${DOCKER_PREFIX[*]:+${DOCKER_PREFIX[*]} }docker compose"
    elif command "${DOCKER_PREFIX[@]}" docker-compose version >/dev/null 2>&1; then
        DC="${DOCKER_PREFIX[*]:+${DOCKER_PREFIX[*]} }docker-compose"
    else
        return 1
    fi
}

# 采用 build-env1.sh 的 docker-compose 文件、安装位置和软链接。
install_compose() {
    require_install_root
    local compose_file target=/usr/local/bin/docker-compose link=/usr/bin/docker-compose
    echo '[信息] docker-compose 未安装，开始从参考脚本地址下载安装…'
    compose_file=$(mktemp) || install_error '无法创建 docker-compose 下载临时文件'
    download_install_file 'https://selfdownload.zhinianboke.com/file/website/docker/docker-compose' "$compose_file" ||
        { rm -f -- "$compose_file"; install_error 'docker-compose 下载失败'; }
    install_as_root mkdir -p /usr/local/bin ||
        { rm -f -- "$compose_file"; install_error '创建 docker-compose 安装目录失败'; }
    if install_path_exists "$target"; then
        install_as_root cp -a -- "$target" "$target.backup.$(date +%Y%m%d%H%M%S).$$" ||
            { rm -f -- "$compose_file"; install_error '备份已有 docker-compose 文件失败'; }
    fi
    install_as_root install -m 0755 "$compose_file" "$target" ||
        { rm -f -- "$compose_file"; install_error '安装 docker-compose 文件失败'; }
    rm -f -- "$compose_file"
    if install_path_exists "$link" && [ "$(install_as_root readlink "$link" || true)" != "$target" ]; then
        install_as_root mv -- "$link" "$link.backup.$(date +%Y%m%d%H%M%S).$$" ||
            install_error '备份已有 docker-compose 链接失败'
    fi
    if ! install_path_exists "$link"; then
        install_as_root ln -s "$target" "$link" || install_error '创建 docker-compose 软链接失败'
    fi
    command "${DOCKER_PREFIX[@]}" "$target" --version ||
        install_error '下载的 docker-compose 无法运行，请检查服务器架构及运行依赖'
    # 使用完整路径，避免 SSH 账号 PATH 未包含 /usr/local/bin。
    DC="${DOCKER_PREFIX[*]:+${DOCKER_PREFIX[*]} }$target"
}

prepare_docker_environment() {
    [ "$(uname -s)" = Linux ] || install_error '此部署脚本仅支持 Linux 服务器'
    local installed=0 context=''
    # 函数 docker 已定义，使用 type -P 检查真实客户端，避免把函数误当已安装。
    if ! type -P docker >/dev/null 2>&1; then install_docker; installed=1; fi
    docker --version || install_error 'Docker 客户端无法执行，请检查安装或 CPU 架构'
    if ! docker info >/dev/null 2>&1; then
        context=$(docker context show 2>/dev/null || true)
        if [ -n "${DOCKER_HOST:-}" ] || [ -n "${DOCKER_CONTEXT:-}" ] || { [ -n "$context" ] && [ "$context" != default ]; }; then
            docker info || true
            install_error '当前 Docker 自定义/远程连接不可用，请检查连接配置和权限'
        fi
        require_install_root
        DOCKER_PREFIX=("${INSTALL_ROOT[@]}")
        if ! docker info >/dev/null 2>&1; then
            if command -v systemctl >/dev/null 2>&1 && [ -d /run/systemd/system ]; then
                install_as_root systemctl enable docker || install_error '设置 Docker 开机启动失败'
                install_as_root systemctl start docker || install_error 'Docker 启动失败，请检查服务日志和 daemon.json'
            elif command -v service >/dev/null 2>&1; then
                install_as_root service docker start || install_error 'Docker 服务启动失败'
            else
                install_error '没有可用的服务管理器，请手动启动 Docker 后重试'
            fi
        fi
    fi
    if [ "$installed" = 1 ] && command -v systemctl >/dev/null 2>&1 && [ -d /run/systemd/system ]; then
        install_as_root systemctl enable docker || install_error '设置 Docker 开机启动失败'
    fi
    local attempt
    for ((attempt=1; attempt<=30; attempt++)); do
        if docker info >/dev/null 2>&1; then break; fi
        sleep 1
    done
    docker info >/dev/null || install_error 'Docker 守护进程不可用，请检查服务日志和访问权限'
    if select_compose; then return; fi
    install_compose
}

prepare_docker_environment </dev/null

export COMPOSE_PROJECT_NAME=xianyu-auto-reply
# 数组保留路径中的空格；日志中的命令使用 Shell 转义，方便直接复制执行。
read -r -a COMPOSE_COMMAND <<< "$DC"
COMPOSE_COMMAND+=(-f "$COMPOSE_FILE" --env-file "$ENV_FILE")
printf -v DC_CMD '%q ' "${COMPOSE_COMMAND[@]}"
DC_CMD=${DC_CMD% }

echo -e "${CYAN}[信息] Docker: $(docker --version)${NC}"
echo -e "${CYAN}[信息] Compose: $DC${NC}"
echo -e "${CYAN}[信息] 项目目录: $WORK_DIR${NC}"
echo ""

# ========== 生成 .env 配置文件 ==========
if [ ! -f "$ENV_FILE" ]; then
    echo -e "${YELLOW}[提示] 首次部署，生成默认配置文件 .env${NC}"
    cat > "$ENV_FILE" << 'ENVEOF'
# ==========================================
# 闲鱼自动回复系统 - 环境变量配置
# ==========================================

# MySQL数据库配置（Docker内置，自动创建）
MYSQL_ROOT_PASSWORD=xianyu@2026
MYSQL_DATABASE=xianyu_data
MYSQL_USER=xianyu
MYSQL_PASSWORD=xianyu@2026
MYSQL_MAX_CONNECTIONS=4000

# 数据库连接池配置（三个服务峰值合计 2640，低于 MySQL 最大连接数并预留管理连接）
BACKEND_DB_POOL_SIZE=800
BACKEND_DB_MAX_OVERFLOW=60
WEBSOCKET_DB_POOL_SIZE=800
WEBSOCKET_DB_MAX_OVERFLOW=150
SCHEDULER_DB_POOL_SIZE=800
SCHEDULER_DB_MAX_OVERFLOW=30
DB_POOL_TIMEOUT=30
DB_POOL_RECYCLE=1800
DB_POOL_PRE_PING=true
DB_POOL_USE_LIFO=true
DB_CONNECT_TIMEOUT=10

# Redis缓存配置（Docker内置）
REDIS_PASSWORD=xianyu@2026
REDIS_DB=0
REDIS_POOL_SIZE=800
REDIS_SOCKET_TIMEOUT=5
REDIS_SOCKET_CONNECT_TIMEOUT=3
REDIS_SOCKET_KEEPALIVE=true
REDIS_SOCKET_KEEPALIVE_IDLE=60
REDIS_SOCKET_KEEPALIVE_INTERVAL=10
REDIS_SOCKET_KEEPALIVE_COUNT=3
REDIS_HEALTH_CHECK_INTERVAL=30
REDIS_PROTOCOL=2
REDIS_STARTUP_MAX_RETRIES=5
REDIS_STARTUP_RETRY_BASE_DELAY=1
REDIS_STARTUP_RETRY_CAP_DELAY=10

# 说明：JWT 密钥由数据库统一托管（首次启动自动生成并持久化），无需在此配置

# 端口配置
FRONTEND_PORT=9000
BACKEND_WEB_PORT=8089
WEBSOCKET_PORT=8090
SCHEDULER_PORT=8091

# 镜像配置
IMAGE_REGISTRY=registry.cn-shanghai.aliyuncs.com/zhinian-software
IMAGE_TAG=latest

# 基础镜像（MySQL / Redis，从阿里云仓库拉取，由 sync_base_images.sh 同步上传）
MYSQL_IMAGE=registry.cn-shanghai.aliyuncs.com/zhinian-software/xianyu-mysql:8.0
REDIS_IMAGE=registry.cn-shanghai.aliyuncs.com/zhinian-software/xianyu-redis:7-alpine

# 日志级别
LOG_LEVEL=INFO

# 在线安装：SSH 连接超时、脚本执行上限和任务日志保留期（秒）
ONLINE_INSTALL_CONNECT_TIMEOUT=60
ONLINE_INSTALL_TIMEOUT=7200
ONLINE_INSTALL_RETENTION_SECONDS=86400

# SQL 日志开关：true=打印每条执行的完整 SQL（便于排查）；默认 false，高并发生产环境建议保持关闭
SQL_ECHO=false

# IM Token 缓存（xy_token_cache 表）随机过期时间区间（小时），不配置默认 5~10 小时
TOKEN_CACHE_TTL_MIN_HOURS=5
TOKEN_CACHE_TTL_MAX_HOURS=10

# Token过期时间（分钟）
ACCESS_TOKEN_EXPIRE_MINUTES=1440
REFRESH_TOKEN_EXPIRE_MINUTES=10080

# 定时任务间隔（分钟）
REDELIVERY_INTERVAL=5
RATE_INTERVAL=20

# 验证码并发数
MAX_CAPTCHA_CONCURRENT=3

# WebSocket 启动时是否自动连接账号
AUTO_START_WEBSOCKET=true
# 滑块验证 DrissionPage 兜底引擎（主引擎失败后重试）：开关 / 超时秒 / 无头
CAPTCHA_DRISSIONPAGE_FALLBACK_ENABLED=false
CAPTCHA_DRISSIONPAGE_TIMEOUT=25
CAPTCHA_DRISSIONPAGE_HEADLESS=true

# 分销卡券上游服务基址（「分销卡券」页面提货 + 个人设置一键创建对接卡密秘钥共用此基址）
CARD_DOCK_BASE_URL=http://backend.zhinianboke.com
# 个人设置「对接卡密秘钥」一键创建密钥的鉴权 key（基址复用 CARD_DOCK_BASE_URL）
EXTERNAL_API_KEY=zhinian_bk

# 前端公网访问地址（用于生成前端页面分享链接，留空则使用默认）
FRONTEND_PUBLIC_URL=
# 启动时是否自动启动 Goofish 定时采集任务
AUTO_START_CRAWL_JOBS=true
# 远程官方服务基址（仪表盘广告、系统公告 = 本地内容 + 远程官方内容）
REMOTE_OFFICIAL_BASE_URL=https://xy.zhinianboke.com
# 是否启用远程官方广告合并展示（官方服务器自身部署建议设为 false）
ENABLE_REMOTE_ADS=true
# 是否启用远程官方公告合并展示（官方服务器自身部署建议设为 false）
ENABLE_REMOTE_ANNOUNCEMENTS=true
# 是否启用远程官方弹窗公告合并展示（官方服务器自身部署建议设为 false）
ENABLE_REMOTE_POPUP_ANNOUNCEMENTS=true
ENVEOF
    echo -e "${GREEN}✓ 已生成 .env 文件${NC}"
    echo -e "${YELLOW}[提示] 如需修改配置（如端口等），请编辑 $ENV_FILE 后重新运行${NC}"
    echo ""
fi

# ========== 生成 docker-compose.deploy.yml（远程镜像版） ==========
echo "[信息] 生成 docker-compose.deploy.yml（远程镜像版）..."
cat > "$COMPOSE_FILE" << 'COMPOSEEOF'
# Docker Compose 配置文件 - 远程镜像部署版
# 闲鱼自动回复系统 - 从镜像仓库拉取预构建镜像
# 由 deploy.sh 自动生成，请勿手动修改

services:
  # ====== 基础设施 ======

  # MySQL数据库（默认从阿里云仓库拉取，可通过 MYSQL_IMAGE 覆盖）
  mysql:
    image: ${MYSQL_IMAGE:-registry.cn-shanghai.aliyuncs.com/zhinian-software/xianyu-mysql:8.0}
    container_name: xianyu-mysql
    restart: unless-stopped
    environment:
      - MYSQL_ROOT_PASSWORD=${MYSQL_ROOT_PASSWORD:-xianyu@2026}
      - MYSQL_DATABASE=${MYSQL_DATABASE:-xianyu_data}
      - MYSQL_USER=${MYSQL_USER:-xianyu}
      - MYSQL_PASSWORD=${MYSQL_PASSWORD:-xianyu@2026}
      - TZ=Asia/Shanghai
    command:
      - --character-set-server=utf8mb4
      - --collation-server=utf8mb4_unicode_ci
      - --max-connections=${MYSQL_MAX_CONNECTIONS:-4000}
      - --max-connect-errors=100000
      - --max-allowed-packet=256M
      - --default-time-zone=+08:00
    volumes:
      - ./xianyu_auto_reply/mysql/data:/var/lib/mysql
    networks:
      - xianyu-network
    healthcheck:
      test: ["CMD", "mysqladmin", "ping", "-h", "127.0.0.1", "-u", "root", "-p${MYSQL_ROOT_PASSWORD:-xianyu@2026}"]
      interval: 10s
      timeout: 5s
      retries: 10
      start_period: 30s

  # Redis缓存（默认从阿里云仓库拉取，可通过 REDIS_IMAGE 覆盖）
  redis:
    image: ${REDIS_IMAGE:-registry.cn-shanghai.aliyuncs.com/zhinian-software/xianyu-redis:7-alpine}
    container_name: xianyu-redis
    restart: unless-stopped
    command: >
      redis-server
      --requirepass ${REDIS_PASSWORD:-xianyu@2026}
      --maxmemory 256mb
      --maxmemory-policy allkeys-lru
      --appendonly yes
    environment:
      - TZ=Asia/Shanghai
    volumes:
      - ./xianyu_auto_reply/redis/data:/data
    networks:
      - xianyu-network
    healthcheck:
      test: ["CMD", "redis-cli", "-a", "${REDIS_PASSWORD:-xianyu@2026}", "ping"]
      interval: 10s
      timeout: 5s
      retries: 5
      start_period: 10s

  # ====== 应用服务（远程镜像） ======

  # Backend-Web 服务
  backend-web:
    image: ${IMAGE_REGISTRY:-registry.cn-shanghai.aliyuncs.com/zhinian-software}/xianyu-backend-web:${IMAGE_TAG:-latest}
    container_name: xianyu-backend-web
    restart: unless-stopped
    environment:
      - ENVIRONMENT=production
      - MYSQL_HOST=mysql
      - MYSQL_PORT=3306
      - MYSQL_USER=${MYSQL_USER:-xianyu}
      - MYSQL_PASSWORD=${MYSQL_PASSWORD:-xianyu@2026}
      - MYSQL_DATABASE=${MYSQL_DATABASE:-xianyu_data}
      - DB_POOL_SIZE=${BACKEND_DB_POOL_SIZE:-800}
      - DB_MAX_OVERFLOW=${BACKEND_DB_MAX_OVERFLOW:-60}
      - DB_POOL_TIMEOUT=${DB_POOL_TIMEOUT:-30}
      - DB_POOL_RECYCLE=${DB_POOL_RECYCLE:-1800}
      - DB_POOL_PRE_PING=${DB_POOL_PRE_PING:-true}
      - DB_POOL_USE_LIFO=${DB_POOL_USE_LIFO:-true}
      - DB_CONNECT_TIMEOUT=${DB_CONNECT_TIMEOUT:-10}
      - REDIS_HOST=redis
      - REDIS_PORT=6379
      - REDIS_PASSWORD=${REDIS_PASSWORD:-xianyu@2026}
      - REDIS_DB=${REDIS_DB:-0}
      - REDIS_POOL_SIZE=${REDIS_POOL_SIZE:-800}
      - REDIS_SOCKET_TIMEOUT=${REDIS_SOCKET_TIMEOUT:-5}
      - REDIS_SOCKET_CONNECT_TIMEOUT=${REDIS_SOCKET_CONNECT_TIMEOUT:-3}
      - REDIS_SOCKET_KEEPALIVE=${REDIS_SOCKET_KEEPALIVE:-true}
      - REDIS_SOCKET_KEEPALIVE_IDLE=${REDIS_SOCKET_KEEPALIVE_IDLE:-60}
      - REDIS_SOCKET_KEEPALIVE_INTERVAL=${REDIS_SOCKET_KEEPALIVE_INTERVAL:-10}
      - REDIS_SOCKET_KEEPALIVE_COUNT=${REDIS_SOCKET_KEEPALIVE_COUNT:-3}
      - REDIS_HEALTH_CHECK_INTERVAL=${REDIS_HEALTH_CHECK_INTERVAL:-30}
      - REDIS_PROTOCOL=${REDIS_PROTOCOL:-2}
      - REDIS_STARTUP_MAX_RETRIES=${REDIS_STARTUP_MAX_RETRIES:-5}
      - REDIS_STARTUP_RETRY_BASE_DELAY=${REDIS_STARTUP_RETRY_BASE_DELAY:-1}
      - REDIS_STARTUP_RETRY_CAP_DELAY=${REDIS_STARTUP_RETRY_CAP_DELAY:-10}
      - BACKEND_WEB_PORT=8089
      - ONLINE_INSTALL_CONNECT_TIMEOUT=${ONLINE_INSTALL_CONNECT_TIMEOUT:-60}
      - ONLINE_INSTALL_TIMEOUT=${ONLINE_INSTALL_TIMEOUT:-7200}
      - ONLINE_INSTALL_RETENTION_SECONDS=${ONLINE_INSTALL_RETENTION_SECONDS:-86400}
      - HOST=0.0.0.0
      - JWT_ALGORITHM=HS256
      - ACCESS_TOKEN_EXPIRE_MINUTES=${ACCESS_TOKEN_EXPIRE_MINUTES:-1440}
      - REFRESH_TOKEN_EXPIRE_MINUTES=${REFRESH_TOKEN_EXPIRE_MINUTES:-10080}
      - INTERNAL_API_TOKEN=${INTERNAL_API_TOKEN:-}
      - CORS_ORIGINS=*
      - WEBSOCKET_SERVICE_URL=http://websocket:8090
      - SCHEDULER_SERVICE_URL=http://scheduler:8091
      - FRONTEND_SERVICE_URL=${FRONTEND_SERVICE_URL:-http://frontend:80}
      - STATIC_DIR=/app/static
      - BACKUP_DIR=/app/backups
      - BACKEND_WEB_PUBLIC_URL=${BACKEND_WEB_PUBLIC_URL:-}
      - CARD_DOCK_BASE_URL=${CARD_DOCK_BASE_URL:-http://backend.zhinianboke.com}
      - EXTERNAL_API_KEY=${EXTERNAL_API_KEY:-zhinian_bk}
      - FRONTEND_PUBLIC_URL=${FRONTEND_PUBLIC_URL:-}
      - AUTO_START_CRAWL_JOBS=${AUTO_START_CRAWL_JOBS:-true}
      - REMOTE_OFFICIAL_BASE_URL=${REMOTE_OFFICIAL_BASE_URL:-https://xy.zhinianboke.com}
      - ENABLE_REMOTE_ADS=${ENABLE_REMOTE_ADS:-true}
      - ENABLE_REMOTE_ANNOUNCEMENTS=${ENABLE_REMOTE_ANNOUNCEMENTS:-true}
      - ENABLE_REMOTE_POPUP_ANNOUNCEMENTS=${ENABLE_REMOTE_POPUP_ANNOUNCEMENTS:-true}
      - BROWSER_HEADLESS=true
      - LOG_LEVEL=${LOG_LEVEL:-INFO}
      - SQL_ECHO=${SQL_ECHO:-false}
      - TOKEN_CACHE_TTL_MIN_HOURS=${TOKEN_CACHE_TTL_MIN_HOURS:-5}
      - TOKEN_CACHE_TTL_MAX_HOURS=${TOKEN_CACHE_TTL_MAX_HOURS:-10}
      - TZ=Asia/Shanghai
    volumes:
      - ./xianyu_auto_reply/logs/backend_web:/app/backend-web/logs
      - ./xianyu_auto_reply/static:/app/static
      - ./xianyu_auto_reply/backups:/app/backups
    ports:
      - "${BACKEND_WEB_PORT:-8089}:8089"
    networks:
      - xianyu-network
    depends_on:
      mysql:
        condition: service_healthy
      redis:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8089/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 60s

  # WebSocket 服务
  websocket:
    image: ${IMAGE_REGISTRY:-registry.cn-shanghai.aliyuncs.com/zhinian-software}/xianyu-websocket:${IMAGE_TAG:-latest}
    container_name: xianyu-websocket
    restart: unless-stopped
    environment:
      - ENVIRONMENT=production
      - MYSQL_HOST=mysql
      - MYSQL_PORT=3306
      - MYSQL_USER=${MYSQL_USER:-xianyu}
      - MYSQL_PASSWORD=${MYSQL_PASSWORD:-xianyu@2026}
      - MYSQL_DATABASE=${MYSQL_DATABASE:-xianyu_data}
      - DB_POOL_SIZE=${WEBSOCKET_DB_POOL_SIZE:-800}
      - DB_MAX_OVERFLOW=${WEBSOCKET_DB_MAX_OVERFLOW:-150}
      - DB_POOL_TIMEOUT=${DB_POOL_TIMEOUT:-30}
      - DB_POOL_RECYCLE=${DB_POOL_RECYCLE:-1800}
      - DB_POOL_PRE_PING=${DB_POOL_PRE_PING:-true}
      - DB_POOL_USE_LIFO=${DB_POOL_USE_LIFO:-true}
      - DB_CONNECT_TIMEOUT=${DB_CONNECT_TIMEOUT:-10}
      - REDIS_HOST=redis
      - REDIS_PORT=6379
      - REDIS_PASSWORD=${REDIS_PASSWORD:-xianyu@2026}
      - REDIS_DB=${REDIS_DB:-0}
      - REDIS_POOL_SIZE=${REDIS_POOL_SIZE:-800}
      - REDIS_SOCKET_TIMEOUT=${REDIS_SOCKET_TIMEOUT:-5}
      - REDIS_SOCKET_CONNECT_TIMEOUT=${REDIS_SOCKET_CONNECT_TIMEOUT:-3}
      - REDIS_SOCKET_KEEPALIVE=${REDIS_SOCKET_KEEPALIVE:-true}
      - REDIS_SOCKET_KEEPALIVE_IDLE=${REDIS_SOCKET_KEEPALIVE_IDLE:-60}
      - REDIS_SOCKET_KEEPALIVE_INTERVAL=${REDIS_SOCKET_KEEPALIVE_INTERVAL:-10}
      - REDIS_SOCKET_KEEPALIVE_COUNT=${REDIS_SOCKET_KEEPALIVE_COUNT:-3}
      - REDIS_HEALTH_CHECK_INTERVAL=${REDIS_HEALTH_CHECK_INTERVAL:-30}
      - REDIS_PROTOCOL=${REDIS_PROTOCOL:-2}
      - REDIS_STARTUP_MAX_RETRIES=${REDIS_STARTUP_MAX_RETRIES:-5}
      - REDIS_STARTUP_RETRY_BASE_DELAY=${REDIS_STARTUP_RETRY_BASE_DELAY:-1}
      - REDIS_STARTUP_RETRY_CAP_DELAY=${REDIS_STARTUP_RETRY_CAP_DELAY:-10}
      - WEBSOCKET_PORT=8090
      - HOST=0.0.0.0
      - MAX_CAPTCHA_CONCURRENT=${MAX_CAPTCHA_CONCURRENT:-3}
      - BROWSER_HEADLESS=true
      - AUTO_START_WEBSOCKET=${AUTO_START_WEBSOCKET:-true}
      - CAPTCHA_DRISSIONPAGE_FALLBACK_ENABLED=${CAPTCHA_DRISSIONPAGE_FALLBACK_ENABLED:-false}
      - CAPTCHA_DRISSIONPAGE_TIMEOUT=${CAPTCHA_DRISSIONPAGE_TIMEOUT:-25}
      - CAPTCHA_DRISSIONPAGE_HEADLESS=${CAPTCHA_DRISSIONPAGE_HEADLESS:-true}
      - BACKEND_WEB_SERVICE_URL=http://backend-web:8089
      - INTERNAL_API_TOKEN=${INTERNAL_API_TOKEN:-}
      - STATIC_DIR=/app/static
      - LOG_LEVEL=${LOG_LEVEL:-INFO}
      - SQL_ECHO=${SQL_ECHO:-false}
      - TOKEN_CACHE_TTL_MIN_HOURS=${TOKEN_CACHE_TTL_MIN_HOURS:-5}
      - TOKEN_CACHE_TTL_MAX_HOURS=${TOKEN_CACHE_TTL_MAX_HOURS:-10}
      - TZ=Asia/Shanghai
    volumes:
      - ./xianyu_auto_reply/logs/websocket:/app/websocket/logs
      - ./xianyu_auto_reply/static:/app/static
      - ./xianyu_auto_reply/browser_data:/app/browser_data
    ports:
      - "${WEBSOCKET_PORT:-8090}:8090"
    networks:
      - xianyu-network
    depends_on:
      mysql:
        condition: service_healthy
      redis:
        condition: service_healthy
      backend-web:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8090/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 60s

  # Scheduler 服务
  scheduler:
    image: ${IMAGE_REGISTRY:-registry.cn-shanghai.aliyuncs.com/zhinian-software}/xianyu-scheduler:${IMAGE_TAG:-latest}
    container_name: xianyu-scheduler
    restart: unless-stopped
    environment:
      - ENVIRONMENT=production
      - MYSQL_HOST=mysql
      - MYSQL_PORT=3306
      - MYSQL_USER=${MYSQL_USER:-xianyu}
      - MYSQL_PASSWORD=${MYSQL_PASSWORD:-xianyu@2026}
      - MYSQL_DATABASE=${MYSQL_DATABASE:-xianyu_data}
      - DB_POOL_SIZE=${SCHEDULER_DB_POOL_SIZE:-800}
      - DB_MAX_OVERFLOW=${SCHEDULER_DB_MAX_OVERFLOW:-30}
      - DB_POOL_TIMEOUT=${DB_POOL_TIMEOUT:-30}
      - DB_POOL_RECYCLE=${DB_POOL_RECYCLE:-1800}
      - DB_POOL_PRE_PING=${DB_POOL_PRE_PING:-true}
      - DB_POOL_USE_LIFO=${DB_POOL_USE_LIFO:-true}
      - DB_CONNECT_TIMEOUT=${DB_CONNECT_TIMEOUT:-10}
      - REDIS_HOST=redis
      - REDIS_PORT=6379
      - REDIS_PASSWORD=${REDIS_PASSWORD:-xianyu@2026}
      - REDIS_DB=${REDIS_DB:-0}
      - REDIS_POOL_SIZE=${REDIS_POOL_SIZE:-800}
      - REDIS_SOCKET_TIMEOUT=${REDIS_SOCKET_TIMEOUT:-5}
      - REDIS_SOCKET_CONNECT_TIMEOUT=${REDIS_SOCKET_CONNECT_TIMEOUT:-3}
      - REDIS_SOCKET_KEEPALIVE=${REDIS_SOCKET_KEEPALIVE:-true}
      - REDIS_SOCKET_KEEPALIVE_IDLE=${REDIS_SOCKET_KEEPALIVE_IDLE:-60}
      - REDIS_SOCKET_KEEPALIVE_INTERVAL=${REDIS_SOCKET_KEEPALIVE_INTERVAL:-10}
      - REDIS_SOCKET_KEEPALIVE_COUNT=${REDIS_SOCKET_KEEPALIVE_COUNT:-3}
      - REDIS_HEALTH_CHECK_INTERVAL=${REDIS_HEALTH_CHECK_INTERVAL:-30}
      - REDIS_PROTOCOL=${REDIS_PROTOCOL:-2}
      - REDIS_STARTUP_MAX_RETRIES=${REDIS_STARTUP_MAX_RETRIES:-5}
      - REDIS_STARTUP_RETRY_BASE_DELAY=${REDIS_STARTUP_RETRY_BASE_DELAY:-1}
      - REDIS_STARTUP_RETRY_CAP_DELAY=${REDIS_STARTUP_RETRY_CAP_DELAY:-10}
      - SCHEDULER_PORT=8091
      - HOST=0.0.0.0
      - REDELIVERY_INTERVAL=${REDELIVERY_INTERVAL:-5}
      - RATE_INTERVAL=${RATE_INTERVAL:-20}
      - WEBSOCKET_SERVICE_URL=http://websocket:8090
      - BACKEND_WEB_SERVICE_URL=http://backend-web:8089
      - INTERNAL_API_TOKEN=${INTERNAL_API_TOKEN:-}
      - STATIC_DIR=/app/static
      - BACKUP_DIR=/app/backups
      - LOG_LEVEL=${LOG_LEVEL:-INFO}
      - SQL_ECHO=${SQL_ECHO:-false}
      - TZ=Asia/Shanghai
    volumes:
      - ./xianyu_auto_reply/logs/scheduler:/app/scheduler/logs
      - ./xianyu_auto_reply/static:/app/static:ro
      - ./xianyu_auto_reply/backups:/app/backups
    ports:
      - "${SCHEDULER_PORT:-8091}:8091"
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

  # 前端服务
  frontend:
    image: ${IMAGE_REGISTRY:-registry.cn-shanghai.aliyuncs.com/zhinian-software}/xianyu-frontend:${IMAGE_TAG:-latest}
    container_name: xianyu-frontend
    restart: unless-stopped
    environment:
      - TZ=Asia/Shanghai
    ports:
      - "${FRONTEND_PORT:-9000}:80"
    networks:
      - xianyu-network
    depends_on:
      backend-web:
        condition: service_healthy

networks:
  xianyu-network:
    driver: bridge
COMPOSEEOF
echo -e "${GREEN}✓ docker-compose.deploy.yml 已生成${NC}"
echo ""

# 在停止任何旧容器前验证配置，错误直接展示并终止。
"${COMPOSE_COMMAND[@]}" config --quiet || install_error 'Compose 配置验证失败，请检查 .env 和 Docker Compose 版本'

# ========== 检测并清理加密版残留 ==========
ENC_CONTAINERS=(
    "xianyu-enc-frontend"
    "xianyu-enc-backend-web"
    "xianyu-enc-websocket"
    "xianyu-enc-scheduler"
    "xianyu-enc-mysql"
    "xianyu-enc-redis"
)

enc_found=0
container_names=$(docker ps -a --format '{{.Names}}') || install_error '读取现有容器列表失败，已停止部署'
for container in "${ENC_CONTAINERS[@]}"; do
    if printf '%s\n' "$container_names" | grep -Fxq -- "$container"; then
        enc_found=1
        break
    fi
done

if [ $enc_found -eq 1 ]; then
    echo -e "${YELLOW}[信息] 检测到加密版容器，清理中（保留数据卷）...${NC}"
    for container in "${ENC_CONTAINERS[@]}"; do
        if printf '%s\n' "$container_names" | grep -Fxq -- "$container"; then
            echo -e "${CYAN}  停止并删除容器: ${container}${NC}"
            docker stop "$container" || install_error "停止加密版容器 $container 失败，已停止部署"
            docker rm "$container" || install_error "移除加密版容器 $container 失败，已停止部署"
        fi
    done
    # 清理加密版应用镜像
    for name in "xianyu-enc-frontend" "xianyu-enc-backend-web" "xianyu-enc-websocket" "xianyu-enc-scheduler"; do
        image_ids=$(docker images --filter "reference=*/${name}" --format '{{.ID}}') || install_error '读取加密版应用镜像失败'
        image_ids=$(printf '%s\n' "$image_ids" | sort -u)
        for id in $image_ids; do
            docker rmi "$id" || echo "[提示] 加密版镜像 $id 未移除，可能仍被其他容器使用，继续部署"
        done
    done
    # 按 Compose 项目标签清理，避免仅凭名称片段误删其他项目的网络。
    enc_networks=$(docker network ls --filter 'label=com.docker.compose.project=xianyu_auto_reply_enc' --format '{{.Name}}') ||
        install_error '读取加密版项目网络失败'
    for enc_network in $enc_networks; do
        docker network rm "$enc_network" || echo "[提示] 网络 $enc_network 未移除，可能仍在使用，继续部署"
    done
    echo -e "${GREEN}✓ 加密版已清理（数据卷已保留）${NC}"
    echo ""
fi

# ========== 创建挂载目录 ==========
mkdir -p \
    "$WORK_DIR/xianyu_auto_reply/mysql/data" \
    "$WORK_DIR/xianyu_auto_reply/redis/data" \
    "$WORK_DIR/xianyu_auto_reply/logs/backend_web" \
    "$WORK_DIR/xianyu_auto_reply/logs/websocket" \
    "$WORK_DIR/xianyu_auto_reply/logs/scheduler" \
    "$WORK_DIR/xianyu_auto_reply/static" \
    "$WORK_DIR/xianyu_auto_reply/backups" \
    "$WORK_DIR/xianyu_auto_reply/browser_data"

# ========== 部署 ==========
echo -e "${YELLOW}步骤 1/3: 拉取最新镜像（旧容器保持运行，减少停机时间）...${NC}"
"${COMPOSE_COMMAND[@]}" pull
echo -e "${GREEN}✓ 镜像拉取完成${NC}"

echo ""
echo -e "${YELLOW}步骤 2/3: 停止旧容器（仅本项目）...${NC}"
"${COMPOSE_COMMAND[@]}" down || install_error '停止本项目旧容器失败，请检查 Docker 状态后重试'
echo -e "${GREEN}✓ 旧容器已清理${NC}"

echo ""
echo -e "${YELLOW}步骤 3/3: 启动服务...${NC}"
"${COMPOSE_COMMAND[@]}" up -d
echo -e "${GREEN}✓ 服务已启动${NC}"

echo ""
echo "[信息] 等待服务启动..."
sleep 15
"${COMPOSE_COMMAND[@]}" ps

# 读取端口配置
frontend_port=$(grep -E "^FRONTEND_PORT=" "$ENV_FILE" 2>/dev/null | cut -d '=' -f2 | tr -d '\r' || echo "9000")
backend_web_port=$(grep -E "^BACKEND_WEB_PORT=" "$ENV_FILE" 2>/dev/null | cut -d '=' -f2 | tr -d '\r' || echo "8089")
websocket_port=$(grep -E "^WEBSOCKET_PORT=" "$ENV_FILE" 2>/dev/null | cut -d '=' -f2 | tr -d '\r' || echo "8090")
scheduler_port=$(grep -E "^SCHEDULER_PORT=" "$ENV_FILE" 2>/dev/null | cut -d '=' -f2 | tr -d '\r' || echo "8091")

frontend_port="${frontend_port:-9000}"
backend_web_port="${backend_web_port:-8089}"
websocket_port="${websocket_port:-8090}"
scheduler_port="${scheduler_port:-8091}"

echo ""
echo -e "${GREEN}=========================================="
echo "  部署完成！"
echo "==========================================${NC}"
echo ""
echo "服务访问地址："
echo "  前端:        http://服务器IP:${frontend_port}"
echo "  Backend-Web: http://服务器IP:${backend_web_port}"
echo "  WebSocket:   http://服务器IP:${websocket_port}"
echo "  Scheduler:   http://服务器IP:${scheduler_port}"
echo ""
echo "常用命令："
echo "  查看日志: $DC_CMD logs -f"
echo "  停止服务: $DC_CMD down"
echo "  重启服务: $DC_CMD restart"
echo "  更新版本: bash update.sh"
echo ""
