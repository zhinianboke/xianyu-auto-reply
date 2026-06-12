# Scheduler 服务 Dockerfile
# 单阶段构建，直接使用Python源码

# 基础镜像使用国内加速源（与 jenkins/优化Buildx网络.sh 一致，buildx 按路径直接拉取）
FROM docker.1ms.run/library/python:3.11-slim

ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright
# Playwright 浏览器下载使用 npmmirror 国内源
ENV PLAYWRIGHT_DOWNLOAD_HOST=https://cdn.npmmirror.com/binaries/playwright

# 配置国内镜像源
RUN sed -i 's|deb.debian.org|mirrors.aliyun.com|g' /etc/apt/sources.list.d/debian.sources 2>/dev/null || \
    sed -i 's|deb.debian.org|mirrors.aliyun.com|g' /etc/apt/sources.list 2>/dev/null || true
RUN pip config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple

WORKDIR /app

RUN apt-get update && apt-get install -y curl ca-certificates gcc \
    && update-ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# 复制项目源码
COPY common /app/common
COPY scheduler /app/scheduler
COPY launcher /app/launcher

# 从pyproject.toml提取并安装依赖
RUN python -c "\
import tomllib; \
deps = tomllib.load(open('/app/scheduler/pyproject.toml','rb')).get('project',{}).get('dependencies',[]); \
open('/tmp/requirements.txt','w').write('\n'.join(deps))" && \
    pip install --no-cache-dir -r /tmp/requirements.txt

# 安装Playwright浏览器
RUN python -m playwright install --with-deps chromium

# 创建日志目录
RUN mkdir -p /app/scheduler/logs

# 暴露端口
EXPOSE 8091

ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app
ENV TZ=Asia/Shanghai

# 启动服务
CMD ["python", "scheduler/main.py"]
