#!/bin/bash
# ==========================================
# 闲鱼自动回复系统 - 一键更新脚本
#
# 功能：
# 1. 拉取最新远程镜像并重建应用容器（frontend / backend-web / websocket / scheduler）
# 2. 不影响 MySQL / Redis 的数据（数据卷保留）
# 3. 自动检测并清理加密版（enc）的容器和镜像（保留数据卷）
# 4. 收尾清理本项目被替换的旧应用镜像，不影响其他项目
#
# 用法：
#   bash update.sh [update|logs|status|clean-enc|help]
# ==========================================

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

WORK_DIR="$(cd "$(dirname "$0")" && pwd)"
COMPOSE_FILE="$WORK_DIR/docker-compose.deploy.yml"
ENV_FILE="$WORK_DIR/.env"
CMD="${1:-update}"

export COMPOSE_PROJECT_NAME="${COMPOSE_PROJECT_NAME:-xianyu-auto-reply}"

# 应用服务列表（不含 mysql / redis）
APP_SERVICES=(
    "frontend"
    "backend-web"
    "websocket"
    "scheduler"
)

# 加密版相关容器名（包含基础设施容器，数据卷会保留）
ENC_CONTAINERS=(
    "xianyu-enc-frontend"
    "xianyu-enc-backend-web"
    "xianyu-enc-websocket"
    "xianyu-enc-scheduler"
    "xianyu-enc-mysql"
    "xianyu-enc-redis"
)

# 加密版应用镜像名
ENC_IMAGE_NAMES=(
    "xianyu-enc-frontend"
    "xianyu-enc-backend-web"
    "xianyu-enc-websocket"
    "xianyu-enc-scheduler"
)

# 应用镜像名（不含加密版前缀）
APP_IMAGE_NAMES=(
    "xianyu-frontend"
    "xianyu-backend-web"
    "xianyu-websocket"
    "xianyu-scheduler"
)

# 更新前记录的应用镜像 ID
APP_OLD_IMAGE_IDS=()
# 完整镜像 reference（registry/name:tag）
APP_IMAGE_REFS=()

print_banner() {
    echo "=========================================="
    echo "  闲鱼自动回复系统 - 一键更新"
    echo "=========================================="
    echo ""
}

check_docker() {
    if ! command -v docker &> /dev/null; then
        echo -e "${RED}[错误] Docker 未安装，请先安装 Docker${NC}"
        exit 1
    fi

    if docker compose version &> /dev/null; then
        DC_CMD=(docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE")
        DC_NAME="docker compose"
    elif command -v docker-compose &> /dev/null; then
        DC_CMD=(docker-compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE")
        DC_NAME="docker-compose"
    else
        echo -e "${RED}[错误] Docker Compose 未安装${NC}"
        exit 1
    fi

    echo -e "${CYAN}[信息] Docker: $(docker --version)${NC}"
    echo -e "${CYAN}[信息] Compose: $DC_NAME${NC}"
    echo -e "${CYAN}[信息] 项目目录: $WORK_DIR${NC}"
    echo ""
}

# 生成远程镜像版 docker-compose.deploy.yml
generate_compose_file() {
    cat > "$COMPOSE_FILE" << 'COMPOSEEOF'
services:
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
      - --max-connections=300
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
      - REDIS_HOST=redis
      - REDIS_PORT=6379
      - REDIS_PASSWORD=${REDIS_PASSWORD:-xianyu@2026}
      - REDIS_DB=${REDIS_DB:-0}
      - BACKEND_WEB_PORT=8089
      - HOST=0.0.0.0
      - JWT_ALGORITHM=HS256
      - ACCESS_TOKEN_EXPIRE_MINUTES=${ACCESS_TOKEN_EXPIRE_MINUTES:-1440}
      - REFRESH_TOKEN_EXPIRE_MINUTES=${REFRESH_TOKEN_EXPIRE_MINUTES:-10080}
      - CORS_ORIGINS=*
      - WEBSOCKET_SERVICE_URL=http://websocket:8090
      - SCHEDULER_SERVICE_URL=http://scheduler:8091
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
      - SQL_ECHO=${SQL_ECHO:-true}
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
      - REDIS_HOST=redis
      - REDIS_PORT=6379
      - REDIS_PASSWORD=${REDIS_PASSWORD:-xianyu@2026}
      - REDIS_DB=${REDIS_DB:-0}
      - WEBSOCKET_PORT=8090
      - HOST=0.0.0.0
      - MAX_CAPTCHA_CONCURRENT=${MAX_CAPTCHA_CONCURRENT:-3}
      - BROWSER_HEADLESS=true
      - AUTO_START_WEBSOCKET=${AUTO_START_WEBSOCKET:-true}
      - CAPTCHA_DRISSIONPAGE_FALLBACK_ENABLED=${CAPTCHA_DRISSIONPAGE_FALLBACK_ENABLED:-true}
      - CAPTCHA_DRISSIONPAGE_TIMEOUT=${CAPTCHA_DRISSIONPAGE_TIMEOUT:-25}
      - CAPTCHA_DRISSIONPAGE_HEADLESS=${CAPTCHA_DRISSIONPAGE_HEADLESS:-true}
      - BACKEND_WEB_SERVICE_URL=http://backend-web:8089
      - STATIC_DIR=/app/static
      - LOG_LEVEL=${LOG_LEVEL:-INFO}
      - SQL_ECHO=${SQL_ECHO:-true}
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
      - REDIS_HOST=redis
      - REDIS_PORT=6379
      - REDIS_PASSWORD=${REDIS_PASSWORD:-xianyu@2026}
      - REDIS_DB=${REDIS_DB:-0}
      - SCHEDULER_PORT=8091
      - HOST=0.0.0.0
      - REDELIVERY_INTERVAL=${REDELIVERY_INTERVAL:-5}
      - RATE_INTERVAL=${RATE_INTERVAL:-20}
      - WEBSOCKET_SERVICE_URL=http://websocket:8090
      - BACKEND_WEB_SERVICE_URL=http://backend-web:8089
      - STATIC_DIR=/app/static
      - BACKUP_DIR=/app/backups
      - LOG_LEVEL=${LOG_LEVEL:-INFO}
      - SQL_ECHO=${SQL_ECHO:-true}
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
}

check_deploy_files() {
    # 如果 .env 不存在，自动生成默认配置
    if [ ! -f "$ENV_FILE" ]; then
        echo -e "${YELLOW}[信息] 未找到 .env 配置文件，自动生成默认配置...${NC}"
        cat > "$ENV_FILE" << 'ENVEOF'
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

# 基础镜像（MySQL / Redis，从阿里云仓库拉取，由 sync_base_images.sh 同步上传）
MYSQL_IMAGE=registry.cn-shanghai.aliyuncs.com/zhinian-software/xianyu-mysql:8.0
REDIS_IMAGE=registry.cn-shanghai.aliyuncs.com/zhinian-software/xianyu-redis:7-alpine

# 日志级别
LOG_LEVEL=INFO

# SQL 日志开关：true=打印每条执行的完整 SQL（默认，便于排查）；高并发生产环境可设为 false
SQL_ECHO=true

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
CAPTCHA_DRISSIONPAGE_FALLBACK_ENABLED=true
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
        echo ""
    fi

    # 如果 docker-compose.deploy.yml 不存在，自动生成
    if [ ! -f "$COMPOSE_FILE" ]; then
        echo -e "${YELLOW}[信息] 未找到 docker-compose.deploy.yml，自动生成...${NC}"
        generate_compose_file
        echo -e "${GREEN}✓ docker-compose.deploy.yml 已生成${NC}"
        echo ""
    fi
}

# 创建宿主机挂载目录
create_mount_dirs() {
    mkdir -p \
        "$WORK_DIR/xianyu_auto_reply/mysql/data" \
        "$WORK_DIR/xianyu_auto_reply/redis/data" \
        "$WORK_DIR/xianyu_auto_reply/logs/backend_web" \
        "$WORK_DIR/xianyu_auto_reply/logs/websocket" \
        "$WORK_DIR/xianyu_auto_reply/logs/scheduler" \
        "$WORK_DIR/xianyu_auto_reply/static" \
        "$WORK_DIR/xianyu_auto_reply/backups" \
        "$WORK_DIR/xianyu_auto_reply/browser_data"
}

read_env_value() {
    local key="$1"
    local value
    value="$(grep -E "^${key}=" "$ENV_FILE" | tail -n 1 | cut -d '=' -f2- | tr -d '\r')"
    echo "$value"
}

# 检测并清理加密版容器和镜像（保留数据卷）
cleanup_enc_version() {
    echo -e "${YELLOW}[信息] 检测加密版部署残留...${NC}"

    local enc_found=0

    # 检查加密版容器是否存在
    for container in "${ENC_CONTAINERS[@]}"; do
        if docker ps -a --format '{{.Names}}' | grep -q "^${container}$"; then
            enc_found=1
            break
        fi
    done

    if [ $enc_found -eq 0 ]; then
        echo -e "${GREEN}✓ 未检测到加密版容器，无需清理${NC}"
        echo ""
        return
    fi

    echo -e "${YELLOW}[信息] 检测到加密版容器，开始清理（保留数据卷）...${NC}"

    # 停止并删除加密版所有容器（数据卷保留）
    for container in "${ENC_CONTAINERS[@]}"; do
        if docker ps -a --format '{{.Names}}' | grep -q "^${container}$"; then
            echo -e "${CYAN}  停止并删除容器: ${container}${NC}"
            docker stop "$container" 2>/dev/null || true
            docker rm "$container" 2>/dev/null || true
        fi
    done

    # 清理加密版应用镜像
    echo -e "${YELLOW}[信息] 清理加密版应用镜像...${NC}"
    local removed=0
    for name in "${ENC_IMAGE_NAMES[@]}"; do
        local image_ids
        image_ids=$(docker images --filter "reference=*/${name}*" --format '{{.ID}}' 2>/dev/null | sort -u)
        for id in $image_ids; do
            if docker rmi "$id" --force 2>/dev/null; then
                removed=$((removed+1))
            fi
        done
    done
    echo -e "${GREEN}✓ 已清理 ${removed} 个加密版应用镜像${NC}"

    # 尝试通过 docker compose 清理加密版项目（如果 compose 文件存在）
    local enc_compose_file="$WORK_DIR/docker-compose.enc.deploy.yml"
    local enc_env_file="$WORK_DIR/.env.enc"
    if [ -f "$enc_compose_file" ]; then
        echo -e "${YELLOW}[信息] 通过 Compose 清理加密版项目网络...${NC}"
        if docker compose version &> /dev/null; then
            COMPOSE_PROJECT_NAME=xianyu_auto_reply_enc docker compose -f "$enc_compose_file" --env-file "$enc_env_file" down --remove-orphans 2>/dev/null || true
        elif command -v docker-compose &> /dev/null; then
            COMPOSE_PROJECT_NAME=xianyu_auto_reply_enc docker-compose -f "$enc_compose_file" --env-file "$enc_env_file" down --remove-orphans 2>/dev/null || true
        fi
    fi

    # 清理加密版网络（如果存在）
    local enc_network
    for enc_network in $(docker network ls --format '{{.Name}}' | grep -i "enc" | grep -i "xianyu"); do
        echo -e "${CYAN}  删除网络: ${enc_network}${NC}"
        docker network rm "$enc_network" 2>/dev/null || true
    done

    echo -e "${GREEN}✓ 加密版清理完成（数据卷已保留）${NC}"
    echo ""
}

# 解析镜像完整引用
resolve_app_image_refs() {
    local registry tag
    registry="$(read_env_value IMAGE_REGISTRY)"
    tag="$(read_env_value IMAGE_TAG)"
    registry="${registry:-registry.cn-shanghai.aliyuncs.com/zhinian-software}"
    tag="${tag:-latest}"

    APP_IMAGE_REFS=()
    for name in "${APP_IMAGE_NAMES[@]}"; do
        APP_IMAGE_REFS+=("${registry}/${name}:${tag}")
    done
}

# 记录当前应用镜像 ID（用于后续清理旧镜像）
record_old_app_image_ids() {
    APP_OLD_IMAGE_IDS=()
    for ref in "${APP_IMAGE_REFS[@]}"; do
        local id
        id="$(docker images --no-trunc --format '{{.ID}}' "$ref" 2>/dev/null | head -n 1)"
        APP_OLD_IMAGE_IDS+=("$id")
    done
}

# 拉取最新镜像
pull_latest_images() {
    echo -e "${YELLOW}[信息] 拉取最新应用镜像（不影响 MySQL/Redis）...${NC}"
    "${DC_CMD[@]}" pull "${APP_SERVICES[@]}"
    echo -e "${GREEN}✓ 最新应用镜像拉取完成${NC}"
    echo ""
}

# 重建应用容器
recreate_app_services() {
    echo -e "${YELLOW}[信息] 使用最新镜像重建应用容器...${NC}"
    "${DC_CMD[@]}" up -d "${APP_SERVICES[@]}"
    echo -e "${YELLOW}[信息] 等待服务启动...${NC}"
    sleep 15
    "${DC_CMD[@]}" ps
    echo ""
}

# 清理本项目被替换的旧应用镜像
cleanup_old_app_images() {
    echo -e "${YELLOW}[信息] 清理旧应用镜像（不影响其他项目）...${NC}"
    local removed=0
    local i
    for ((i=0; i<${#APP_IMAGE_REFS[@]}; i++)); do
        local ref="${APP_IMAGE_REFS[$i]}"
        local old_id="${APP_OLD_IMAGE_IDS[$i]}"
        if [ -z "$old_id" ]; then
            continue
        fi
        local new_id
        new_id="$(docker images --no-trunc --format '{{.ID}}' "$ref" 2>/dev/null | head -n 1)"
        if [ -z "$new_id" ] || [ "$new_id" = "$old_id" ]; then
            continue
        fi
        if docker rmi "$old_id" >/dev/null 2>&1; then
            removed=$((removed+1))
        fi
    done
    echo -e "${GREEN}✓ 已清理 ${removed} 个旧应用镜像${NC}"
    echo ""
}

print_success_info() {
    local frontend_port backend_web_port websocket_port scheduler_port
    frontend_port="$(read_env_value FRONTEND_PORT)"
    backend_web_port="$(read_env_value BACKEND_WEB_PORT)"
    websocket_port="$(read_env_value WEBSOCKET_PORT)"
    scheduler_port="$(read_env_value SCHEDULER_PORT)"

    frontend_port="${frontend_port:-9000}"
    backend_web_port="${backend_web_port:-8089}"
    websocket_port="${websocket_port:-8090}"
    scheduler_port="${scheduler_port:-8091}"

    echo -e "${GREEN}=========================================="
    echo "  更新完成！"
    echo "==========================================${NC}"
    echo ""
    echo "服务访问地址："
    echo "  前端:        http://服务器IP:${frontend_port}"
    echo "  Backend-Web: http://服务器IP:${backend_web_port}"
    echo "  WebSocket:   http://服务器IP:${websocket_port}"
    echo "  Scheduler:   http://服务器IP:${scheduler_port}"
    echo ""
    echo "常用命令："
    echo "  查看状态: bash $0 status"
    echo "  查看日志: bash $0 logs"
    echo "  再次更新: bash $0 update"
    echo "  清理加密版: bash $0 clean-enc"
    echo ""
}

# 主更新流程
run_update() {
    print_banner
    check_docker
    check_deploy_files
    create_mount_dirs
    cleanup_enc_version
    resolve_app_image_refs
    record_old_app_image_ids
    pull_latest_images
    recreate_app_services
    cleanup_old_app_images
    print_success_info
}

# 仅清理加密版
run_clean_enc() {
    print_banner
    check_docker
    cleanup_enc_version
    echo -e "${GREEN}加密版清理完成。数据卷已保留。${NC}"
    echo ""
    echo -e "${YELLOW}[提示] 如需同时删除加密版的数据卷（会丢失所有数据），请手动执行：${NC}"
    echo "  docker volume rm xianyu_auto_reply_enc_mysql_data xianyu_auto_reply_enc_redis_data"
    echo ""
}

show_help() {
    echo "用法: bash update.sh [update|logs|status|clean-enc|help]"
    echo ""
    echo "  update    - 拉取最新镜像并重建应用容器，不影响 MySQL/Redis 数据（默认）"
    echo "  logs      - 查看实时日志"
    echo "  status    - 查看服务状态"
    echo "  clean-enc - 仅清理加密版容器和镜像（保留数据卷）"
    echo "  help      - 查看帮助"
}

case "$CMD" in
    update)
        run_update
        ;;
    logs)
        check_docker
        check_deploy_files
        "${DC_CMD[@]}" logs -f --tail=100
        ;;
    status)
        check_docker
        check_deploy_files
        "${DC_CMD[@]}" ps
        ;;
    clean-enc)
        check_docker
        run_clean_enc
        ;;
    help|-h|--help)
        show_help
        ;;
    *)
        show_help
        exit 1
        ;;
esac
