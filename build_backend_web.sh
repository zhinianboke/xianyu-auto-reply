#!/bin/bash
# ==========================================
# 闲鱼自动回复系统 - 单独构建并重启 Backend-Web 服务
# 用法: bash build_backend_web.sh
# ==========================================

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

WORK_DIR="$(cd "$(dirname "$0")" && pwd)"
COMPOSE_FILE="$WORK_DIR/docker-compose.yml"
ENV_FILE="$WORK_DIR/.env"

export COMPOSE_PROJECT_NAME="xianyu-auto-reply"

if docker compose version &> /dev/null; then
    DC="docker compose"
elif command -v docker-compose &> /dev/null; then
    DC="docker-compose"
else
    echo -e "${RED}错误: Docker Compose 未安装${NC}"
    exit 1
fi

DC_CMD="$DC -f $COMPOSE_FILE"
if [ -f "$ENV_FILE" ]; then
    DC_CMD="$DC -f $COMPOSE_FILE --env-file $ENV_FILE"
fi

echo "=========================================="
echo "  构建并重启 Backend-Web 服务"
echo "=========================================="
echo ""

echo -e "${YELLOW}[1/3] 停止 Backend-Web 容器...${NC}"
$DC_CMD stop backend-web 2>/dev/null || true
$DC_CMD rm -f backend-web 2>/dev/null || true
echo -e "${GREEN}✓ 已停止${NC}"
echo ""

echo -e "${YELLOW}[2/3] 重新构建 Backend-Web 镜像（--no-cache）...${NC}"
$DC_CMD build --no-cache backend-web
echo -e "${GREEN}✓ 构建完成${NC}"
echo ""

echo -e "${YELLOW}[3/3] 启动 Backend-Web 服务...${NC}"
$DC_CMD up -d backend-web
echo ""

sleep 5
$DC_CMD ps backend-web

echo ""
echo -e "${GREEN}✓ Backend-Web 服务已重启${NC}"
echo "查看日志: $DC_CMD logs -f backend-web"
