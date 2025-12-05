"""项目启动入口：

1. 创建 CookieManager，按配置文件 / 环境变量初始化账号任务
2. 在后台线程启动 FastAPI (reply_server) 提供管理与自动回复接口
3. 主协程保持运行
"""

import os
import sys
import shutil
from pathlib import Path

# ==================== ARMv8架构优化 ====================
def _setup_armv8_optimization():
    """初始化ARMv8架构优化"""
    try:
        # 检查当前架构
        import platform
        arch = platform.machine().lower()
        is_arm64 = arch in ('aarch64', 'arm64', 'armv8')
        
        if not is_arm64:
            # 非ARM64架构，使用标准配置
            print(f"[INFO] 检测到架构: {arch}，使用标准配置")
            return False
        
        print("=" * 60)
        print("⚡ 检测到ARM64架构，启用优化配置...")
        
        # 设置ARM64性能优化环境变量
        os.environ.setdefault('ARM64_OPTIMIZED', 'true')
        
        # Python性能优化
        os.environ.setdefault('PYTHONOPTIMIZE', '2')
        os.environ.setdefault('PYTHONMALLOC', 'malloc')
        
        # 数学库优化
        cpu_count = os.cpu_count() or 4
        os.environ.setdefault('OPENBLAS_NUM_THREADS', str(min(cpu_count, 4)))
        os.environ.setdefault('OMP_NUM_THREADS', str(min(cpu_count, 4)))
        os.environ.setdefault('MKL_NUM_THREADS', str(min(cpu_count, 4)))
        
        # 检测ARMv8特性
        armv8_features = _detect_armv8_features()
        
        if armv8_features.get('has_crc32'):
            os.environ.setdefault('ENABLE_CRC32_ACCELERATION', 'true')
            print("   ✅ CRC32硬件加速: 启用")
        
        if armv8_features.get('has_neon'):
            os.environ.setdefault('ENABLE_NEON_ACCELERATION', 'true')
            print("   ✅ NEON SIMD优化: 启用")
        
        if armv8_features.get('has_crypto'):
            os.environ.setdefault('ENABLE_CRYPTO_ACCELERATION', 'true')
            print("   ✅ 加密指令加速: 启用")
        
        # 架构信息
        cpu_model = armv8_features.get('cpu_model', 'ARM64处理器')
        print(f"   📊 CPU型号: {cpu_model}")
        print(f"   🎯 CPU核心数: {cpu_count}")
        
        print("=" * 60)
        return True
        
    except Exception as e:
        print(f"[WARN] ARMv8优化初始化失败: {e}")
        return False

def _detect_armv8_features():
    """检测ARMv8 CPU特性"""
    features = {
        'has_crc32': False,
        'has_neon': False,
        'has_crypto': False,
        'has_atomics': False,
        'cpu_model': '未知ARM64处理器'
    }
    
    try:
        import platform
        arch = platform.machine().lower()
        
        if arch not in ('aarch64', 'arm64', 'armv8'):
            return features
        
        # Linux系统检测
        if sys.platform == 'linux':
            if Path('/proc/cpuinfo').exists():
                with open('/proc/cpuinfo', 'r') as f:
                    cpuinfo = f.read().lower()
                
                features['has_crc32'] = 'crc32' in cpuinfo or 'pmull' in cpuinfo
                features['has_neon'] = 'asimd' in cpuinfo
                features['has_crypto'] = all(x in cpuinfo for x in ['aes', 'sha1', 'sha2'])
                features['has_atomics'] = 'atomics' in cpuinfo
                
                # 获取CPU型号
                for line in cpuinfo.split('\n'):
                    if 'model name' in line or 'processor' in line:
                        if ':' in line:
                            features['cpu_model'] = line.split(':')[1].strip()
                            break
        
        # macOS系统检测 (Apple Silicon)
        elif sys.platform == 'darwin' and arch == 'arm64':
            try:
                import subprocess
                result = subprocess.run(
                    ['sysctl', '-n', 'machdep.cpu.brand_string'],
                    capture_output=True, text=True
                )
                if result.returncode == 0:
                    features['cpu_model'] = result.stdout.strip()
                
                # Apple Silicon已知特性
                features['has_crc32'] = True
                features['has_neon'] = True
                features['has_crypto'] = True
                features['has_atomics'] = True  # M1/M2支持ARMv8.1原子指令
            except:
                pass
        
    except Exception:
        pass
    
    return features

# 在程序启动时应用ARMv8优化
_armv8_optimized = _setup_armv8_optimization()
# ==================== ARMv8优化结束 ====================

# 设置标准输出编码为UTF-8（Windows兼容）
def _setup_console_encoding():
    """设置控制台编码为UTF-8，避免Windows GBK编码问题"""
    # ... 保持原有代码不变 ...
