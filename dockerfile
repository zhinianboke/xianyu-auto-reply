# Dockerfile-armv8
# 为ARMv8优化的闲鱼自动回复系统镜像
# 支持ARM64特定优化和性能提升

# 第一阶段：基础镜像（支持多架构）
FROM --platform=$BUILDPLATFORM python:3.11-slim-bookworm AS base

# 设置环境变量
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    TZ=Asia/Shanghai \
    DOCKER_ENV=true \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \
    # ARMv8优化环境变量
    OPENBLAS_NUM_THREADS=4 \
    OMP_NUM_THREADS=4 \
    MKL_NUM_THREADS=4 \
    PYTHONOPTIMIZE=2 \
    PYTHONMALLOC=malloc \
    # ARM64架构检测
    TARGETARCH=$TARGETARCH

# 设置工作目录
WORKDIR /app

# 第二阶段：构建阶段
FROM base AS builder

# 安装基础依赖和ARM64构建工具
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        curl \
        ca-certificates \
        gcc \
        g++ \
        make \
        cmake \
        pkg-config \
        libffi-dev \
        libssl-dev \
        zlib1g-dev \
        libbz2-dev \
        libreadline-dev \
        libsqlite3-dev \
        wget \
        # ARM64特定构建工具
        gcc-aarch64-linux-gnu \
        g++-aarch64-linux-gnu \
        binutils-aarch64-linux-gnu \
        # ARM64数学库开发包
        libopenblas-dev \
        liblapack-dev \
        libatlas-base-dev \
        && apt-get clean && rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

# 创建虚拟环境
RUN python -m venv /opt/venv && \
    /opt/venv/bin/pip install --no-cache-dir --upgrade pip wheel setuptools

ENV VIRTUAL_ENV=/opt/venv
ENV PATH="$VIRTUAL_ENV/bin:$PATH"

# 复制requirements.txt并安装Python依赖
COPY requirements.txt .

# ARM64优化：根据架构选择优化编译标志
RUN if [ "$TARGETARCH" = "arm64" ]; then \
        echo "🔧 ARM64架构检测，启用优化编译..." && \
        # 设置ARMv8优化编译标志
        export CFLAGS="-march=armv8-a+crc+crypto -mtune=native -O3 -pipe -fstack-protector-strong -fno-plt" && \
        export CXXFLAGS="$CFLAGS" && \
        export LDFLAGS="-Wl,-O1,--sort-common,--as-needed,-z,relro,-z,now" && \
        # 安装针对ARM64优化的包
        pip install --no-cache-dir \
            --compile \
            --global-option="build_ext" \
            --global-option="--enable-optimizations" \
            -r requirements.txt && \
        echo "✅ ARM64优化编译完成"; \
    else \
        echo "🔧 x86_64架构，使用标准编译..." && \
        pip install --no-cache-dir -r requirements.txt; \
    fi

# 复制项目文件
COPY . .

# 第三阶段：运行时阶段
FROM base AS runtime

# 设置标签信息
LABEL maintainer="zhinianboke" \
      version="2.2.1-arm64" \
      description="闲鱼自动回复系统 - ARM64优化版，支持ARMv8指令集加速" \
      repository="https://github.com/zhinianboke/xianyu-auto-reply" \
      license="仅供学习使用，禁止商业用途" \
      author="zhinianboke" \
      architecture="$TARGETARCH" \
      build-date="$BUILD_DATE"

# 安装ARM64优化运行依赖
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        nodejs \
        npm \
        tzdata \
        curl \
        ca-certificates \
        # 图像处理依赖
        libjpeg-dev \
        libpng-dev \
        libfreetype6-dev \
        fonts-dejavu-core \
        fonts-liberation \
        # ARM64优化的数学库
        libopenblas64 \
        liblapack64 \
        libatlas3-base \
        # ARM64多媒体库
        libgstreamer1.0-0 \
        libgstreamer-plugins-base1.0-0 \
        libgstreamer-plugins-good1.0-0 \
        # Playwright浏览器依赖
        libnss3 \
        libnspr4 \
        libatk-bridge2.0-0 \
        libdrm2 \
        libxkbcommon0 \
        libxcomposite1 \
        libxdamage1 \
        libxrandr2 \
        libgbm1 \
        libxss1 \
        libasound2 \
        libatspi2.0-0 \
        libgtk-3-0 \
        libgdk-pixbuf2.0-0 \
        libxcursor1 \
        libxi6 \
        libxrender1 \
        libxext6 \
        libx11-6 \
        libxft2 \
        libxinerama1 \
        libxtst6 \
        libappindicator3-1 \
        libx11-xcb1 \
        libxfixes3 \
        xdg-utils \
        chromium \
        xvfb \
        x11vnc \
        fluxbox \
        # OpenCV运行时依赖
        libgl1 \
        libglib2.0-0 \
        libgl1-mesa-glx \
        libgomp1 \
        # ARM64性能监控工具
        lm-sensors \
        hwdata \
        && apt-get clean && rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

# ARM64特定优化：安装性能工具
RUN if [ "$TARGETARCH" = "arm64" ]; then \
        apt-get update && \
        apt-get install -y --no-install-recommends \
            cpufrequtils \
            ethtool \
            iperf3 \
            stress-ng \
            && apt-get clean && rm -rf /var/lib/apt/lists/*; \
    fi

# 设置时区        
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

# 验证Node.js安装
RUN node --version && npm --version

# 复制Python环境
COPY --from=builder /opt/venv /opt/venv
COPY --from=builder /app /app

ENV VIRTUAL_ENV=/opt/venv
ENV PATH="$VIRTUAL_ENV/bin:$PATH"

# ARM64优化：配置系统性能
RUN if [ "$TARGETARCH" = "arm64" ]; then \
        echo "🔧 配置ARM64性能优化..." && \
        # 调整系统限制
        echo "* soft nofile 65536" >> /etc/security/limits.conf && \
        echo "* hard nofile 65536" >> /etc/security/limits.conf && \
        echo "* soft nproc 65536" >> /etc/security/limits.conf && \
        echo "* hard nproc 65536" >> /etc/security/limits.conf && \
        # 配置内核参数
        echo "vm.swappiness=10" >> /etc/sysctl.conf && \
        echo "vm.vfs_cache_pressure=50" >> /etc/sysctl.conf && \
        # 创建性能优化脚本
        cat > /usr/local/bin/arm64-optimize << 'EOF'
#!/bin/bash
# ARM64性能优化脚本
echo "🔄 应用ARM64性能优化..."
# 设置CPU性能模式
if command -v cpupower &> /dev/null; then
    cpupower frequency-set -g performance
fi
# 设置网络优化
if command -v ethtool &> /dev/null; then
    ethtool -K eth0 tx off rx off tso off gso off 2>/dev/null || true
fi
echo "✅ ARM64优化完成"
EOF
        chmod +x /usr/local/bin/arm64-optimize; \
    fi

# 安装Playwright和浏览器
RUN playwright install chromium && \
    playwright install-deps chromium

# 对于ARM64，可能需要额外的浏览器配置
RUN if [ "$TARGETARCH" = "arm64" ]; then \
        echo "🔧 配置ARM64版Chromium..." && \
        # 创建ARM64优化的Chromium启动脚本
        cat > /usr/local/bin/chromium-arm64 << 'EOF'
#!/bin/bash
# ARM64优化的Chromium启动脚本
export CHROMIUM_FLAGS="\
--disable-background-networking \
--disable-background-timer-throttling \
--disable-breakpad \
--disable-client-side-phishing-detection \
--disable-component-update \
--disable-default-apps \
--disable-dev-shm-usage \
--disable-extensions \
--disable-features=site-per-process,TranslateUI \
--disable-hang-monitor \
--disable-ipc-flooding-protection \
--disable-popup-blocking \
--disable-prompt-on-repost \
--disable-renderer-backgrounding \
--disable-sync \
--disable-translate \
--metrics-recording-only \
--no-first-run \
--safebrowsing-disable-auto-update \
--use-mock-keychain \
--no-sandbox \
--disable-setuid-sandbox \
--disable-gpu \
--disable-dev-shm-usage \
--disable-software-rasterizer \
--disable-web-security \
--disable-features=VizDisplayCompositor \
--enable-features=NetworkServiceInProcess"
exec chromium $CHROMIUM_FLAGS "$@"
EOF
        chmod +x /usr/local/bin/chromium-arm64; \
    fi

# 创建必要的目录并设置权限
RUN mkdir -p /app/logs /app/data /app/backups /app/static/uploads/images && \
    chmod 777 /app/logs /app/data /app/backups /app/static/uploads /app/static/uploads/images

# 配置系统限制，防止core文件生成
RUN echo "ulimit -c 0" >> /etc/profile && \
    echo "kernel.core_pattern=|/bin/false" >> /etc/sysctl.conf

# 创建ARM64优化启动脚本
RUN cat > /app/start_arm64.sh << 'EOF'
#!/bin/bash
# ARM64优化启动脚本

echo "🚀 闲鱼自动回复系统 ARM64优化版启动中..."
echo "=========================================="

# 检测架构
ARCH=$(uname -m)
echo "架构: $ARCH"

if [ "$ARCH" = "aarch64" ] || [ "$ARCH" = "arm64" ]; then
    echo "✅ 检测到ARM64架构，启用优化..."
    
    # 应用ARM64性能优化
    if [ -f /usr/local/bin/arm64-optimize ]; then
        /usr/local/bin/arm64-optimize
    fi
    
    # 设置ARM64特定的环境变量
    export ARM64_OPTIMIZED=true
    export ENABLE_NEON_ACCELERATION=true
    export USE_HARDWARE_CRC32=true
    
    # 调整Python内存分配器
    export PYTHONMALLOC=malloc
    
    # 根据CPU核心数调整线程数
    CPU_CORES=$(nproc)
    export OPENBLAS_NUM_THREADS=$((CPU_CORES > 4 ? 4 : CPU_CORES))
    export OMP_NUM_THREADS=$((CPU_CORES > 4 ? 4 : CPU_CORES))
    export MKL_NUM_THREADS=$((CPU_CORES > 4 ? 4 : CPU_CORES))
    
    echo "🎯 ARM64优化配置:"
    echo "   CPU核心数: $CPU_CORES"
    echo "   OpenBLAS线程数: $OPENBLAS_NUM_THREADS"
    echo "   OMP线程数: $OMP_NUM_THREADS"
    
    # 检测ARMv8特性
    echo "🔍 检测ARMv8特性..."
    if grep -q "crc32" /proc/cpuinfo; then
        echo "   ✅ CRC32指令集: 支持"
        export ENABLE_CRC32_ACCELERATION=true
    fi
    
    if grep -q "asimd" /proc/cpuinfo; then
        echo "   ✅ NEON SIMD: 支持"
        export ENABLE_NEON_ACCELERATION=true
    fi
    
    if grep -q "atomics" /proc/cpuinfo; then
        echo "   ✅ ARMv8.1原子指令: 支持"
    fi
    
else
    echo "ℹ️  x86_64架构，使用标准配置..."
fi

echo "=========================================="

# 启动主应用
exec python /app/Start.py
EOF

RUN chmod +x /app/start_arm64.sh /app/entrypoint.sh

# 暴露端口
EXPOSE 8080

# 健康检查（ARM64优化版）
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8080/health || (echo "ARM64健康检查失败" && exit 1)

# 默认使用ARM64优化启动脚本
CMD ["/app/start_arm64.sh"]