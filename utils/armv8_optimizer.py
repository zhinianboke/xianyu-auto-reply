# utils/armv8_optimizer.py
"""
ARMv8指令集优化检测器
支持CRC32、加密指令、NEON SIMD等硬件加速
"""

import platform
import subprocess
import sys
from typing import Dict, Any

class ARMV8Optimizer:
    """ARMv8架构优化器"""
    
    def __init__(self):
        self.arch = platform.machine().lower()
        self.is_arm64 = self.arch in ('aarch64', 'arm64', 'armv8')
        self.features = self._detect_features()
    
    def _detect_features(self) -> Dict[str, bool]:
        """检测ARMv8 CPU特性"""
        features = {
            'has_crc32': False,
            'has_crypto': False,  # AES/SHA1/SHA2
            'has_neon': False,
            'has_atomics': False,  # ARMv8.1 LSE
            'has_fp16': False,     # ARMv8.2 FP16
            'has_dotprod': False,  # ARMv8.2 Dot Product
        }
        
        if not self.is_arm64:
            return features
        
        try:
            # 在Linux上检测CPU特性
            if sys.platform == 'linux':
                with open('/proc/cpuinfo', 'r') as f:
                    cpuinfo = f.read().lower()
                
                # 检测各种ARMv8特性
                features['has_crc32'] = 'crc32' in cpuinfo or 'pmull' in cpuinfo
                features['has_crypto'] = all(x in cpuinfo for x in ['aes', 'sha1', 'sha2'])
                features['has_neon'] = 'asimd' in cpuinfo
                features['has_atomics'] = 'atomics' in cpuinfo
                features['has_fp16'] = 'fphp' in cpuinfo or 'asimdhp' in cpuinfo
                features['has_dotprod'] = 'asimddp' in cpuinfo or 'dotprod' in cpuinfo
            
            # macOS (Apple Silicon) 特性检测
            elif sys.platform == 'darwin' and self.arch == 'arm64':
                features['has_crc32'] = True
                features['has_crypto'] = True
                features['has_neon'] = True
                features['has_atomics'] = True  # M1/M2支持ARMv8.1原子指令
                features['has_fp16'] = True     # Apple Neural Engine
                features['has_dotprod'] = True
            
        except Exception as e:
            print(f"[警告] ARMv8特性检测失败: {e}")
        
        return features
    
    def optimize_for_armv8(self) -> None:
        """应用ARMv8优化配置"""
        if not self.is_arm64:
            return
        
        print(f"⚡ ARM64架构优化启动 ({self.arch})")
        print(f"✅ 检测到ARMv8特性: {self.get_feature_summary()}")
        
        # 设置环境变量以优化ARM64性能
        import os
        
        # 优化Python内存管理
        os.environ.setdefault('PYTHONMALLOC', 'malloc')
        
        # 对于NumPy，使用ARM64优化的BLAS库
        if self.features['has_neon']:
            os.environ.setdefault('NPY_USE_BLAS_ILP64', '0')
            os.environ.setdefault('NPY_BLAS_ORDER', 'openblas')
            os.environ.setdefault('NPY_LAPACK_ORDER', 'openblas')
        
        # 设置OpenBLAS线程数（ARM通常核心更多）
        cpu_count = os.cpu_count() or 4
        os.environ.setdefault('OPENBLAS_NUM_THREADS', str(min(cpu_count, 8)))
        os.environ.setdefault('OMP_NUM_THREADS', str(min(cpu_count, 8)))
    
    def get_feature_summary(self) -> str:
        """获取特性摘要"""
        if not self.is_arm64:
            return "非ARM64架构"
        
        enabled = [f for f, has in self.features.items() if has]
        return f"已启用: {', '.join(enabled) if enabled else '基础ARM64'}"
    
    def should_use_hardware_acceleration(self) -> bool:
        """是否应该使用硬件加速"""
        return any(self.features.values())
    
    def get_cpu_model(self) -> str:
        """获取CPU型号信息"""
        if not self.is_arm64:
            return "未知"
        
        try:
            if sys.platform == 'linux':
                with open('/proc/cpuinfo', 'r') as f:
                    for line in f:
                        if 'model name' in line or 'Processor' in line:
                            return line.split(':')[1].strip()
            
            elif sys.platform == 'darwin':
                result = subprocess.run(
                    ['sysctl', '-n', 'machdep.cpu.brand_string'],
                    capture_output=True, text=True
                )
                if result.returncode == 0:
                    return result.stdout.strip()
        
        except Exception:
            pass
        
        return "ARM64处理器"


# 全局实例
armv8_optimizer = ARMV8Optimizer()

# 快速访问函数
def is_arm64() -> bool:
    return armv8_optimizer.is_arm64

def has_armv8_feature(feature: str) -> bool:
    return armv8_optimizer.features.get(feature, False)

def optimize_system() -> None:
    """优化系统配置（在项目启动时调用）"""
    armv8_optimizer.optimize_for_armv8()