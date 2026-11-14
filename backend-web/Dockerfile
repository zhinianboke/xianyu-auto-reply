# Backend-Web 服务 Dockerfile
# 单阶段构建，直接使用Python源码
#
# 体积优化说明（详见 PR 描述）：
#   1. 系统基础包层与 scheduler / websocket 保持完全一致，三个镜像可以复用同一层；
#   2. gcc / libc6-dev 只在 pip 安装期间存在，同层安装并卸载，不会残留在镜像里；
#   3. playwright 先用 --with-deps 装一轮系统依赖，patchright 复用这些依赖，
#      不再触发第二次 apt 安装；
#   4. 每层结束都清理 apt lists 与缓存，避免无谓残留。

# 基础镜像走 docker.io 官方名（由 buildx 的 buildkitd 镜像加速配置拉取，见流水线 BUILDKIT 配置）
FROM python:3.11-slim

ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright
ENV PIP_DISABLE_PIP_VERSION_CHECK=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app
ENV TZ=Asia/Shanghai

# 配置国内镜像源
RUN sed -i 's|deb.debian.org|mirrors.aliyun.com|g' /etc/apt/sources.list.d/debian.sources 2>/dev/null || \
    sed -i 's|deb.debian.org|mirrors.aliyun.com|g' /etc/apt/sources.list 2>/dev/null || true
RUN pip config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple

WORKDIR /app

# 系统基础包：三个服务保持完全一致的命令，这层才能跨镜像复用
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl ca-certificates \
        fonts-dejavu-core fonts-liberation \
    && update-ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# 复制项目源码
COPY common /app/common
COPY backend-web /app/backend-web
COPY launcher /app/launcher

# 从pyproject.toml提取依赖
RUN python -c "\
import tomllib; \
deps = tomllib.load(open('/app/backend-web/pyproject.toml','rb')).get('project',{}).get('dependencies',[]); \
open('/tmp/requirements.txt','w').write('\n'.join(deps))"

# 安装依赖：编译工具与安装动作放在同一层，装完立即卸载，镜像里不留 gcc 及其依赖
RUN apt-get update && apt-get install -y --no-install-recommends gcc libc6-dev \
    && pip install --no-cache-dir -r /tmp/requirements.txt \
    && apt-get purge -y --auto-remove gcc libc6-dev \
    && rm -rf /var/lib/apt/lists/* /root/.cache

# 浏览器：playwright 安装系统依赖，patchright 复用同一套依赖，避免第二次 apt
RUN python -m playwright install --with-deps chromium \
    && python -m patchright install chromium \
    && rm -rf /var/lib/apt/lists/* /root/.cache/ms-playwright/.links

# 创建日志目录
RUN mkdir -p /app/backend-web/logs /app/static/uploads

# 暴露端口
EXPOSE 8089

# 启动服务
CMD ["python", "backend-web/main.py"]
