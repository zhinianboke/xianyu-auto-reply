#!/bin/bash
# ==========================================
# 闲鱼自动回复系统 - 远程 MySQL/Redis 一键部署脚本
# 使用外部（远程）MySQL 和 Redis，仅启动应用服务（不内置 mysql/redis 容器）
# 自动生成 docker-compose.remote.yml 与 .env.remote 并拉取镜像启动
# 用法: bash deploy_remote.sh
# ==========================================

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

WORK_DIR="$(cd "$(dirname "$0")" && pwd)"
COMPOSE_FILE="$WORK_DIR/docker-compose.remote.yml"
ENV_FILE="$WORK_DIR/.env.remote"

echo "=========================================="
echo "  闲鱼自动回复系统 - 远程 MySQL/Redis 部署"
echo "=========================================="
echo ""

# ========== 检查环境 ==========
if ! command -v docker &> /dev/null; then
    echo -e "${RED}错误: Docker 未安装，请先安装 Docker${NC}"
    echo "安装教程: https://docs.docker.com/get-docker/"
    exit 1
fi

if docker compose version &> /dev/null; then
    DC="docker compose"
elif command -v docker-compose &> /dev/null; then
    DC="docker-compose"
else
    echo -e "${RED}错误: Docker Compose 未安装${NC}"
    exit 1
fi

export COMPOSE_PROJECT_NAME=xianyu-auto-reply
DC_CMD="$DC -f $COMPOSE_FILE --env-file $ENV_FILE"

echo -e "${CYAN}[信息] Docker: $(docker --version)${NC}"
echo -e "${CYAN}[信息] Compose: $DC${NC}"
echo -e "${CYAN}[信息] 项目目录: $WORK_DIR${NC}"
echo ""

# ========== 生成 .env.remote 配置文件 ==========
if [ ! -f "$ENV_FILE" ]; then
    echo -e "${YELLOW}[提示] 首次部署，生成默认配置文件 .env.remote${NC}"
    cat > "$ENV_FILE" << 'ENVEOF'
# ==========================================
# 闲鱼自动回复系统 - 远程 MySQL / Redis 环境变量配置
# ==========================================

# ========== 远程 MySQL 配置（必填，请改成你的远程数据库地址） ==========
# 注意：不要填 localhost / 127.0.0.1（容器内会指向容器自身）
# 远程库需提前创建好 MYSQL_DATABASE，并授权 MYSQL_USER 可从部署机 IP 远程访问
MYSQL_HOST=your-remote-mysql-host
MYSQL_PORT=3306
MYSQL_DATABASE=xianyu_data
MYSQL_USER=xianyu
MYSQL_PASSWORD=xianyu@2026

# ========== 远程 Redis 配置（必填，请改成你的远程 Redis 地址） ==========
# 同样不要填 localhost / 127.0.0.1
REDIS_HOST=your-remote-redis-host
REDIS_PORT=6379
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
    echo -e "${GREEN}✓ 已生成 .env.remote 文件${NC}"
    echo -e "${RED}[重要] 请先编辑 $ENV_FILE 填写远程 MYSQL_HOST / REDIS_HOST 等连接信息，${NC}"
    echo -e "${RED}       填写完成后重新运行 bash deploy_remote.sh${NC}"
    exit 0
fi

# ========== 生成 docker-compose.remote.yml（远程镜像 + 远程 MySQL/Redis） ==========
echo "[信息] 生成 docker-compose.remote.yml..."
cat > "$COMPOSE_FILE" << 'COMPOSEEOF'
# Docker Compose 配置文件 - 远程 MySQL / Redis 版
# 闲鱼自动回复系统 - 使用外部（远程）MySQL 和 Redis，仅启动应用服务
# 由 deploy_remote.sh 自动生成，请勿手动修改

services:
  # ====== 应用服务（远程镜像 + 远程 MySQL/Redis） ======

  # Backend-Web 服务
  backend-web:
    image: ${IMAGE_REGISTRY:-registry.cn-shanghai.aliyuncs.com/zhinian-software}/xianyu-backend-web:${IMAGE_TAG:-latest}
    container_name: xianyu-backend-web
    restart: unless-stopped
    environment:
      - ENVIRONMENT=production
      - MYSQL_HOST=${MYSQL_HOST}
      - MYSQL_PORT=${MYSQL_PORT:-3306}
      - MYSQL_USER=${MYSQL_USER:-xianyu}
      - MYSQL_PASSWORD=${MYSQL_PASSWORD:-xianyu@2026}
      - MYSQL_DATABASE=${MYSQL_DATABASE:-xianyu_data}
      - REDIS_HOST=${REDIS_HOST}
      - REDIS_PORT=${REDIS_PORT:-6379}
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
      - MYSQL_HOST=${MYSQL_HOST}
      - MYSQL_PORT=${MYSQL_PORT:-3306}
      - MYSQL_USER=${MYSQL_USER:-xianyu}
      - MYSQL_PASSWORD=${MYSQL_PASSWORD:-xianyu@2026}
      - MYSQL_DATABASE=${MYSQL_DATABASE:-xianyu_data}
      - REDIS_HOST=${REDIS_HOST}
      - REDIS_PORT=${REDIS_PORT:-6379}
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
      - MYSQL_HOST=${MYSQL_HOST}
      - MYSQL_PORT=${MYSQL_PORT:-3306}
      - MYSQL_USER=${MYSQL_USER:-xianyu}
      - MYSQL_PASSWORD=${MYSQL_PASSWORD:-xianyu@2026}
      - MYSQL_DATABASE=${MYSQL_DATABASE:-xianyu_data}
      - REDIS_HOST=${REDIS_HOST}
      - REDIS_PORT=${REDIS_PORT:-6379}
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
echo -e "${GREEN}✓ docker-compose.remote.yml 已生成${NC}"
echo ""

# ========== 校验远程连接配置 ==========
mysql_host=$(grep -E "^MYSQL_HOST=" "$ENV_FILE" 2>/dev/null | cut -d '=' -f2- | tr -d '\r' | xargs)
redis_host=$(grep -E "^REDIS_HOST=" "$ENV_FILE" 2>/dev/null | cut -d '=' -f2- | tr -d '\r' | xargs)

if [ -z "$mysql_host" ] || [ "$mysql_host" = "your-remote-mysql-host" ]; then
    echo -e "${RED}错误: 请先在 $ENV_FILE 中填写真实的 MYSQL_HOST（远程数据库地址）${NC}"
    exit 1
fi
if [ -z "$redis_host" ] || [ "$redis_host" = "your-remote-redis-host" ]; then
    echo -e "${RED}错误: 请先在 $ENV_FILE 中填写真实的 REDIS_HOST（远程 Redis 地址）${NC}"
    exit 1
fi

case "$mysql_host" in
    localhost|127.0.0.1)
        echo -e "${YELLOW}[警告] MYSQL_HOST=$mysql_host，容器内的 localhost 指向容器自身，${NC}"
        echo -e "${YELLOW}       若数据库在宿主机上，请改用 host.docker.internal 或宿主机内网 IP${NC}"
        ;;
esac
case "$redis_host" in
    localhost|127.0.0.1)
        echo -e "${YELLOW}[警告] REDIS_HOST=$redis_host，容器内的 localhost 指向容器自身，${NC}"
        echo -e "${YELLOW}       若 Redis 在宿主机上，请改用 host.docker.internal 或宿主机内网 IP${NC}"
        ;;
esac

echo -e "${CYAN}[信息] 远程 MySQL: $mysql_host${NC}"
echo -e "${CYAN}[信息] 远程 Redis: $redis_host${NC}"
echo ""

# ========== 创建挂载目录 ==========
mkdir -p \
    "$WORK_DIR/xianyu_auto_reply/logs/backend_web" \
    "$WORK_DIR/xianyu_auto_reply/logs/websocket" \
    "$WORK_DIR/xianyu_auto_reply/logs/scheduler" \
    "$WORK_DIR/xianyu_auto_reply/static" \
    "$WORK_DIR/xianyu_auto_reply/backups" \
    "$WORK_DIR/xianyu_auto_reply/browser_data"

# ========== 部署 ==========
echo -e "${YELLOW}步骤 1/3: 停止旧容器（仅本项目）...${NC}"
$DC_CMD down 2>/dev/null || true
echo -e "${GREEN}✓ 旧容器已清理${NC}"

echo ""
echo -e "${YELLOW}步骤 2/3: 拉取最新镜像...${NC}"
$DC_CMD pull
echo -e "${GREEN}✓ 镜像拉取完成${NC}"

echo ""
echo -e "${YELLOW}步骤 3/3: 启动服务...${NC}"
$DC_CMD up -d
echo -e "${GREEN}✓ 服务已启动${NC}"

echo ""
echo "[信息] 等待服务启动..."
sleep 15
$DC_CMD ps

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
echo ""
